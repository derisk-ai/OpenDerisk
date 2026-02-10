import json
import logging
import os
import time
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)
class AgentFileSystem:
    """
    通用 Agent 文件系统 (AFS)
    功能：透明地管理本地文件与远端 OSS 存储的同步。
    适用场景：对话恢复、多 Agent 协作、大数据持久化。
    """

    def __init__(self, conv_id: str, base_working_dir: str = "agent_storage"):
        self.conv_id = conv_id
        # 为每个会话创建独立的隔离目录
        self.local_dir = os.path.join(base_working_dir, conv_id)
        self.meta_path = os.path.join(self.local_dir, "__file_catalog__.json")

        if not os.path.exists(self.local_dir):
            os.makedirs(self.local_dir)

        self.catalog = self._load_catalog()

    def _load_catalog(self) -> Dict:
        if os.path.exists(self.meta_path):
            with open(self.meta_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}

    def _save_catalog(self):
        with open(self.meta_path, 'w', encoding='utf-8') as f:
            json.dump(self.catalog, f, ensure_ascii=False, indent=2)

    def _mock_oss_upload(self, local_path: str) -> str:
        """模拟将文件推送到远程 OSS"""
        file_name = os.path.basename(local_path)
        return f"oss://bucket-name/{self.conv_id}/{file_name}"

    def _mock_oss_download(self, oss_url: str, local_path: str):
        """模拟从远程 OSS 拉取文件"""
        logger.info(f"[AFS] 从远程恢复: {oss_url} -> {local_path}")
        # 实际生产中这里是真实的下载逻辑
        if not os.path.exists(os.path.dirname(local_path)):
            os.makedirs(os.path.dirname(local_path))
        with open(local_path, 'w', encoding='utf-8') as f:
            f.write(f"这是从 {oss_url} 恢复的内容")

    def sync_workspace(self):
        """
        初始化/追问时调用：确保 Catalog 中的所有文件在本地物理存在。
        """
        recovered_count = 0
        for file_key, info in self.catalog.items():
            l_path = info['local_path']
            if not os.path.exists(l_path):
                self._mock_oss_download(info['oss_url'], l_path)
                recovered_count += 1
        if recovered_count > 0:
            logger.info(f"[AFS] 会话 {self.conv_id} 环境恢复完成，共恢复 {recovered_count} 个文件。")

    def save_file(self, file_key: str, data: Any, extension: str = "log") -> str:
        """
        核心方法：保存任意数据。
        如果是 Agent 产生的中间文件（如生成的代码、采集的日志），调用此方法。
        """
        filename = f"{file_key}_{int(time.time() * 1000)}.{extension}"
        local_path = os.path.join(self.local_dir, filename)

        # 写入本地文件系统
        with open(local_path, 'w', encoding='utf-8') as f:
            if isinstance(data, (dict, list)):
                json.dump(data, f, ensure_ascii=False, indent=2)
            else:
                f.write(str(data))

        # 同步到远程存储
        oss_url = self._mock_oss_upload(local_path)

        # 记录元数据
        self.catalog[file_key] = {
            "local_path": local_path,
            "oss_url": oss_url,
            "size": os.path.getsize(local_path),
            "timestamp": time.time()
        }
        self._save_catalog()
        return local_path

    def read_file(self, file_key: str) -> Optional[str]:
        """
        核心方法：读取文件内容。
        透明处理：如果本地没有，先从云端拉取。
        """
        info = self.catalog.get(file_key)
        if not info:
            return None

        local_path = info['local_path']
        if not os.path.exists(local_path):
            self._mock_oss_download(info['oss_url'], local_path)

        with open(local_path, 'r', encoding='utf-8') as f:
            return f.read()