import hashlib
import json
import logging
import os
import time
import asyncio
from typing import Dict, Any, Optional, Union, List
from pathlib import Path

from derisk.configs.model_config import DATA_DIR
from derisk.sandbox.base import SandboxBase
from derisk.sandbox.client.file.types import FileInfo

logger = logging.getLogger(__name__)


class FileSystem:
    """
    高并发异步 Agent 文件系统 (Async AFS)
    负责所有的 IO 操作、OSS 模拟、元数据管理。

    1. 异步 I/O：使用 asyncio 全面改造，适应高并发协程环境。
    2. 支持沙箱环境：如果提供了 sandbox，所有文件操作将在沙箱中执行。
    3. 非阻塞文件操作：利用 run_in_executor/to_thread 将磁盘 I/O 放入线程池。
    4. 协程锁：使用 asyncio.Lock 保证元数据读写安全。
    5. 原子写入与路径安全：保留原有的安全机制。
    6. 增加了内存缓存机制 (Hot Cache)
    7. [新增] 增加了内容去重机制 (Content Deduplication)，防止重复存储大文件(SOP)
    """

    def __init__(self, session_id: str, goal_id: str,
                 base_working_dir: str = str(os.path.join(DATA_DIR, "agent_storage")),
                 sandbox: Optional[SandboxBase] = None):
        self.session_id = session_id
        self.goal_id = goal_id
        self.sandbox = sandbox

        # 根据是否使用沙箱选择存储路径
        if self.sandbox:
            # 在沙箱环境中使用虚拟路径
            self.base_path = Path(f"{self.sandbox.work_dir}/{self.session_id}/{self.goal_id}")
        else:
            # 本地文件系统路径
            self.base_path = Path(base_working_dir) / self.session_id / self.goal_id

        self.meta_path = self.base_path / "__file_catalog__.json"

        # 协程锁，保证元数据读写安全
        self._lock = asyncio.Lock()
        self._catalog_cache: Optional[Dict] = None

        # 内存内容缓存 (Hot Cache)
        self._content_cache: Dict[str, str] = {}

        # 哈希索引: content_hash -> file_key
        self._hash_index: Dict[str, str] = {}

    def _ensure_dir(self):
        """确保目录存在（在沙箱中或本地）"""
        if not self.sandbox:
            # 本地文件系统：创建目录
            if not self.base_path.exists():
                self.base_path.mkdir(parents=True, exist_ok=True)

    def _compute_hash(self, data: Union[str, Dict, List]) -> str:
        """计算数据的 MD5 哈希"""
        if isinstance(data, (dict, list)):
            content_str = json.dumps(data, sort_keys=True, ensure_ascii=False)
        else:
            content_str = str(data)
        return hashlib.md5(content_str.encode('utf-8')).hexdigest()

    async def _load_catalog(self) -> Dict:
        """加载元数据（无锁版本，供外部调用）"""
        # 快速路径：如果内存中有，直接返回
        if self._catalog_cache is not None:
            return self._catalog_cache

        # 慢速路径：需要从文件加载
        async with self._lock:
            # 双重检查，防止竞争条件
            if self._catalog_cache is not None:
                return self._catalog_cache

            await self._load_catalog_without_lock()
            return self._catalog_cache

    async def _load_catalog_without_lock(self) -> Dict:
        """内部使用的无锁版本，假设调用者已经持有锁"""
        if self.sandbox:
            # 沙箱环境
            try:
                file_info: FileInfo = await self.sandbox.file.read(str(self.meta_path))
                catalog_content = file_info.content
                if catalog_content:
                    self._catalog_cache = json.loads(catalog_content)
                else:
                    self._catalog_cache = {}
            except Exception:
                logger.error(f"[AFS] Catalog损坏或不存在于沙箱: {self.meta_path}")
                self._catalog_cache = {}
        else:
            # 本地文件系统
            if await asyncio.to_thread(self.meta_path.exists):
                try:
                    def _read():
                        with open(self.meta_path, 'r', encoding='utf-8') as f:
                            return json.load(f)

                    self._catalog_cache = await asyncio.to_thread(_read)
                except Exception:
                    logger.error(f"[AFS] Catalog损坏，重置: {self.meta_path}")
                    self._catalog_cache = {}
            else:
                self._catalog_cache = {}

        # 重建哈希索引
        self._hash_index = {}
        if self._catalog_cache:
            for key, info in self._catalog_cache.items():
                if 'hash' in info:
                    self._hash_index[info['hash']] = key

        return self._catalog_cache

    async def _save_catalog(self):
        """保存元数据（无锁版本，假设调用者已经持有锁）"""
        if self._catalog_cache is None:
            return

        self._ensure_dir()

        if self.sandbox:
            # 沙箱环境：使用沙箱的写入接口
            catalog_content = json.dumps(self._catalog_cache, ensure_ascii=False, indent=2)
            await self.sandbox.file.create(str(self.meta_path), catalog_content)
        else:
            # 本地文件系统
            def _write_atomic():
                temp_path = self.meta_path.with_suffix('.tmp')
                try:
                    with open(temp_path, 'w', encoding='utf-8') as f:
                        json.dump(self._catalog_cache, f, ensure_ascii=False, indent=2)
                        f.flush()
                        os.fsync(f.fileno())
                    temp_path.replace(self.meta_path)
                except Exception as e:
                    if temp_path.exists():
                        temp_path.unlink()
                    raise e

            await asyncio.to_thread(_write_atomic)

    def _sanitize_filename(self, key: str) -> str:
        return "".join([c for c in key if c.isalnum() or c in ('-', '_', '.')])

    async def _oss_upload(self, local_path: Path) -> str:
        """上传文件到OSS"""
        # 检查是否有可用的OSS客户端
        has_oss = self.sandbox and hasattr(self.sandbox.file, 'oss') and self.sandbox.file.oss is not None

        if not has_oss:
            # 如果没有OSS客户端，返回模拟URL
            await asyncio.sleep(0.05)
            return f"local://chat/{self.session_id}/{self.goal_id}/{local_path.name}"

        # 有OSS客户端时的真实上传
        oss_object_name = f"{self.session_id}/{self.goal_id}/{local_path.name}"

        try:
            if self.sandbox:
                # 沙箱环境：需要先将沙箱文件下载到本地临时目录，然后上传到OSS
                # 创建临时目录
                temp_dir = Path("/tmp") / self.session_id / self.goal_id
                await asyncio.to_thread(temp_dir.mkdir, parents=True, exist_ok=True)
                temp_file = temp_dir / local_path.name

                # 从沙箱读取文件内容并写入临时文件
                file_info: FileInfo = await self.sandbox.file.read(str(local_path))
                content = file_info.content
                if content:
                    def _write_temp_file():
                        with open(temp_file, 'w', encoding='utf-8') as f:
                            f.write(content)

                    await asyncio.to_thread(_write_temp_file)

                    # 上传到OSS
                    await asyncio.to_thread(
                        self.sandbox.file.oss.upload_file,
                        str(temp_file),
                        oss_object_name
                    )

                    # 清理临时文件
                    await asyncio.to_thread(temp_file.unlink)

                    return f"oss://{self.sandbox.file.oss.bucket_name}/{oss_object_name}"
                else:
                    logger.error(f"[AFS] 无法从沙箱读取文件: {local_path}")
                    return f"oss://{self.sandbox.file.oss.bucket_name}/{oss_object_name}"

            else:
                # 本地文件系统：直接上传
                await asyncio.to_thread(
                    self.sandbox.file.oss.upload_file,
                    str(local_path),
                    oss_object_name
                )
                return f"oss://{self.sandbox.file.oss.bucket_name}/{oss_object_name}"

        except Exception as e:
            logger.error(f"[AFS] OSS上传失败: {e}")
            # 上传失败时返回模拟URL作为fallback
            return f"local://chat/{self.session_id}/{self.goal_id}/{local_path.name}"

    async def _oss_download(self, oss_url: str, local_path: Path):
        """从OSS下载文件"""
        self._ensure_dir()

        # 检查是否有可用的OSS客户端
        has_oss = self.sandbox and hasattr(self.sandbox.file, 'oss') and self.sandbox.file.oss is not None

        if not has_oss:
            # 如果没有OSS客户端，模拟下载
            await asyncio.sleep(0.05)

            # 本地文件系统
            if not await asyncio.to_thread(local_path.exists):
                if self.sandbox:
                    await self.sandbox.file.create(str(local_path), "")
                else:
                    await asyncio.to_thread(local_path.touch)
            return

        # 有OSS客户端时的真实下载
        try:
            # 从OSS URL解析对象名称
            # oss_url格式: oss://bucket/session_id/filename 或 local://chat/session_id/filename
            if oss_url.startswith(f"oss://{self.sandbox.file.oss.bucket_name}/"):
                oss_object_name = oss_url.replace(f"oss://{self.sandbox.file.oss.bucket_name}/", "")
            elif oss_url.startswith("local://chat/"):
                # 如果是本地URL，不需要下载
                return
            else:
                logger.warning(f"[AFS] 未知的OSS URL格式: {oss_url}")
                return

            if self.sandbox:
                # 沙箱环境：先下载到本地临时文件，然后写入沙箱
                temp_dir = Path("/tmp") / self.session_id / self.goal_id
                await asyncio.to_thread(temp_dir.mkdir, parents=True, exist_ok=True)
                temp_file = temp_dir / local_path.name

                # 下载到临时文件
                await asyncio.to_thread(
                    self.sandbox.file.oss.download_file,
                    oss_object_name,
                    str(temp_file)
                )

                # 读取临时文件内容并写入沙箱
                def _read_temp_file():
                    with open(temp_file, 'r', encoding='utf-8') as f:
                        return f.read()

                content = await asyncio.to_thread(_read_temp_file)
                await self.sandbox.file.create(str(local_path), content)

                # 清理临时文件
                await asyncio.to_thread(temp_file.unlink)

            else:
                # 本地文件系统：直接下载
                await asyncio.to_thread(
                    self.sandbox.file.oss.download_file,
                    oss_object_name,
                    str(local_path)
                )

        except Exception as e:
            logger.error(f"[AFS] OSS下载失败: {e}")
            # 失败时创建空文件
            if self.sandbox:
                await self.sandbox.file.create(str(local_path), "")
            else:
                if not await asyncio.to_thread(local_path.exists):
                    await asyncio.to_thread(local_path.touch)

    async def sync_workspace(self):
        """同步工作区"""
        catalog = await self._load_catalog()
        tasks = []
        for _, info in catalog.items():
            if self.sandbox:
                # 沙箱环境：检查文件是否存在
                try:
                    file_info: FileInfo = await self.sandbox.file.read(info['local_path'])
                    content = file_info.content
                    if content is None:
                        tasks.append(self._oss_download(info['oss_url'], Path(info['local_path'])))
                except Exception:
                    tasks.append(self._oss_download(info['oss_url'], Path(info['local_path'])))
            else:
                # 本地文件系统
                l_path = Path(info['local_path'])
                if not await asyncio.to_thread(l_path.exists):
                    tasks.append(self._oss_download(info['oss_url'], l_path))

        if tasks:
            await asyncio.gather(*tasks)

    async def save_file(self, file_key: str, data: Any, extension: str = "txt", cache_immediately: bool = False) -> str:
        """
        保存文件 (带去重机制)
        支持沙箱环境和本地文件系统
        """
        self._ensure_dir()

        # 使用无锁版本预先加载 catalog
        if self._catalog_cache is None:
            await self._load_catalog()

        # 1. 计算指纹与去重检测
        content_hash = self._compute_hash(data)

        # 检查去重（需要在锁内进行）
        async with self._lock:
            # 使用内部无锁版本加载（如果还没加载）
            if self._catalog_cache is None:
                await self._load_catalog_without_lock()

            # 检查是否有完全相同内容的文件存在
            if content_hash in self._hash_index:
                existing_key = self._hash_index[content_hash]
                if file_key != existing_key:
                    logger.info(
                        f"[AFS] Deduplication: '{file_key}' content matches existing '{existing_key}'. Skipping write.")

                existing_info = self._catalog_cache[existing_key]
                return existing_info['local_path']

        # 2. 如果是新内容，继续正常的保存流程
        if '.' in file_key and len(file_key.split('.')[-1]) <= 4:
            safe_key = self._sanitize_filename(file_key)
        else:
            safe_key = f"{self._sanitize_filename(file_key)}.{extension}"

        local_path = self.base_path / safe_key

        content_str = ""
        if isinstance(data, (dict, list)):
            content_str = json.dumps(data, ensure_ascii=False, indent=2)
        else:
            content_str = str(data)

        if self.sandbox:
            # 沙箱环境：使用沙箱的创建文件接口
            await self.sandbox.file.create(str(local_path), content_str)
        else:
            # 本地文件系统
            def _write_file():
                with open(local_path, 'w', encoding='utf-8') as f:
                    f.write(content_str)

            await asyncio.to_thread(_write_file)

        oss_url = await self._oss_upload(local_path)

        async with self._lock:
            # 再次检查去重（防止竞争条件）
            if content_hash in self._hash_index:
                existing_key = self._hash_index[content_hash]
                existing_info = self._catalog_cache[existing_key]
                # 删除刚创建的文件，因为发现有重复
                if self.sandbox:
                    # 沙箱环境：尝试删除文件
                    try:
                        await self.sandbox.file.remove(path=str(local_path))
                    except Exception:
                        pass
                else:
                    if await asyncio.to_thread(local_path.exists):
                        await asyncio.to_thread(local_path.unlink)
                return existing_info['local_path']

            self._catalog_cache[file_key] = {
                "local_path": str(local_path),
                "filename": safe_key,
                "oss_url": oss_url,
                "timestamp": time.time(),
                "hash": content_hash
            }
            self._hash_index[content_hash] = file_key

            if cache_immediately:
                self._content_cache[file_key] = content_str

            await self._save_catalog()

        return str(local_path)

    async def read_file(self, file_key: str, use_cache: bool = False) -> Optional[str]:
        """读取文件内容 - 修复死锁版本"""
        if use_cache and file_key in self._content_cache:
            return self._content_cache[file_key]

        # 先无锁加载catalog
        catalog = await self._load_catalog()

        # 然后有锁获取文件信息
        async with self._lock:
            info = catalog.get(file_key)

        if not info:
            return None

        if self.sandbox:
            # 沙箱环境：使用沙箱的读取接口
            try:
                file_info: FileInfo = await self.sandbox.file.read(info['local_path'])
                content = file_info.content
                if use_cache and content:
                    self._content_cache[file_key] = content
                return content
            except Exception as e:
                logger.error(f"[AFS] 沙箱读取失败 {file_key}: {e}")
                return None
        else:
            # 本地文件系统
            local_path = Path(info['local_path'])
            if not await asyncio.to_thread(local_path.exists):
                await self._oss_download(info['oss_url'], local_path)

            try:
                def _read():
                    with open(local_path, 'r', encoding='utf-8') as f:
                        return f.read()

                content = await asyncio.to_thread(_read)

                if use_cache and content:
                    self._content_cache[file_key] = content

                return content
            except Exception as e:
                logger.error(f"[AFS] 读取失败 {file_key}: {e}")
                return None

    async def get_file_info(self, file_key: str) -> Optional[Dict]:
        """获取文件信息 - 修复死锁版本"""
        # 先无锁加载catalog
        catalog = await self._load_catalog()

        # 然后有锁获取文件信息
        async with self._lock:
            return catalog.get(file_key)

    async def preload_file(self, file_key: str, content: str):
        """预加载文件到缓存"""
        if not (await self.get_file_info(file_key)):
            await self.save_file(file_key, content, cache_immediately=True)
        else:
            self._content_cache[file_key] = content


# --- 异步使用示例 ---
if __name__ == "__main__":
    async def main():
        # 模拟并发测试
        afs = FileSystem(session_id="async_session_001")

        # 初始化/同步
        await afs.sync_workspace()

        async def worker(idx):
            print(f"Worker {idx} starting...")
            await afs.save_file(f"log_{idx}", f"Async Data from task {idx}")
            print(f"Worker {idx} finished.")

        # 创建 10 个并发任务
        tasks = [worker(i) for i in range(10)]
        start_time = time.time()

        await asyncio.gather(*tasks)

        print(f"并发写入测试完成，耗时: {time.time() - start_time:.2f}秒")

        # 验证读取
        content = await afs.read_file("log_0")
        print(f"读取验证 log_0: {content}")


    # 运行 Event Loop
    asyncio.run(main())
