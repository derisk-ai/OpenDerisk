"""
SimpleMemory - 简化的Memory系统

SQL ite存储，支持Compaction机制
"""

import sqlite3
import json
from typing import List, Dict, Any, Optional
from datetime import datetime
from pathlib import Path


class SimpleMemory:
    """
    简化Memory系统 - SQLite存储

    设计原则:
    1. SQLite本地存储 - ACID保证
    2. Compaction机制 - 上下文压缩
    3. 简单查询 - 快速响应

    示例:
        memory = SimpleMemory("memory.db")

        # 添加消息
        memory.add_message("session-1", "user", "你好")
        memory.add_message("session-1", "assistant", "你好！")

        # 获取历史
        messages = memory.get_messages("session-1")

        # 压缩上下文
        memory.compact("session-1", "对话摘要...")
    """

    def __init__(self, db_path: str = ":memory:"):
        """
        初始化Memory

        Args:
            db_path: 数据库路径，默认内存数据库
        """
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """初始化数据库schema"""
        conn = self._get_connection()

        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                metadata TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 创建索引
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_session_id 
            ON messages(session_id)
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_created_at 
            ON messages(created_at)
        """)

        conn.commit()

    def _get_connection(self) -> sqlite3.Connection:
        """获取数据库连接"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        """
        添加消息

        Args:
            session_id: 会话ID
            role: 角色 (user/assistant/system)
            content: 消息内容
            metadata: 元数据

        Returns:
            int: 消息ID
        """
        conn = self._get_connection()

        cursor = conn.execute(
            "INSERT INTO messages (session_id, role, content, metadata) VALUES (?, ?, ?, ?)",
            (session_id, role, content, json.dumps(metadata) if metadata else None),
        )

        conn.commit()
        message_id = cursor.lastrowid
        conn.close()

        return message_id

    def get_messages(
        self, session_id: str, limit: Optional[int] = None, offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        获取会话消息

        Args:
            session_id: 会话ID
            limit: 限制数量
            offset: 偏移量

        Returns:
            List[Dict]: 消息列表
        """
        conn = self._get_connection()

        query = "SELECT * FROM messages WHERE session_id = ? ORDER BY created_at ASC"
        params = [session_id]

        if limit:
            query += f" LIMIT {limit} OFFSET {offset}"

        cursor = conn.execute(query, params)
        rows = cursor.fetchall()

        messages = []
        for row in rows:
            messages.append(
                {
                    "id": row["id"],
                    "session_id": row["session_id"],
                    "role": row["role"],
                    "content": row["content"],
                    "metadata": json.loads(row["metadata"])
                    if row["metadata"]
                    else None,
                    "created_at": row["created_at"],
                }
            )

        conn.close()
        return messages

    def compact(self, session_id: str, summary: str):
        """
        压缩会话消息 - Compaction机制

        将所有历史消息压缩为一条摘要消息

        Args:
            session_id: 会话ID
            summary: 摘要内容
        """
        conn = self._get_connection()

        # 1. 统计压缩前的消息数
        cursor = conn.execute(
            "SELECT COUNT(*) FROM messages WHERE session_id = ?", (session_id,)
        )
        old_count = cursor.fetchone()[0]

        # 2. 删除旧消息
        conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))

        # 3. 插入摘要
        conn.execute(
            "INSERT INTO messages (session_id, role, content, metadata) VALUES (?, ?, ?, ?)",
            (
                session_id,
                "system",
                summary,
                json.dumps(
                    {
                        "compaction": True,
                        "compacted_messages": old_count,
                        "compacted_at": datetime.now().isoformat(),
                    }
                ),
            ),
        )

        conn.commit()
        conn.close()

    def delete_session(self, session_id: str):
        """删除会话所有消息"""
        conn = self._get_connection()
        conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        conn.commit()
        conn.close()

    def get_session_count(self, session_id: str) -> int:
        """获取会话消息数量"""
        conn = self._get_connection()
        cursor = conn.execute(
            "SELECT COUNT(*) FROM messages WHERE session_id = ?", (session_id,)
        )
        count = cursor.fetchone()[0]
        conn.close()
        return count

    def search_messages(
        self, session_id: str, query: str, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """搜索消息"""
        conn = self._get_connection()

        cursor = conn.execute(
            """
            SELECT * FROM messages 
            WHERE session_id = ? AND content LIKE ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (session_id, f"%{query}%", limit),
        )

        rows = cursor.fetchall()

        messages = []
        for row in rows:
            messages.append(
                {
                    "id": row["id"],
                    "session_id": row["session_id"],
                    "role": row["role"],
                    "content": row["content"],
                    "metadata": json.loads(row["metadata"])
                    if row["metadata"]
                    else None,
                    "created_at": row["created_at"],
                }
            )

        conn.close()
        return messages
