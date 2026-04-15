import json
import re
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional
from collections import defaultdict
import logging
from typing_extensions import Annotated, Doc

from derisk.agent.resource import tool
from derisk_serve.agent.resource.func_registry import derisk_tool

# 使用 derisk 统一日志系统，不调用 logging.basicConfig 以防止重复输出
logger = logging.getLogger(__name__)


# Constants

async def _fetch_flamegraph_svg(profile_path: str) -> Optional[str]:
    try:
        with open(profile_path, 'r', encoding='utf-8') as file:
            return file.read()
    except FileNotFoundError:
        logger.info(f"错误：火焰图文件 {profile_path} 不存在")
        return None
    except UnicodeDecodeError:
        logger.info(f"错误：火焰图文件 {profile_path} 编码解析失败")
        return None

def _parse_flamegraph_svg(svg_content: str) -> Dict:
    """
    解析火焰图SVG，提取性能数据并构建层级关系
    Args:
        svg_content: SVG内容
    Returns:
        Dict: 解析后的性能数据，包含层级关系
    """
    try:
        # 解析SVG
        root = ET.fromstring(svg_content)

        # 提取所有rect元素，支持不同的命名空间
        rects = []
        # 尝试不同的命名空间查找方式
        for ns in ['', '{http://www.w3.org/2000/svg}']:
            found_rects = root.findall(f'.//{ns}rect')
            if found_rects:
                rects = found_rects
                break

        # 如果还是没找到，尝试直接查找所有rect元素
        if not rects:
            for elem in root.iter():
                if elem.tag.endswith('rect'):
                    rects.append(elem)

        logger.info(f"解析到 {len(rects)} 个rect元素")

        # 构建函数调用数据
        functions = []

        # 获取SVG尺寸
        svg_width = float(root.get('width', 1440))
        svg_height = float(root.get('height', 1686))

        # 收集所有有效的Y坐标来计算层级
        valid_y_coords = []
        for rect in rects:
            try:
                # 处理百分比格式的坐标值
                y_str = rect.get('y', '0')
                height_str = rect.get('height', '0')
                width_str = rect.get('width', '0')

                # 移除百分比符号并转换为浮点数
                y = float(y_str.rstrip('%'))
                height = float(height_str.rstrip('%'))
                width = float(width_str.rstrip('%'))

                # 跳过背景rect和无效rect
                if width >= 99.0 and height >= 99.0:
                    continue
                if height <= 0 or width <= 0:
                    continue

                valid_y_coords.append(y)
            except (ValueError, TypeError):
                continue

        # 对Y坐标排序，用于计算层级
        valid_y_coords = sorted(set(valid_y_coords))

        # 检测火焰图方向：通过查找"all"函数的位置来判断
        # 如果all函数在Y坐标较小的位置，说明是正向火焰图（all在顶部）
        # 如果all函数在Y坐标较大的位置，说明是反向火焰图（all在底部）
        all_function_y = None
        for rect in rects:
            try:
                # 查找title元素
                title_element = None
                for ns in ['', '{http://www.w3.org/2000/svg}']:
                    title_element = rect.find(f'.//{ns}title')
                    if title_element is not None:
                        break

                if title_element is not None and title_element.text:
                    title_text = title_element.text.strip()
                    if title_text.startswith('all ') or title_text == 'all':
                        y_str = rect.get('y', '0')
                        all_function_y = float(y_str.rstrip('%'))
                        break
            except (ValueError, TypeError):
                continue

        # 判断火焰图方向
        is_inverted = False  # 默认正向（all在顶部）
        if all_function_y is not None and valid_y_coords:
            # 如果all函数的Y坐标在中位数以上，说明是反向火焰图
            median_y = sorted(valid_y_coords)[len(valid_y_coords) // 2]
            is_inverted = all_function_y > median_y
            logger.info(f"检测到火焰图方向: {'反向(all在底部)' if is_inverted else '正向(all在顶部)'}, all_y={all_function_y}, median_y={median_y}")

        # 创建Y坐标到层级的映射
        y_to_level = {}
        if is_inverted:
            # 反向火焰图：Y值越大层级越低（L1在底部）
            valid_y_coords_sorted = sorted(set(valid_y_coords), reverse=True)
            for i, y in enumerate(valid_y_coords_sorted):
                y_to_level[y] = i + 1
        else:
            # 正向火焰图：Y值越小层级越低（L1在顶部）
            valid_y_coords_sorted = sorted(set(valid_y_coords))
            for i, y in enumerate(valid_y_coords_sorted):
                y_to_level[y] = i + 1

        # 构建元素到父元素的映射
        parent_map = {}
        for parent in root.iter():
            for child in parent:
                parent_map[child] = parent

        # 解析每个rect及其对应的title
        for i, rect in enumerate(rects):
            try:
                # 处理百分比格式的坐标值
                x_str = rect.get('x', '0')
                y_str = rect.get('y', '0')
                width_str = rect.get('width', '0')
                height_str = rect.get('height', '0')

                # 移除百分比符号并转换为浮点数
                x = float(x_str.rstrip('%'))
                y = float(y_str.rstrip('%'))
                width = float(width_str.rstrip('%'))
                height = float(height_str.rstrip('%'))

                # 跳过背景rect（通常是第一个，覆盖整个SVG）
                if width >= 99.0 and height >= 99.0:  # 调整阈值以适应百分比格式
                    continue

                # 跳过无效的rect
                if height <= 0 or width <= 0:
                    continue

                # 初始化变量
                function_name = ""
                samples = 0
                percentage = 0.0
                title_text = ""

                # 获取原始的x和width值（如果存在fg:x和fg:w属性）
                original_x = rect.get('fg:x')
                original_width = rect.get('fg:w')
                if original_x is not None:
                    try:
                        original_x = int(original_x)
                    except (ValueError, TypeError):
                        original_x = None
                if original_width is not None:
                    try:
                        original_width = int(original_width)
                        samples = original_width  # fg:w通常表示采样数
                    except (ValueError, TypeError):
                        original_width = None

                # 查找与当前rect关联的title元素
                # 方法1：查找rect的直接子元素title
                title_element = None
                for ns in ['', '{http://www.w3.org/2000/svg}']:
                    title_element = rect.find(f'.//{ns}title')
                    if title_element is not None:
                        break

                # 方法2：如果没找到子title，查找父元素中的title
                if title_element is None:
                    parent = parent_map.get(rect)
                    if parent is not None:
                        # 查找父元素下的所有title
                        for ns in ['', '{http://www.w3.org/2000/svg}']:
                            parent_titles = parent.findall(f'.//{ns}title')
                            if parent_titles:
                                # 尝试找到位置最接近的title
                                for title in parent_titles:
                                    if title.text and title.text.strip():
                                        title_element = title
                                        break
                                if title_element is not None:
                                    break

                # 方法3：如果还是没找到，查找同级的g元素中的title
                if title_element is None:
                    parent = parent_map.get(rect)
                    if parent is not None:
                        # 查找同级g元素
                        for ns in ['', '{http://www.w3.org/2000/svg}']:
                            siblings = parent.findall(f'.//{ns}g')
                            if siblings:
                                for sibling in siblings:
                                    title = sibling.find(f'.//{ns}title')
                                    if title is not None and title.text and title.text.strip():
                                        # 检查这个g元素是否包含当前rect的坐标范围
                                        g_rects = sibling.findall(f'.//{ns}rect')
                                        for g_rect in g_rects:
                                            try:
                                                g_x_str = g_rect.get('x', '0')
                                                g_y_str = g_rect.get('y', '0')
                                                g_width_str = g_rect.get('width', '0')
                                                g_height_str = g_rect.get('height', '0')

                                                g_x = float(g_x_str.rstrip('%'))
                                                g_y = float(g_y_str.rstrip('%'))
                                                g_width = float(g_width_str.rstrip('%'))
                                                g_height = float(g_height_str.rstrip('%'))

                                                # 检查坐标是否匹配（允许小的误差）
                                                if (abs(g_x - x) < 0.01 and abs(g_y - y) < 0.01 and
                                                        abs(g_width - width) < 0.01 and abs(g_height - height) < 0.01):
                                                    title_element = title
                                                    break
                                            except (ValueError, TypeError):
                                                continue
                                        if title_element is not None:
                                            break
                                if title_element is not None:
                                    break

                # 解析title信息
                if title_element is not None:
                    title_text = title_element.text or ""
                    if title_text:
                        # 解析title格式，支持多种格式：
                        # 格式1：'函数名 (samples数, 百分比%)'
                        # 格式2：'函数名 (samples数 samples, 百分比%)'
                        # 例如：'C2_CompilerThre (3,019 samples, 73.22%)'
                        # 例如：'_build_request (derisk/util/api_utils.py:174) (4 samples, 0.12%)'
                        if '(' in title_text and ')' in title_text:
                            # 找到最后一个括号对，这通常包含采样信息
                            last_paren_start = title_text.rfind('(')
                            last_paren_end = title_text.rfind(')')

                            if last_paren_start < last_paren_end:
                                function_name = title_text[:last_paren_start].strip()
                                info_part = title_text[last_paren_start+1:last_paren_end]

                                try:
                                    # 解析samples数和百分比
                                    # 匹配格式：3,019 samples, 73.22% 或 4 samples, 0.12%
                                    samples_match = re.search(r'([\d,]+)\s*samples?', info_part)
                                    if samples_match:
                                        samples_str = samples_match.group(1).replace(',', '')
                                        samples = int(samples_str)
                                    elif original_width is not None:
                                        # 如果title中没有找到samples，使用fg:w的值
                                        samples = original_width

                                    # 解析百分比
                                    percentage_match = re.search(r'([\d.]+)%', info_part)
                                    if percentage_match:
                                        percentage = float(percentage_match.group(1))

                                except (ValueError, AttributeError) as e:
                                    logger.warning(f"解析title信息失败: {title_text}, 错误: {e}")
                                    # 如果解析失败，使用默认值或fg:w的值
                                    if original_width is not None:
                                        samples = original_width
                                    else:
                                        samples = 1
                                    percentage = width  # 在百分比格式中，width本身就是百分比
                            else:
                                # 没有有效的括号信息
                                function_name = title_text.strip()
                                if original_width is not None:
                                    samples = original_width
                                else:
                                    samples = 1
                                percentage = width  # 在百分比格式中，width本身就是百分比
                        else:
                            # 没有括号信息的title，直接作为函数名
                            function_name = title_text.strip()
                            if original_width is not None:
                                samples = original_width
                            else:
                                samples = 1
                            percentage = width  # 在百分比格式中，width本身就是百分比

                # 如果没有获取到函数名，尝试从text元素获取
                if not function_name:
                    # 查找与rect关联的text元素
                    text_element = None
                    for ns in ['', '{http://www.w3.org/2000/svg}']:
                        text_element = rect.find(f'.//{ns}text')
                        if text_element is not None:
                            break

                    if text_element is None:
                        parent = parent_map.get(rect)
                        if parent is not None:
                            for ns in ['', '{http://www.w3.org/2000/svg}']:
                                text_element = parent.find(f'.//{ns}text')
                                if text_element is not None:
                                    break

                    if text_element is not None and text_element.text:
                        function_name = text_element.text.strip()

                # 如果还是没有函数名，跳过这个元素
                if not function_name or function_name == "None":
                    continue

                # 修复层级计算 - 使用Y坐标映射到层级
                level = y_to_level.get(y, 1)

                functions.append({
                    'id': f"func_{i}",
                    'name': function_name,
                    'x': x,
                    'y': y,
                    'width': width,
                    'height': height,
                    'samples': samples,
                    'percentage': percentage,
                    'level': level,
                    'title': title_text,
                    'index': i,
                    'original_x': original_x,
                    'original_width': original_width
                })

            except (ValueError, TypeError) as e:
                logger.warning(f"解析rect元素 {i} 失败: {e}")
                continue

        logger.info(f"成功解析 {len(functions)} 个有效函数")

        # 计算总采样数
        total_samples = max(f['samples'] for f in functions) if functions else 0

        # 找到根节点（all函数，通常samples最多）
        root_function = None
        for func in functions:
            if func['name'] == 'all' or func['samples'] == total_samples:
                root_function = func
                total_samples = func['samples']
                break

        # 构建层级关系
        functions_by_level = defaultdict(list)
        for func in functions:
            functions_by_level[func['level']].append(func)

        return {
            'total_functions': len(functions),
            'total_samples': total_samples,
            'functions': functions,
            'functions_by_level': dict(functions_by_level),
            'max_level': max(functions_by_level.keys()) if functions_by_level else 0,
            'min_level': min(functions_by_level.keys()) if functions_by_level else 0,
            'svg_width': svg_width,
            'svg_height': svg_height,
            'root_function': root_function,
            'is_inverted': is_inverted
        }

    except ET.ParseError as e:
        logger.error(f"SVG解析失败: {e}")
        return {'error': f'SVG解析失败: {str(e)}'}


def _build_hierarchical_view(parsed_data: Dict, max_functions_per_level: int = 5, limit: int = 50) -> List[str]:
    """
    构建层级视图，从L1（底层）到最高层显示主要函数
    Args:
        parsed_data: 解析后的数据
        max_functions_per_level: 每层最多显示的函数数
        limit: 限制返回的层级数量
    Returns:
        List[str]: 层级视图字符串列表
    """
    if 'error' in parsed_data:
        return []

    functions_by_level = parsed_data.get('functions_by_level', {})
    if not functions_by_level:
        return []

    result = []

    # 从L1开始到最高层
    for level in sorted(functions_by_level.keys()):
        level_functions = functions_by_level[level]

        # 合并相同名称的函数
        function_stats = defaultdict(lambda: {
            'samples': 0,
            'percentage': 0.0,
            'count': 0
        })

        for func in level_functions:
            name = func['name']
            # 过滤无意义的函数名
            if (name.startswith('unknown_func_') or
                    name.startswith('func_') or
                    name.startswith('parse_error_') or
                    len(name) <= 2 or
                    name == "None"):
                continue

            function_stats[name]['samples'] = max(function_stats[name]['samples'], func['samples'])
            function_stats[name]['percentage'] = max(function_stats[name]['percentage'], func['percentage'])
            function_stats[name]['count'] += 1

        # 转换为列表并排序（按samples降序）
        level_result = []
        for name, stats in function_stats.items():
            level_result.append({
                'name': name,
                'samples': stats['samples'],
                'percentage': stats['percentage']
            })

        level_result.sort(key=lambda x: x['samples'], reverse=True)

        # 构建该层级的显示字符串
        if level_result:
            # 如果是L1层且有all函数，只显示all
            if level == 1 and any(f['name'] == 'all' for f in level_result):
                all_func = next(f for f in level_result if f['name'] == 'all')
                result.append(
                    f"L{level} {all_func['name']} ({all_func['samples']} samples, {all_func['percentage']:.2f}%)")
            else:
                # 显示前N个函数
                func_strs = []
                for func in level_result[:max_functions_per_level]:
                    func_strs.append(f"{func['name']} ({func['samples']} samples, {func['percentage']:.2f}%)")
                result.append(f"L{level} {', '.join(func_strs)}")

        # 如果达到限制层级数量，停止添加
        if len(result) >= limit:
            break

    # 倒序显示（从高层到低层）
    result.reverse()

    return result



# 工具定义
profile_path_info = {
    "type": "string",
    "description": "性能分析地址，用于获取对应的火焰图数据"
}


# @derisk_tool(
#     name="flamegraph_overview",
#     description="获取火焰图概览，按层级显示CPU占用最高的函数（从L1根节点向上展示）",
#     input_schema={
#         "type": "object",
#         "properties": {
#             "profile_path": profile_path_info,
#             "max_functions_per_level": {
#                 "type": "integer",
#                 "description": "每层最多显示的函数数，默认为5",
#                 "default": 5,
#             },
#             "limit": {
#                 "type": "integer",
#                 "description": "限制返回的层级数量，默认为50层（L1-L50）",
#                 "default": 50,
#             }
#         },
#         "required": ["profile_id"]
#     }
# )


@tool(description="获取火焰图概览，按层级显示CPU占用最高的函数（从L1根节点向上展示）")
async def flamegraph_overview(profile_path: Annotated[str, Doc("性能分析地址，用于获取对应的火焰图数据.")],
                              max_functions_per_level: Annotated[int, Doc("每层最多显示的函数数，默认为5")] = 5,
                              limit: Annotated[int, Doc("限制返回的层级数量，默认为50层（L1-L50）")] = 50) -> str:
    """
    获取火焰图概览，按层级显示CPU占用最高的函数
    Args:
        profile_path: 性能分析ID
        max_functions_per_level: 每层最多显示的函数数，默认为5
        limit: 限制返回的层级数量，默认为50层
    Returns:
        str: JSON格式的分析结果
    """
    try:
        # 获取火焰图SVG数据
        svg_content = await _fetch_flamegraph_svg(profile_path)

        # 解析SVG数据
        parsed_data = _parse_flamegraph_svg(svg_content)

        if 'error' in parsed_data:
            return json.dumps({
                'success': False,
                'error': parsed_data['error']
            }, ensure_ascii=False, indent=2)

        # 构建层级视图，限制层级数量
        hierarchical_view = _build_hierarchical_view(parsed_data, max_functions_per_level, limit)

        # 构建返回结果
        result = {
            'success': True,
            'profile_path': profile_path,
            'summary': {
                'total_functions': parsed_data['total_functions'],
                'total_samples': parsed_data['total_samples'],
                'total_levels': parsed_data['max_level'],
                'displayed_levels': min(limit, parsed_data['max_level']),
            },
            'hierarchical_view': hierarchical_view,
            'description': f"火焰图层级视图（显示前{min(limit, parsed_data['max_level'])}层，从高层到低层，L1是根节点）"
        }

        return json.dumps(result, ensure_ascii=False, indent=2)

    except Exception as e:
        logger.error(f"火焰图概览分析失败: {e}")
        return json.dumps({
            'success': False,
            'error': f'火焰图概览分析失败: {str(e)}'
        }, ensure_ascii=False, indent=2)


# @derisk_tool(
#     name="flamegraph_drill_down",
#     description="深入分析指定函数，展示该函数及其上层（子函数）的CPU占用情况，支持精确匹配和模糊匹配",
#     input_schema={
#         "type": "object",
#         "properties": {
#             "profile_path": profile_path_info,
#             "function_name": {
#                 "type": "string",
#                 "description": "要分析的函数名称，通常从概览结果中选择感兴趣的函数。支持精确匹配和模糊匹配（当fuzzy_match=True时）"
#             },
#             "fuzzy_match": {
#                 "type": "boolean",
#                 "description": "是否使用模糊匹配，默认为False。当为True时，会匹配包含function_name的所有函数",
#                 "default": True
#             },
#             "levels_to_show": {
#                 "type": "integer",
#                 "description": "显示多少层子函数，默认为10层",
#                 "default": 10
#             }
#         },
#         "required": ["profile_id", "function_name"]
#     }
# )
@tool(description="深入分析指定函数，展示该函数及其上层（子函数）的CPU占用情况，支持精确匹配和模糊匹配")
async def flamegraph_drill_down(profile_path: Annotated[str, Doc("性能分析地址，用于获取对应的火焰图数据.")],
                                function_name: Annotated[str, Doc(
                                    "要分析的函数名称，通常从概览结果中选择感兴趣的函数。支持精确匹配和模糊匹配（当fuzzy_match=True时）.")],
                                fuzzy_match: Annotated[bool, Doc(
                                    "是否使用模糊匹配，默认为False。当为True时，会匹配包含function_name的所有函数")] = False,
                                levels_to_show: Annotated[int, Doc("显示多少层子函数，默认为10层.")] = 10) -> str:
    """
    钻取分析指定函数的子函数调用情况
    Args:
        profile_path: 火焰图文件路径
        function_name: 要分析的函数名称
        fuzzy_match: 是否使用模糊匹配，默认为False
        levels_to_show: 显示多少层子函数，默认为5层
    Returns:
        str: JSON格式的分析结果
    """
    try:
        # 获取火焰图SVG数据
        svg_content = await _fetch_flamegraph_svg(profile_path)

        # 解析SVG数据
        parsed_data = _parse_flamegraph_svg(svg_content)

        if 'error' in parsed_data:
            return json.dumps({
                'success': False,
                'error': parsed_data['error']
            }, ensure_ascii=False, indent=2)

        # 查找指定的函数 - 支持精确匹配和模糊匹配
        if fuzzy_match:
            # 模糊匹配：查找包含function_name的所有函数
            target_functions = [f for f in parsed_data['functions'] if function_name.lower() in f['name'].lower()]
        else:
            # 精确匹配
            target_functions = [f for f in parsed_data['functions'] if f['name'] == function_name]

        if not target_functions:
            match_type = "模糊匹配" if fuzzy_match else "精确匹配"
            return json.dumps({
                'success': False,
                'error': f'未找到函数: {function_name} ({match_type})'
            }, ensure_ascii=False, indent=2)

        # 选择采样数最多的实例
        target_function = max(target_functions, key=lambda x: x['samples'])
        target_level = target_function['level']
        target_x = target_function['x']
        target_width = target_function['width']
        target_x_end = target_x + target_width

        # 构建该函数的调用链视图 - 只包含目标函数及其子函数
        hierarchical_view = []

        # 添加目标函数本身
        match_info = f" [FUZZY MATCH]" if fuzzy_match else ""
        hierarchical_view.append(
            f"L{target_level} [TARGET]{match_info} {target_function['name']} ({target_function['samples']} samples, {target_function['percentage']:.2f}%)"
        )

        # 如果是模糊匹配且找到多个函数，显示所有匹配的函数
        if fuzzy_match and len(target_functions) > 1:
            other_matches = [f for f in target_functions if f != target_function]
            other_matches.sort(key=lambda x: x['samples'], reverse=True)

            hierarchical_view.append("--- 其他匹配的函数 ---")
            for i, func in enumerate(other_matches[:5]):  # 最多显示5个其他匹配
                hierarchical_view.append(
                    f"L{func['level']} [MATCH {i + 2}] {func['name']} ({func['samples']} samples, {func['percentage']:.2f}%)"
                )
            if len(other_matches) > 5:
                hierarchical_view.append(f"... 还有 {len(other_matches) - 5} 个匹配的函数")
            hierarchical_view.append("--- 主要函数的子函数调用链 ---")

        # 只查找上层函数（子函数），不查找下层函数
        for level_offset in range(1, levels_to_show + 1):
            child_level = target_level + level_offset
            if child_level > parsed_data['max_level']:
                break

            # 查找在目标函数范围内的子函数
            child_functions = []
            for func in parsed_data['functions']:
                if func['level'] == child_level:
                    # 子函数应该在目标函数的X坐标范围内
                    func_x = func['x']
                    func_x_end = func['x'] + func['width']
                    # 检查是否在目标函数的范围内（有重叠）
                    if (func_x >= target_x and func_x < target_x_end) or \
                            (func_x_end > target_x and func_x_end <= target_x_end) or \
                            (func_x <= target_x and func_x_end >= target_x_end):
                        child_functions.append(func)

            if child_functions:
                # 合并相同名称的函数
                function_stats = defaultdict(lambda: {
                    'samples': 0,
                    'percentage': 0.0
                })

                for func in child_functions:
                    name = func['name']
                    function_stats[name]['samples'] = max(function_stats[name]['samples'], func['samples'])
                    function_stats[name]['percentage'] = max(function_stats[name]['percentage'], func['percentage'])

                # 排序并构建显示字符串
                level_funcs = []
                for name, stats in sorted(function_stats.items(), key=lambda x: x[1]['samples'], reverse=True):
                    level_funcs.append(f"{name} ({stats['samples']} samples, {stats['percentage']:.2f}%)")

                # 只显示前5个最重要的函数
                hierarchical_view.append(f"L{child_level} {', '.join(level_funcs[:5])}")
            else:
                # 如果没有找到子函数，停止继续查找
                break

        # 构建返回结果
        result = {
            'success': True,
            'profile_path': profile_path,
            'target_function': {
                'name': function_name,
                'actual_name': target_function['name'],
                'level': target_level,
                'samples': target_function['samples'],
                'percentage': target_function['percentage'],
                'occurrences': len(target_functions),
                'fuzzy_match': fuzzy_match
            },
            'hierarchical_view': hierarchical_view,
            'description': f"函数 {function_name} 的子函数调用链分析（{'模糊匹配' if fuzzy_match else '精确匹配'}，从L{target_level}层开始向上{len([h for h in hierarchical_view if h.startswith('L') and '[TARGET]' in h or h.startswith('L') and '[TARGET]' not in h and '[MATCH' not in h]) - 1}层）"
        }

        return json.dumps(result, ensure_ascii=False, indent=2)

    except Exception as e:
        logger.error(f"火焰图钻取分析失败: {e}")
        return json.dumps({
            'success': False,
            'error': f'火焰图钻取分析失败: {str(e)}'
        }, ensure_ascii=False, indent=2)


if __name__ == '__main__':
    import asyncio

    # 测试火焰图分析工具
    test_profile_id = "./pilot/data/f162eff6-330b-4388-9a31-bf8777dcbd60.svg"

    print("=== 火焰图CPU性能分析工具测试 ===")

    # 1. 测试概览分析
    print("\n1. 测试火焰图概览:")
    overview_result = asyncio.run(flamegraph_overview(test_profile_id, 5, 50))
    print(overview_result)

    # 2. 测试精确匹配钻取分析
    print("\n2. 测试精确匹配钻取分析 - C2_CompilerThre:")
    drill_down_result = asyncio.run(flamegraph_drill_down(test_profile_id, "C2_CompilerThre", False, 5))
    print(drill_down_result)

    # 3. 测试模糊匹配钻取分析
    print("\n3. 测试模糊匹配钻取分析 - 搜索包含'Compiler'的函数:")
    drill_down_result2 = asyncio.run(flamegraph_drill_down(test_profile_id, "Compiler", True, 5))
    print(drill_down_result2)

    # 4. 测试另一个模糊匹配
    print("\n4. 测试模糊匹配钻取分析 - 搜索包含'Load'的函数:")
    drill_down_result3 = asyncio.run(flamegraph_drill_down(test_profile_id, "Load", True, 5))
    print(drill_down_result3)

    # 5. 测试精确匹配 - LoadNode::Value
    print("\n5. 测试精确匹配钻取分析 - LoadNode::Value:")
    drill_down_result4 = asyncio.run(flamegraph_drill_down(test_profile_id, "LoadNode::Value", False, 5))
    print(drill_down_result4)

    # 6. 测试Java方法的模糊匹配
    print("\n6. 测试模糊匹配钻取分析 - 搜索包含'doIntercept'的函数:")
    drill_down_result5 = asyncio.run(flamegraph_drill_down(test_profile_id, "doIntercept", True, 5))
    print(drill_down_result5)

    print("\n测试完成！")
