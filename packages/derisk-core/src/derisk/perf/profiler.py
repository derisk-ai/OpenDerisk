from typing import Optional

from derisk import BaseComponent, SystemApp
from derisk.component import ComponentType

from .periodic_profiler_simple import PeriodicAsyncProfiler


class PerformanceProfiler(BaseComponent):
    name = ComponentType.PERFERMANCE
    profiler: Optional[PeriodicAsyncProfiler] = None

    def init_app(self, system_app: SystemApp):
        if system_app.config.configs.get("app_config").system.enable_performance_sampling:
            # 创建监控器
            self.profiler = PeriodicAsyncProfiler(
                sample_interval=0.05,  # 20Hz采样
                report_every_n_samples=100,  # 每5秒报告,
                blocking_threshold=0.2,  # 门限200 ms
            )

    def after_start(self):
        if self.profiler:
            # 启动监控器
            self.profiler.start_monitoring()

    def before_stop(self):
        if self.profiler:
            # 停止监控器
            self.profiler.stop_monitoring()
