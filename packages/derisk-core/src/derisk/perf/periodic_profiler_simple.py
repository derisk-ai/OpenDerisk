import asyncio
import concurrent.futures
import sys
import threading
import time
import traceback
from collections import Counter

from derisk.util.logger import setup_logging, LoggingParameters

logger = setup_logging("perf", log_config=LoggingParameters(
    file="perf.log",
    formatter="%(asctime)s.%(msecs)03d %(message)s",
    propagate=False,
))


class PeriodicAsyncProfiler:
    def __init__(self,
                 sample_interval=0.05,
                 report_every_n_samples=100,
                 blocking_threshold=0.1):
        """
        sample_interval: 采样间隔（秒）
        report_every_n_samples: 每N次采样打印一次报告
        blocking_threshold: 性能耗时门限 (秒)
        """
        self.sample_interval = sample_interval
        self.report_every_n_samples = report_every_n_samples

        # 监控状态
        self.monitoring = False
        self.sample_count = 0

        # 数据存储
        self.current_stack_counter = Counter()

        # 事件循环检测
        self.loop = None
        self.blocking_threshold = blocking_threshold

    def start_monitoring(self, loop=None):
        """开始监控"""
        self.loop = loop or asyncio.get_event_loop()
        self.monitoring = True
        self.sample_count = 0

        # 启动监控线程
        monitor_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        monitor_thread.start()

        logger.info("🚀 AsyncIO性能监控已启动")
        logger.info(f"   耗时门限: {self.blocking_threshold}s")
        logger.info(f"   采样间隔: {self.sample_interval}s")
        logger.info(f"   报告频率: 每{self.report_every_n_samples}次采样")
        logger.info(f"   预计报告间隔: {self.sample_interval * self.report_every_n_samples:.1f}s")

    def _monitoring_loop(self):
        """监控主循环"""
        while self.monitoring:
            try:
                start_time = time.time()

                # 执行一次采样
                self._take_sample()
                self.sample_count += 1

                # 检查是否需要打印报告
                if self.sample_count % self.report_every_n_samples == 0:
                    self._log_periodic_report()
                    self._reset_current_data()

                # 控制采样间隔
                elapsed = time.time() - start_time
                sleep_time = max(0, self.sample_interval - elapsed)
                time.sleep(sleep_time)  # 单独进程 sleep不会阻塞主事件循环
            except Exception:
                pass

    def _take_sample(self):
        """执行一次采样"""

        # 1. 检测事件循环阻塞
        self._check_event_loop_blocking()

        # 2. 采样主线程堆栈
        self._sample_main_thread_stack()

    def _check_event_loop_blocking(self):
        """检测事件循环阻塞"""
        try:
            future = asyncio.run_coroutine_threadsafe(
                self._ping_event_loop(), self.loop
            )

            future.result(timeout=self.blocking_threshold)

        except (asyncio.TimeoutError, concurrent.futures.TimeoutError, TimeoutError):
            main_stack = self._get_main_thread_stack()
            stack_summary = self._get_stack_summary(main_stack)
            logger.info("block," + stack_summary + ",")
        except Exception as e:
            pass

    async def _ping_event_loop(self):
        """事件循环ping函数"""
        return None

    def _sample_main_thread_stack(self):
        """采样主线程堆栈"""

        main_stack = self._get_main_thread_stack()
        filtered_stack = [
            f for f in main_stack
            if 'derisk' in f.filename and
               'derisk-app' not in f.filename and
               "site-packages" not in f.filename
        ]

        if filtered_stack:
            current_func = filtered_stack[-1]
            func_key = f"{self._get_short_filename(current_func.filename)}:{current_func.lineno}#{current_func.name}"
            self.current_stack_counter[func_key] += 1

    def _get_main_thread_stack(self):
        """获取主线程堆栈"""
        main_thread = threading.main_thread()
        frame = sys._current_frames().get(main_thread.ident)
        if frame:
            return traceback.extract_stack(frame)
        return []

    def _get_stack_summary(self, stack):
        """获取堆栈摘要"""
        if not stack:
            return "Unknown"

        relevant_frames = []
        tail = None
        for frame in reversed(stack):
            if ('derisk' in frame.filename and
                'site-packages' not in frame.filename and
                'periodic_async_profiler' not in frame.filename):
                name = f"{self._get_short_filename(frame.filename)}:{frame.lineno}#{frame.name}"
                relevant_frames.append(name)
                tail = tail or frame.name
                if len(relevant_frames) >= 4:
                    break
        if not relevant_frames or tail in {"run_uvicorn", "aggregation_chat"}:
            relevant_frames = self._get_stack_frame_all(stack)
        return " -> ".join(reversed(relevant_frames)) if relevant_frames else "System"

    def _get_stack_frame_all(self, stack):
        frames = []
        for frame in reversed(stack):
            name = f"{self._get_short_filename(frame.filename)}:{frame.lineno}#{frame.name}"
            frames.append(name)

            if (('multiprocess.py' in frame.filename) or
                ('derisk' in frame.filename and 'site-packages' not in frame.filename and 'periodic_async_profiler' not in frame.filename)
            ):
                break
        return frames

    def _get_short_filename(self, filepath):
        """获取短文件名"""
        return filepath.split('/')[-1] if '/' in filepath else filepath.split('\\')[-1]

    def _log_periodic_report(self):
        """使用logger输出周期性报告"""
        period_duration = self.sample_interval * self.report_every_n_samples

        # 主报告标题
        logger.info("=" * 60)
        logger.info(f"📊 性能报告 - 过去 {period_duration:.1f}s 的分析结果")
        logger.info("=" * 60)

        # 热点函数分析
        self._log_hotspot_analysis()

        logger.info("=" * 60)

    def _log_hotspot_analysis(self):
        """记录热点分析"""
        if not self.current_stack_counter:
            logger.info("🔥 热点函数: 无数据")
            return

        logger.info("🔥 热点函数分析 (Top 5):")

        for i, (func, count) in enumerate(self.current_stack_counter.most_common(5), 1):
            logger.info(f"hotspot,{count},{func},")

    def _reset_current_data(self):
        """重置当前周期的数据"""
        self.current_stack_counter.clear()

    def stop_monitoring(self):
        """停止监控"""
        self.monitoring = False
        logger.info(f"🛑 监控已停止 (总采样: {self.sample_count}次)")
