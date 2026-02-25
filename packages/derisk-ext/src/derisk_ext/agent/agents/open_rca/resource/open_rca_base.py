from enum import Enum
from pathlib import Path


class OpenRcaScene(Enum):
    BANK = "bank"
    TELECOM = "telecom"
    MARKET = "market"


def get_open_rca_data(scene_name: str):
    pass


def check_data_exsit(path: str):
    path_obj = Path(path)

    # 检查路径是否存在
    exists = path_obj.exists()

    # 如果路径不存在，返回 (False, None)
    if not exists:
        return False, None

    # 检查路径是否为空
    if path_obj.is_file():
        # 文件：检查文件大小是否为0
        is_empty = path_obj.stat().st_size == 0
    elif path_obj.is_dir():
        # 目录：检查是否包含任何文件或子目录
        # 使用 any() 避免加载整个目录列表
        is_empty = not any(path_obj.iterdir())
    else:
        # 其他类型（如符号链接、设备文件等）视为非空
        is_empty = False

    return True, is_empty


def get_open_rca_background(scene_name: str):
    scene = OpenRcaScene(scene_name)
    schema = None
    data_path = None
    match scene:
        case OpenRcaScene.BANK:
            from derisk_ext.agent.agents.open_rca.resource.basic_prompt_Bank import (
                schema,
                data_path,
            )

            schema = schema
            data_path = data_path
        case OpenRcaScene.TELECOM:
            from derisk_ext.agent.agents.open_rca.resource.basic_prompt_Telecom import (
                schema,
                data_path,
            )

            schema = schema
            data_path = data_path
        case OpenRcaScene.MARKET:
            from derisk_ext.agent.agents.open_rca.resource.basic_prompt_Market import (
                schema,
                data_path,
            )

            schema = schema
            data_path = data_path
        case _:
            raise ValueError(f"Unknown Scene background {scene_name}! ")

    return schema


def get_open_rca_cand(scene_name: str):
    scene = OpenRcaScene(scene_name)
    match scene:
        case OpenRcaScene.BANK:
            from derisk_ext.agent.agents.open_rca.resource.basic_prompt_Bank import cand

            return cand
        case OpenRcaScene.TELECOM:
            from derisk_ext.agent.agents.open_rca.resource.basic_prompt_Telecom import (
                cand,
            )

            return cand
        case OpenRcaScene.MARKET:
            from derisk_ext.agent.agents.open_rca.resource.basic_prompt_Market import (
                cand,
            )

            return cand
        case _:
            raise ValueError(f"Unknown Scene cand {scene_name}! ")
