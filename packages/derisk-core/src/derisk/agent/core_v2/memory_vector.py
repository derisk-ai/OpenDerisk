"""
MemoryVector - 向量检索系统

实现记忆的向量化存储和语义检索
支持多种Embedding模型和向量数据库后端
"""

from typing import List, Optional, Dict, Any, Tuple
from pydantic import BaseModel, Field
from datetime import datetime
from abc import ABC, abstractmethod
import numpy as np
import logging
import uuid

logger = logging.getLogger(__name__)


class VectorDocument(BaseModel):
    """向量文档"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4().hex))
    content: str
    embedding: Optional[List[float]] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    session_id: Optional[str] = None
    message_id: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.now)
    
    importance_score: float = 0.5
    access_count: int = 0


class SearchResult(BaseModel):
    """搜索结果"""
    document: VectorDocument
    score: float
    distance: float


class EmbeddingModel(ABC):
    """Embedding模型基类"""
    
    @abstractmethod
    async def embed(self, text: str) -> List[float]:
        """生成文本嵌入"""
        pass
    
    @abstractmethod
    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """批量生成嵌入"""
        pass
    
    @abstractmethod
    def get_dimension(self) -> int:
        """获取向量维度"""
        pass


class OpenAIEmbedding(EmbeddingModel):
    """OpenAI Embedding"""
    
    def __init__(self, api_key: str, model: str = "text-embedding-3-small"):
        self.api_key = api_key
        self.model = model
        self._client = None
        self._dimensions = {
            "text-embedding-3-small": 1536,
            "text-embedding-3-large": 3072,
            "text-embedding-ada-002": 1536,
        }
    
    async def _ensure_client(self):
        if self._client is None:
            try:
                from openai import AsyncOpenAI
                self._client = AsyncOpenAI(api_key=self.api_key)
            except ImportError:
                raise ImportError("Please install openai: pip install openai")
    
    async def embed(self, text: str) -> List[float]:
        await self._ensure_client()
        
        response = await self._client.embeddings.create(
            model=self.model,
            input=text
        )
        
        return response.data[0].embedding
    
    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        await self._ensure_client()
        
        response = await self._client.embeddings.create(
            model=self.model,
            input=texts
        )
        
        return [d.embedding for d in response.data]
    
    def get_dimension(self) -> int:
        return self._dimensions.get(self.model, 1536)


class SimpleEmbedding(EmbeddingModel):
    """简单Embedding（基于词频，用于测试）"""
    
    def __init__(self, dimension: int = 128):
        self.dimension = dimension
        np.random.seed(42)
        self._word_vectors: Dict[str, np.ndarray] = {}
    
    async def embed(self, text: str) -> List[float]:
        words = text.lower().split()
        
        vector = np.zeros(self.dimension)
        
        for word in words:
            if word not in self._word_vectors:
                self._word_vectors[word] = np.random.randn(self.dimension)
            vector += self._word_vectors[word]
        
        if len(words) > 0:
            vector /= len(words)
        
        vector = vector / (np.linalg.norm(vector) + 1e-8)
        
        return vector.tolist()
    
    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        return [await self.embed(text) for text in texts]
    
    def get_dimension(self) -> int:
        return self.dimension


class VectorStore(ABC):
    """向量存储基类"""
    
    @abstractmethod
    async def add(self, documents: List[VectorDocument]) -> int:
        """添加文档"""
        pass
    
    @abstractmethod
    async def search(
        self,
        query_embedding: List[float],
        top_k: int = 10,
        filter: Optional[Dict[str, Any]] = None
    ) -> List[SearchResult]:
        """搜索相似文档"""
        pass
    
    @abstractmethod
    async def delete(self, ids: List[str]) -> int:
        """删除文档"""
        pass
    
    @abstractmethod
    async def get(self, id: str) -> Optional[VectorDocument]:
        """获取文档"""
        pass
    
    @abstractmethod
    async def count(self) -> int:
        """统计文档数量"""
        pass


class InMemoryVectorStore(VectorStore):
    """内存向量存储"""
    
    def __init__(self):
        self._documents: Dict[str, VectorDocument] = {}
        self._embeddings: Dict[str, np.ndarray] = {}
        self._session_index: Dict[str, List[str]] = {}
    
    async def add(self, documents: List[VectorDocument]) -> int:
        count = 0
        
        for doc in documents:
            if doc.embedding is None:
                continue
            
            self._documents[doc.id] = doc
            self._embeddings[doc.id] = np.array(doc.embedding)
            
            if doc.session_id:
                if doc.session_id not in self._session_index:
                    self._session_index[doc.session_id] = []
                self._session_index[doc.session_id].append(doc.id)
            
            count += 1
        
        return count
    
    async def search(
        self,
        query_embedding: List[float],
        top_k: int = 10,
        filter: Optional[Dict[str, Any]] = None
    ) -> List[SearchResult]:
        if not self._embeddings:
            return []
        
        query_vec = np.array(query_embedding)
        query_vec = query_vec / (np.linalg.norm(query_vec) + 1e-8)
        
        candidates = list(self._documents.keys())
        
        if filter:
            candidates = self._apply_filter(candidates, filter)
        
        similarities = []
        for doc_id in candidates:
            doc_vec = self._embeddings[doc_id]
            
            similarity = np.dot(query_vec, doc_vec)
            distance = 1 - similarity
            
            similarities.append((doc_id, similarity, distance))
        
        similarities.sort(key=lambda x: x[1], reverse=True)
        
        results = []
        for doc_id, similarity, distance in similarities[:top_k]:
            doc = self._documents[doc_id]
            doc.access_count += 1
            
            results.append(SearchResult(
                document=doc,
                score=float(similarity),
                distance=float(distance)
            ))
        
        return results
    
    def _apply_filter(
        self,
        candidates: List[str],
        filter: Dict[str, Any]
    ) -> List[str]:
        filtered = []
        
        for doc_id in candidates:
            doc = self._documents[doc_id]
            match = True
            
            for key, value in filter.items():
                if key == "session_id":
                    match = match and doc.session_id == value
                elif key == "start_time":
                    match = match and doc.timestamp >= value
                elif key == "end_time":
                    match = match and doc.timestamp <= value
                elif key in doc.metadata:
                    match = match and doc.metadata[key] == value
            
            if match:
                filtered.append(doc_id)
        
        return filtered
    
    async def delete(self, ids: List[str]) -> int:
        count = 0
        
        for doc_id in ids:
            if doc_id in self._documents:
                doc = self._documents.pop(doc_id)
                self._embeddings.pop(doc_id, None)
                
                if doc.session_id and doc.session_id in self._session_index:
                    if doc_id in self._session_index[doc.session_id]:
                        self._session_index[doc.session_id].remove(doc_id)
                
                count += 1
        
        return count
    
    async def get(self, id: str) -> Optional[VectorDocument]:
        return self._documents.get(id)
    
    async def count(self) -> int:
        return len(self._documents)
    
    async def get_by_session(self, session_id: str) -> List[VectorDocument]:
        doc_ids = self._session_index.get(session_id, [])
        return [self._documents[doc_id] for doc_id in doc_ids if doc_id in self._documents]


class VectorMemoryStore:
    """
    向量记忆存储
    
    职责:
    1. 记忆向量化存储
    2. 语义相似度检索
    3. 记忆持久化
    4. 多维度查询
    
    示例:
        store = VectorMemoryStore(
            embedding_model=OpenAIEmbedding(api_key="..."),
            vector_store=InMemoryVectorStore()
        )
        
        # 存储记忆
        await store.add_memory(session_id, "用户喜欢Python编程")
        
        # 检索相关记忆
        results = await store.search(session_id, "编程相关", top_k=5)
    """
    
    def __init__(
        self,
        embedding_model: Optional[EmbeddingModel] = None,
        vector_store: Optional[VectorStore] = None,
        auto_embed: bool = True
    ):
        self.embedding_model = embedding_model or SimpleEmbedding()
        self.vector_store = vector_store or InMemoryVectorStore()
        self.auto_embed = auto_embed
    
    async def add_memory(
        self,
        session_id: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        importance_score: float = 0.5,
        message_id: Optional[str] = None
    ) -> VectorDocument:
        """
        添加记忆
        
        Args:
            session_id: 会话ID
            content: 内容
            metadata: 元数据
            importance_score: 重要性分数
            message_id: 源消息ID
            
        Returns:
            VectorDocument: 文档对象
        """
        doc = VectorDocument(
            session_id=session_id,
            content=content,
            metadata=metadata or {},
            importance_score=importance_score,
            message_id=message_id
        )
        
        if self.auto_embed and self.embedding_model:
            doc.embedding = await self.embedding_model.embed(content)
        
        await self.vector_store.add([doc])
        
        logger.debug(f"[VectorMemoryStore] 添加记忆: {doc.id[:8]} - {content[:50]}...")
        return doc
    
    async def add_memories(
        self,
        memories: List[Dict[str, Any]]
    ) -> List[VectorDocument]:
        """批量添加记忆"""
        documents = []
        
        for mem in memories:
            doc = VectorDocument(
                session_id=mem.get("session_id"),
                content=mem.get("content", ""),
                metadata=mem.get("metadata", {}),
                importance_score=mem.get("importance_score", 0.5),
                message_id=mem.get("message_id")
            )
            documents.append(doc)
        
        if self.auto_embed and self.embedding_model:
            contents = [d.content for d in documents]
            embeddings = await self.embedding_model.embed_batch(contents)
            
            for doc, embedding in zip(documents, embeddings):
                doc.embedding = embedding
        
        await self.vector_store.add(documents)
        
        return documents
    
    async def search(
        self,
        query: str,
        top_k: int = 10,
        session_id: Optional[str] = None,
        min_score: float = 0.0,
        filter: Optional[Dict[str, Any]] = None
    ) -> List[SearchResult]:
        """
        搜索相关记忆
        
        Args:
            query: 查询文本
            top_k: 返回数量
            session_id: 会话ID（可选过滤）
            min_score: 最小相似度
            filter: 额外过滤条件
            
        Returns:
            List[SearchResult]: 搜索结果
        """
        query_embedding = await self.embedding_model.embed(query)
        
        search_filter = filter or {}
        if session_id:
            search_filter["session_id"] = session_id
        
        results = await self.vector_store.search(
            query_embedding=query_embedding,
            top_k=top_k * 2,
            filter=search_filter if search_filter else None
        )
        
        filtered_results = [
            r for r in results
            if r.score >= min_score
        ][:top_k]
        
        return filtered_results
    
    async def search_by_embedding(
        self,
        embedding: List[float],
        top_k: int = 10,
        filter: Optional[Dict[str, Any]] = None
    ) -> List[SearchResult]:
        """通过嵌入向量搜索"""
        return await self.vector_store.search(
            query_embedding=embedding,
            top_k=top_k,
            filter=filter
        )
    
    async def get_related_memories(
        self,
        document_id: str,
        top_k: int = 5
    ) -> List[SearchResult]:
        """获取相关记忆"""
        doc = await self.vector_store.get(document_id)
        
        if not doc or not doc.embedding:
            return []
        
        results = await self.vector_store.search(
            query_embedding=doc.embedding,
            top_k=top_k + 1
        )
        
        return [r for r in results if r.document.id != document_id][:top_k]
    
    async def delete_memory(self, document_id: str) -> bool:
        """删除记忆"""
        count = await self.vector_store.delete([document_id])
        return count > 0
    
    async def delete_session_memories(self, session_id: str) -> int:
        """删除会话的所有记忆"""
        if hasattr(self.vector_store, "get_by_session"):
            docs = await self.vector_store.get_by_session(session_id)
            ids = [d.id for d in docs]
            return await self.vector_store.delete(ids)
        return 0
    
    async def get_memory(self, document_id: str) -> Optional[VectorDocument]:
        """获取单个记忆"""
        return await self.vector_store.get(document_id)
    
    async def count_memories(self, session_id: Optional[str] = None) -> int:
        """统计记忆数量"""
        if session_id and hasattr(self.vector_store, "get_by_session"):
            docs = await self.vector_store.get_by_session(session_id)
            return len(docs)
        return await self.vector_store.count()
    
    async def update_importance(
        self,
        document_id: str,
        importance_score: float
    ) -> bool:
        """更新重要性分数"""
        doc = await self.vector_store.get(document_id)
        
        if not doc:
            return False
        
        doc.importance_score = importance_score
        
        return True


class MemoryRetriever:
    """
    记忆检索器
    
    提供高级检索功能
    
    示例:
        retriever = MemoryRetriever(store)
        
        # 混合检索
        results = await retriever.hybrid_search(
            query="Python编程",
            session_id="session-1",
            strategy="semantic_time_decay"
        )
    """
    
    def __init__(self, store: VectorMemoryStore):
        self.store = store
    
    async def semantic_search(
        self,
        query: str,
        top_k: int = 10,
        session_id: Optional[str] = None
    ) -> List[SearchResult]:
        """语义检索"""
        return await self.store.search(query, top_k, session_id)
    
    async def time_decay_search(
        self,
        query: str,
        top_k: int = 10,
        session_id: Optional[str] = None,
        decay_rate: float = 0.1
    ) -> List[SearchResult]:
        """时间衰减检索"""
        results = await self.store.search(query, top_k * 2, session_id)
        
        now = datetime.now()
        
        scored_results = []
        for result in results:
            doc = result.document
            
            age_seconds = (now - doc.timestamp).total_seconds()
            age_days = age_seconds / 86400
            time_score = np.exp(-decay_rate * age_days)
            
            combined_score = (
                0.7 * result.score +
                0.2 * time_score +
                0.1 * doc.importance_score
            )
            
            result.score = combined_score
            scored_results.append(result)
        
        scored_results.sort(key=lambda x: x.score, reverse=True)
        
        return scored_results[:top_k]
    
    async def importance_weighted_search(
        self,
        query: str,
        top_k: int = 10,
        session_id: Optional[str] = None,
        importance_weight: float = 0.3
    ) -> List[SearchResult]:
        """重要性加权检索"""
        results = await self.store.search(query, top_k * 2, session_id)
        
        weighted_results = []
        for result in results:
            doc = result.document
            
            semantic_weight = 1.0 - importance_weight
            combined_score = (
                semantic_weight * result.score +
                importance_weight * doc.importance_score
            )
            
            result.score = combined_score
            weighted_results.append(result)
        
        weighted_results.sort(key=lambda x: x.score, reverse=True)
        
        return weighted_results[:top_k]
    
    async def hybrid_search(
        self,
        query: str,
        top_k: int = 10,
        session_id: Optional[str] = None,
        strategy: str = "semantic_time_decay"
    ) -> List[SearchResult]:
        """混合检索策略"""
        if strategy == "semantic_time_decay":
            return await self.time_decay_search(query, top_k, session_id)
        elif strategy == "importance_weighted":
            return await self.importance_weighted_search(query, top_k, session_id)
        else:
            return await self.semantic_search(query, top_k, session_id)
    
    async def get_context(
        self,
        query: str,
        session_id: str,
        max_tokens: int = 2000
    ) -> str:
        """
        获取相关上下文
        
        Args:
            query: 查询
            session_id: 会话ID
            max_tokens: 最大Token数
            
        Returns:
            str: 组装的相关上下文
        """
        results = await self.hybrid_search(
            query=query,
            session_id=session_id,
            top_k=10
        )
        
        context_parts = []
        current_tokens = 0
        
        for result in results:
            content = result.document.content
            estimated_tokens = len(content) // 4
            
            if current_tokens + estimated_tokens > max_tokens:
                break
            
            context_parts.append(content)
            current_tokens += estimated_tokens
        
        return "\n\n".join(context_parts)


vector_memory_store = VectorMemoryStore()