"""
SceneSwitchDetector - 场景切换检测器

根据用户输入和会话上下文，判断是否需要切换场景
支持多种检测策略：关键词匹配、语义相似度、LLM 分类

设计原则:
- 多策略融合：结合多种检测方法，提高准确性
- 渐进式检测：优先使用简单快速的方法，复杂方法作为后备
- 可配置：支持调整检测阈值和策略权重
"""

from typing import Optional, Dict, Any, List
import logging
import re
from dataclasses import dataclass
from datetime import datetime

from .scene_definition import (
    SceneDefinition,
    SceneSwitchDecision,
)

logger = logging.getLogger(__name__)


@dataclass
class SessionContext:
    """会话上下文"""

    session_id: str
    conv_id: str
    user_id: Optional[str] = None
    current_scene_id: Optional[str] = None
    message_count: int = 0
    last_user_input: Optional[str] = None
    last_scene_switch_time: Optional[datetime] = None
    scene_history: List[str] = None

    def __post_init__(self):
        if self.scene_history is None:
            self.scene_history = []


@dataclass
class DetectionResult:
    """单个检测策略的结果"""

    scene_id: Optional[str]
    confidence: float
    matched_keywords: List[str]
    reasoning: str
    strategy: str  # "keyword", "semantic", "llm"


class SceneSwitchDetector:
    """
    场景切换检测器

    支持三种检测策略：
    1. 关键词匹配（快速，高准确率）
    2. 语义相似度（中等速度，中等准确率）
    3. LLM 分类（慢速，高准确率）
    """

    def __init__(
        self,
        available_scenes: List[SceneDefinition],
        llm_client: Optional[Any] = None,
        keyword_weight: float = 0.4,
        semantic_weight: float = 0.3,
        llm_weight: float = 0.3,
        confidence_threshold: float = 0.7,
        min_messages_between_switches: int = 2,
    ):
        """
        初始化场景切换检测器

        Args:
            available_scenes: 可用场景列表
            llm_client: LLM 客户端（用于语义分析和 LLM 分类）
            keyword_weight: 关键词匹配权重
            semantic_weight: 语义相似度权重
            llm_weight: LLM 分类权重
            confidence_threshold: 置信度阈值（低于此值不切换）
            min_messages_between_switches: 场景切换之间的最小消息数
        """
        self.available_scenes = available_scenes
        self.llm_client = llm_client

        # 策略权重
        self.keyword_weight = keyword_weight
        self.semantic_weight = semantic_weight
        self.llm_weight = llm_weight

        # 配置
        self.confidence_threshold = confidence_threshold
        self.min_messages_between_switches = min_messages_between_switches

        # 构建关键词索引
        self._keyword_index = self._build_keyword_index()

        logger.info(
            f"[SceneSwitchDetector] Initialized with {len(available_scenes)} scenes, "
            f"threshold={confidence_threshold}"
        )

    def _build_keyword_index(self) -> Dict[str, List[str]]:
        """构建关键词到场景的索引"""
        index = {}

        for scene in self.available_scenes:
            for keyword in scene.trigger_keywords:
                keyword_lower = keyword.lower()
                if keyword_lower not in index:
                    index[keyword_lower] = []
                index[keyword_lower].append(scene.scene_id)

        return index

    async def detect_scene(
        self,
        user_input: str,
        session_context: SessionContext,
    ) -> SceneSwitchDecision:
        """
        检测场景

        Args:
            user_input: 用户输入
            session_context: 会话上下文

        Returns:
            SceneSwitchDecision: 场景切换决策
        """
        # 1. 检查是否允许切换（避免频繁切换）
        if not self._should_check_switch(session_context):
            return SceneSwitchDecision(
                should_switch=False,
                reasoning="Too frequent scene switches or not enough messages",
            )

        # 2. 如果当前没有激活场景，必须选择一个
        if not session_context.current_scene_id:
            decision = await self._select_initial_scene(user_input)
            logger.info(
                f"[SceneSwitchDetector] Initial scene selection: {decision.target_scene}, "
                f"confidence={decision.confidence:.2f}"
            )
            return decision

        # 3. 执行检测
        results = []

        # 策略1: 关键词匹配（快速）
        keyword_result = self._keyword_match(user_input)
        if keyword_result.scene_id:
            results.append(keyword_result)

        # 策略2: 语义相似度（如果有关键词匹配，跳过）
        if not results or results[0].confidence < 0.8:
            semantic_result = await self._semantic_similarity(user_input)
            if semantic_result.scene_id:
                results.append(semantic_result)

        # 策略3: LLM 分类（作为后备）
        if not results or max(r.confidence for r in results) < 0.8:
            llm_result = await self._llm_classify(user_input, session_context)
            if llm_result.scene_id:
                results.append(llm_result)

        # 4. 聚合结果
        if not results:
            return SceneSwitchDecision(
                should_switch=False,
                reasoning="No matching scene found",
            )

        # 选择置信度最高的结果
        best_result = max(results, key=lambda r: r.confidence)

        # 5. 判断是否切换
        should_switch = (
            best_result.confidence >= self.confidence_threshold
            and best_result.scene_id != session_context.current_scene_id
        )

        decision = SceneSwitchDecision(
            should_switch=should_switch,
            target_scene=best_result.scene_id if should_switch else None,
            confidence=best_result.confidence,
            reasoning=best_result.reasoning,
            matched_keywords=best_result.matched_keywords,
        )

        if should_switch:
            logger.info(
                f"[SceneSwitchDetector] Scene switch detected: "
                f"{session_context.current_scene_id} -> {decision.target_scene}, "
                f"confidence={decision.confidence:.2f}, strategy={best_result.strategy}"
            )

        return decision

    def _should_check_switch(self, context: SessionContext) -> bool:
        """检查是否应该检测场景切换"""
        # 如果消息数太少，允许检测
        if context.message_count < self.min_messages_between_switches:
            return True

        # 如果最近刚切换过场景，不检测
        if context.last_scene_switch_time:
            time_since_switch = (
                datetime.now() - context.last_scene_switch_time
            ).total_seconds()
            # 60 秒内不再次检测
            if time_since_switch < 60:
                return False

        return True

    async def _select_initial_scene(self, user_input: str) -> SceneSwitchDecision:
        """选择初始场景"""
        # 使用关键词匹配快速选择
        keyword_result = self._keyword_match(user_input)

        if keyword_result.scene_id and keyword_result.confidence >= 0.5:
            return SceneSwitchDecision(
                should_switch=True,
                target_scene=keyword_result.scene_id,
                confidence=keyword_result.confidence,
                reasoning=f"Initial scene selection by keyword match: {keyword_result.matched_keywords}",
                matched_keywords=keyword_result.matched_keywords,
            )

        # 如果没有匹配，选择优先级最高的默认场景
        if self.available_scenes:
            default_scene = max(self.available_scenes, key=lambda s: s.trigger_priority)
            return SceneSwitchDecision(
                should_switch=True,
                target_scene=default_scene.scene_id,
                confidence=0.6,
                reasoning="Default scene selection (highest priority)",
            )

        return SceneSwitchDecision(
            should_switch=False,
            reasoning="No available scenes",
        )

    def _keyword_match(self, user_input: str) -> DetectionResult:
        """
        关键词匹配检测

        快速但可能不够准确的检测方法
        """
        matched_scenes = {}
        matched_keywords = []

        # 检查用户输入中的关键词
        user_input_lower = user_input.lower()

        for keyword, scene_ids in self._keyword_index.items():
            if keyword in user_input_lower:
                matched_keywords.append(keyword)
                for scene_id in scene_ids:
                    if scene_id not in matched_scenes:
                        matched_scenes[scene_id] = 0
                    matched_scenes[scene_id] += 1

        if not matched_scenes:
            return DetectionResult(
                scene_id=None,
                confidence=0.0,
                matched_keywords=[],
                reasoning="No keyword matched",
                strategy="keyword",
            )

        # 选择匹配关键词最多的场景
        best_scene_id = max(matched_scenes.keys(), key=lambda sid: matched_scenes[sid])
        match_count = matched_scenes[best_scene_id]

        # 计算置信度（基于匹配关键词数量）
        confidence = min(0.9, 0.5 + match_count * 0.1)

        return DetectionResult(
            scene_id=best_scene_id,
            confidence=confidence,
            matched_keywords=matched_keywords,
            reasoning=f"Matched {match_count} keywords: {matched_keywords}",
            strategy="keyword",
        )

    async def _semantic_similarity(self, user_input: str) -> DetectionResult:
        """
        语义相似度检测

        使用向量相似度计算用户输入与场景描述的匹配度
        """
        # TODO: 实现基于 Embedding 的语义相似度计算
        # 当前使用简化版本：检查场景名称和描述中的词汇

        scored_scenes = []

        user_words = set(re.findall(r"\w+", user_input.lower()))

        for scene in self.available_scenes:
            # 提取场景描述中的词汇
            scene_words = set(re.findall(r"\w+", scene.description.lower()))
            scene_words.update(re.findall(r"\w+", scene.scene_name.lower()))

            # 计算重叠度
            overlap = len(user_words & scene_words)
            if overlap > 0:
                similarity = overlap / max(len(user_words), len(scene_words))
                scored_scenes.append((scene.scene_id, similarity))

        if not scored_scenes:
            return DetectionResult(
                scene_id=None,
                confidence=0.0,
                matched_keywords=[],
                reasoning="No semantic match found",
                strategy="semantic",
            )

        # 选择相似度最高的场景
        best_scene_id, best_similarity = max(scored_scenes, key=lambda x: x[1])

        return DetectionResult(
            scene_id=best_scene_id,
            confidence=best_similarity,
            matched_keywords=[],
            reasoning=f"Semantic similarity: {best_similarity:.2f}",
            strategy="semantic",
        )

    async def _llm_classify(
        self,
        user_input: str,
        context: SessionContext,
    ) -> DetectionResult:
        """
        LLM 分类检测

        使用 LLM 判断用户意图属于哪个场景
        """
        if not self.llm_client:
            return DetectionResult(
                scene_id=None,
                confidence=0.0,
                matched_keywords=[],
                reasoning="LLM client not available",
                strategy="llm",
            )

        # TODO: 实现 LLM 分类逻辑
        # 当前返回 None，等待后续实现
        return DetectionResult(
            scene_id=None,
            confidence=0.0,
            matched_keywords=[],
            reasoning="LLM classification not implemented yet",
            strategy="llm",
        )

    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "available_scenes": len(self.available_scenes),
            "keyword_index_size": len(self._keyword_index),
            "confidence_threshold": self.confidence_threshold,
            "weights": {
                "keyword": self.keyword_weight,
                "semantic": self.semantic_weight,
                "llm": self.llm_weight,
            },
        }


# ==================== 导出 ====================

__all__ = [
    "SceneSwitchDetector",
    "SessionContext",
    "DetectionResult",
]
