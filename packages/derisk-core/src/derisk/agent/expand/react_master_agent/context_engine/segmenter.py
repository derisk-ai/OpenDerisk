"""Segmenter —— 按 conv_id 结构化分段。

段 = 一个 conv_id（一个用户轮次）。生产事实：每轮用户输入新建 conv_id
（``{session}_{N}``），ask_user 追问回复也各自新建 conv_id。因此 conv_id 本身
就是确定的轮次边界，**不做语义猜测**。

当前轮 user 单元 = 锚点（逐字）；历史轮 user 单元参与分层（可被压入 cold）。
"""

from typing import List

from .timeline import Segment, Timeline, TimelineUnit


class Segmenter:
    """把全局有序的 Timeline 按 conv_id 切成 Segment 列表。"""

    def segment(self, timeline: Timeline) -> List[Segment]:
        segments: List[Segment] = []
        by_conv = {}

        for unit in timeline.units:
            seg = by_conv.get(unit.conv_id)
            if seg is None:
                seg = Segment(
                    conv_id=unit.conv_id,
                    units=[],
                    first_rounds=unit.rounds,
                    first_created_at=unit.created_at,
                )
                by_conv[unit.conv_id] = seg
                segments.append(seg)
            seg.units.append(unit)

        # 按段首单元的 (rounds, created_at) 排序，保持轮次顺序
        segments.sort(key=lambda s: s.sort_key)

        # 保证 current_conv 段排在最后（锚点轮永远在末尾）
        current = timeline.current_conv_id
        if current:
            cur_segs = [s for s in segments if s.conv_id == current]
            other = [s for s in segments if s.conv_id != current]
            segments = other + cur_segs

        return segments

    @staticmethod
    def flatten(segments: List[Segment]) -> List[TimelineUnit]:
        """把分段重新拍平为全局有序单元列表（oldest -> newest）。"""
        return [u for seg in segments for u in seg.units]
