import asyncio
import concurrent.futures
import logging
import statistics
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
        self.current_samples = []
        self.current_stack_counter = Counter()
        self.blocking_events = []

        # 历史数据
        self.historical_reports = []

        # 事件循环检测
        self.loop = None
        self.last_ping_time = time.time()
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
            time.sleep(sleep_time) # 单独进程 sleep不会阻塞主事件循环

    def _take_sample(self):
        """执行一次采样"""
        current_time = time.time()

        # 1. 检测事件循环阻塞
        self._check_event_loop_blocking(current_time)

        # 2. 采样主线程堆栈
        self._sample_main_thread_stack(current_time)

    def _check_event_loop_blocking(self, current_time):
        """检测事件循环阻塞"""
        try:
            future = asyncio.run_coroutine_threadsafe(
                self._ping_event_loop(self.last_ping_time), self.loop
            )

            ping_response_time = future.result(timeout=self.blocking_threshold)
            delay = ping_response_time - self.last_ping_time

            if delay > self.blocking_threshold:
                main_stack = self._get_main_thread_stack()
                blocking_info = {
                    'timestamp': current_time,
                    'delay': delay,
                    'stack_summary': self._get_stack_summary(main_stack)
                }
                self.blocking_events.append(blocking_info)

                # 立即记录严重阻塞
                if delay > 0.5:  # 超过500ms立即警告
                    logger.warning(f"🚨 严重阻塞检测: {delay:.3f}s - {blocking_info['stack_summary']}")

            self.last_ping_time = ping_response_time


        except (asyncio.TimeoutError, concurrent.futures.TimeoutError, TimeoutError):
            main_stack = self._get_main_thread_stack()
            blocking_info = {
                'timestamp': current_time,
                'delay': f">{self.blocking_threshold}",
                'stack_summary': self._get_stack_summary(main_stack)
            }
            self.blocking_events.append(blocking_info)

            logger.error(f"💥 事件循环严重阻塞: >{self.blocking_threshold}s - {blocking_info['stack_summary']}")
            self.last_ping_time = current_time
        except Exception as e:
            pass

    async def _ping_event_loop(self, timestamp):
        """事件循环ping函数"""
        return timestamp

    def _sample_main_thread_stack(self, current_time):
        """采样主线程堆栈"""
        main_thread = threading.main_thread()
        frame = sys._current_frames().get(main_thread.ident)

        if frame:
            stack = traceback.extract_stack(frame)
            filtered_stack = [
                f for f in stack
                if 'derisk' in f.filename and
                   'derisk-app' not in f.filename and
                   "site-packages" not in f.filename
            ]

            if filtered_stack:
                current_func = filtered_stack[-1]
                func_key = f"{self._get_short_filename(current_func.filename)}:{current_func.lineno}#{current_func.name}"

                self.current_samples.append({
                    'timestamp': current_time,
                    'function': func_key,
                    'full_stack': filtered_stack
                })

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
        for frame in reversed(stack):
            if ('derisk' in frame.filename and
                'site-packages' not in frame.filename and
                'periodic_async_profiler' not in frame.filename):
                relevant_frames.append(f"{self._get_short_filename(frame.filename)}:{frame.lineno}#{frame.name}")
                if len(relevant_frames) >= 4:
                    break

        return " -> ".join(reversed(relevant_frames)) if relevant_frames else "System"

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

        # 基本统计
        self._log_basic_stats()

        # 热点函数分析
        self._log_hotspot_analysis()

        # 阻塞事件分析
        self._log_blocking_analysis()

        # 趋势分析
        if len(self.historical_reports) > 0:
            self._log_trend_analysis()

        # 性能建议
        self._log_recommendations()

        # 保存当前报告
        self._save_current_report()

        logger.info("=" * 60)

    def _log_basic_stats(self):
        """记录基本统计信息"""
        logger.info(f"📈 基本统计:")
        logger.info(f"   └─ 总采样次数: {len(self.current_samples)}")
        logger.info(f"   └─ 阻塞事件数: {len(self.blocking_events)}")

        if self.current_samples:
            sampling_rate = len(self.current_samples) / self.report_every_n_samples * 100
            logger.info(f"   └─ 采样成功率: {sampling_rate:.1f}%")

    def _log_hotspot_analysis(self):
        """记录热点分析"""
        if not self.current_stack_counter:
            logger.info("🔥 热点函数: 无数据")
            return

        logger.info("🔥 热点函数分析 (Top 5):")
        total_samples = len(self.current_samples)

        for i, (func, count) in enumerate(self.current_stack_counter.most_common(5), 1):
            percentage = (count / total_samples) * 100
            estimated_time = count * self.sample_interval

            # 根据占用时间设置不同的日志级别
            if percentage > 50:
                log_func = logger.error
                icon = "🚨"
            elif percentage > 30:
                log_func = logger.warning
                icon = "⚠️"
            else:
                log_func = logger.info
                icon = "📍"

            log_func(f"   {i}. {icon} {percentage:5.1f}% ({estimated_time:.2f}s) - {func}")

    def _log_blocking_analysis(self):
        """记录阻塞分析"""
        if not self.blocking_events:
            logger.info("✅ 阻塞事件: 未检测到阻塞")
            return

        logger.warning(f"⚠️ 阻塞事件分析:")
        logger.warning(f"   └─ 阻塞次数: {len(self.blocking_events)}")

        # 统计阻塞位置和时间
        blocking_locations = Counter()
        numeric_delays = []

        for event in self.blocking_events:
            blocking_locations[event['stack_summary']] += 1
            if isinstance(event['delay'], (int, float)):
                numeric_delays.append(event['delay'])

        if numeric_delays:
            avg_delay = statistics.mean(numeric_delays)
            max_delay = max(numeric_delays)
            total_blocking_time = sum(numeric_delays)

            logger.warning(f"   └─ 平均阻塞时间: {avg_delay:.3f}s")
            logger.warning(f"   └─ 最大阻塞时间: {max_delay:.3f}s")
            logger.warning(f"   └─ 总阻塞时间: {total_blocking_time:.3f}s")

        logger.warning("   └─ 主要阻塞位置:")
        for i, (location, count) in enumerate(blocking_locations.most_common(3), 1):
            logger.warning(f"      {i}. {count}次 - {location}")

    def _log_trend_analysis(self):
        """记录趋势分析"""
        if len(self.historical_reports) < 2:
            return

        logger.info("📈 趋势分析:")

        current_blocking_rate = len(self.blocking_events) / self.report_every_n_samples
        previous_blocking_rate = self.historical_reports[-1]['blocking_rate']

        if current_blocking_rate > previous_blocking_rate * 1.2:
            trend_icon = "📈"
            trend_level = logger.warning
            trend_desc = "恶化"
        elif current_blocking_rate < previous_blocking_rate * 0.8:
            trend_icon = "📉"
            trend_level = logger.info
            trend_desc = "改善"
        else:
            trend_icon = "➡️"
            trend_level = logger.info
            trend_desc = "稳定"

        trend_level(f"   └─ 阻塞率趋势: {trend_icon} {trend_desc} - 当前:{current_blocking_rate:.3f} 上期:{previous_blocking_rate:.3f}")

        # 热点函数变化
        if self.current_stack_counter and self.historical_reports[-1]['top_function']:
            current_top = self.current_stack_counter.most_common(1)[0][0]
            previous_top = self.historical_reports[-1]['top_function']

            if current_top == previous_top:
                logger.info(f"   └─ 热点函数: 🔄 持续 - {current_top}")
            else:
                logger.info(f"   └─ 热点函数: 🔄 变化 - {current_top}")
                logger.debug(f"      (上期: {previous_top})")

    def _log_recommendations(self):
        """记录性能建议"""
        recommendations = []

        # 基于阻塞事件的建议
        blocking_rate = len(self.blocking_events) / self.report_every_n_samples
        if blocking_rate > 0.05:  # 超过5%的采样有阻塞
            recommendations.append(("🚨", "检测到频繁的事件循环阻塞", logger.error))
            recommendations.append(("   →", "检查同步IO操作 (time.sleep, requests等)", logger.error))
            recommendations.append(("   →", "将CPU密集型任务移到executor", logger.error))
        elif blocking_rate > 0.01:  # 超过1%
            recommendations.append(("⚠️", "检测到偶发的事件循环阻塞", logger.warning))
            recommendations.append(("   →", "建议检查可能的同步操作", logger.warning))

        # 基于热点函数的建议
        if self.current_stack_counter:
            top_func, top_count = self.current_stack_counter.most_common(1)[0]
            hotspot_rate = top_count / len(self.current_samples)

            if hotspot_rate > 0.5:  # 超过50%时间在一个函数
                recommendations.append(("🔥", f"函数 {top_func} 占用过多CPU时间 ({hotspot_rate:.1%})", logger.error))
                recommendations.append(("   →", "考虑优化算法或添加异步yield点", logger.error))
            elif hotspot_rate > 0.3:  # 超过30%
                recommendations.append(("🔥", f"函数 {top_func} 是性能热点 ({hotspot_rate:.1%})", logger.warning))
                recommendations.append(("   →", "可以考虑优化该函数", logger.warning))

        if not recommendations:
            recommendations.append(("✅", "当前性能表现良好", logger.info))

        logger.info("💡 性能建议:")
        for icon, message, log_func in recommendations:
            log_func(f"   {icon} {message}")

    def _save_current_report(self):
        """保存当前报告到历史"""
        report_data = {
            'timestamp': time.time(),
            'sample_count': len(self.current_samples),
            'blocking_count': len(self.blocking_events),
            'blocking_rate': len(self.blocking_events) / self.report_every_n_samples if self.report_every_n_samples > 0 else 0,
            'top_function': self.current_stack_counter.most_common(1)[0][0] if self.current_stack_counter else None,
        }

        self.historical_reports.append(report_data)

        # 只保留最近10个报告
        if len(self.historical_reports) > 10:
            self.historical_reports.pop(0)

    def _reset_current_data(self):
        """重置当前周期的数据"""
        self.current_samples.clear()
        self.current_stack_counter.clear()
        self.blocking_events.clear()

    def stop_monitoring(self):
        """停止监控"""
        self.monitoring = False
        logger.info(f"🛑 监控已停止 (总采样: {self.sample_count}次)")

    def get_final_summary(self):
        """获取最终总结并记录到日志"""
        if not self.historical_reports:
            logger.info("📋 监控总结: 没有历史数据")
            return

        total_reports = len(self.historical_reports)
        avg_blocking_rate = statistics.mean([r['blocking_rate'] for r in self.historical_reports])
        total_blocking_events = sum([r['blocking_count'] for r in self.historical_reports])

        logger.info("📋 监控总结:")
        logger.info(f"   └─ 监控周期数: {total_reports}")
        logger.info(f"   └─ 平均阻塞率: {avg_blocking_rate:.3f}")
        logger.info(f"   └─ 总阻塞事件: {total_blocking_events}")
        logger.info(f"   └─ 总采样次数: {self.sample_count}")

