import asyncio
import logging
import logging.handlers
import os
import sys
import threading
import time
from dataclasses import dataclass, field
from logging import Logger
from logging.handlers import TimedRotatingFileHandler
from queue import Queue
from typing import Any, List, Optional, cast

from derisk.configs.model_config import resolve_root_path, LOGDIR
from derisk.util.i18n_utils import _
from derisk.util.parameter_utils import BaseParameters

try:
    from termcolor import colored
except ImportError:

    def colored(x, *args, **kwargs):
        return x


if not os.path.exists(LOGDIR):
    try:
        os.mkdir(LOGDIR)
    except FileExistsError:
        pass

server_error_msg = (
    "**NETWORK ERROR DUE TO HIGH TRAFFIC. PLEASE REGENERATE OR REFRESH THIS PAGE.**"
)


class TraceIdFilter(logging.Filter):
    def filter(self, record):
        if "trace_id" in record.__dict__:
            return True

        from derisk.util.tracer import root_tracer

        trace_id = root_tracer.get_context_trace_id()
        record.trace_id = trace_id if trace_id is not None else ""
        return True


class ConvIdFilter(logging.Filter):
    def filter(self, record):
        if "conv_id" in record.__dict__:
            return True

        from derisk.util.tracer import root_tracer

        conv_id = root_tracer.get_context_conv_id()
        record.conv_id = conv_id if conv_id is not None else ""
        return True


default_handler = None
stdout_handler = None
stderr_handler = None
_locker = threading.RLock()


def _get_logging_level() -> str:
    return os.getenv("DERISK_LOG_LEVEL", "INFO")


@dataclass
class LoggingParameters(BaseParameters):
    """Logging parameters."""

    level: Optional[str] = field(
        default=None,
        metadata={
            "help": _(
                "Logging level, just support FATAL, ERROR, WARNING, INFO, DEBUG, NOTSET"
            ),
            "valid_values": [
                "FATAL",
                "ERROR",
                "WARNING",
                "WARNING",
                "INFO",
                "DEBUG",
                "NOTSET",
            ],
        },
    )
    file: Optional[str] = field(
        default=None,
        metadata={
            "help": _("The filename to store logs"),
        },
    )

    formatter: Optional[str] = field(
        default="%(asctime)s.%(msecs)03d | %(levelname)s | %(name)s | [%(trace_id)s][%(conv_id)s]%(message)s",
        metadata={"help": _("The formatter of log record")},
    )

    propagate: Optional[bool] = field(
        default=False,
        metadata={
            "help": _("Whether to propagate to parent logger"),
        },
    )

    backup_count: Optional[int] = field(
        default=2,
        metadata={
            "help": _("Size of backup log files."),
        },
    )

    when: Optional[str] = field(
        default="midnight",
        metadata={
            "help": _(
                "Log file rollover strategy. S - Seconds, M - Minutes, H - Hours, "
                "D - Days, midnight - roll over at midnight, W{0-6} - roll over on a certain day(0 - Monday)"
            ),
        },
    )

    # redirect_stdio: Optional[bool] = field(
    #     default=False,
    #     metadata={"help": _("Whether to redirect stdio")}
    # )

    def get_real_log_file(self) -> Optional[str]:
        """Get the real log file path.

        It will resolve the root path if the log file is not None.
        """
        if self.file:
            return resolve_root_path(self.file)
        return None


def setup_logging_level(
    logging_level: Optional[str] = None, logger_name: Optional[str] = None
):
    """Setup logging level without using basicConfig to prevent duplicate output."""
    if not logging_level:
        logging_level = _get_logging_level()
    if type(logging_level) is str:
        logging_level = logging.getLevelName(logging_level.upper())
    if logger_name:
        logger = logging.getLogger(logger_name)
        logger.setLevel(cast(str, logging_level))
    else:
        # Set root logger level directly instead of using basicConfig
        # This prevents duplicate handlers from being added
        logging.getLogger().setLevel(cast(str, logging_level))


def setup_logging(
    logger_name: str,
    log_config: Optional[LoggingParameters] = None,
):
    log_config = log_config or LoggingParameters()
    log_config.level = log_config.level or _get_logging_level()

    has_coloredlogs = False
    try:
        import coloredlogs

        has_coloredlogs = True
    except ImportError:
        pass

    logger = _build_logger(logger_name, log_config, skip_stdout=has_coloredlogs)

    # Only install coloredlogs if logger doesn't already have a console handler
    # This prevents duplicate log output when logging.basicConfig was called earlier
    if has_coloredlogs:
        import coloredlogs

        # Check if logger already has handlers that output to console
        has_console_handler = any(
            isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
            for h in logger.handlers
        )

        if not has_console_handler:
            color_level = log_config.level if log_config.level else "INFO"
            coloredlogs.install(level=color_level, logger=logger)
    return logger


def get_gpu_memory(max_gpus=None):
    import torch

    gpu_memory = []
    num_gpus = (
        torch.cuda.device_count()
        if max_gpus is None
        else min(max_gpus, torch.cuda.device_count())
    )
    for gpu_id in range(num_gpus):
        with torch.cuda.device(gpu_id):
            device = torch.cuda.current_device()
            gpu_properties = torch.cuda.get_device_properties(device)
            total_memory = gpu_properties.total_memory / (1024**3)
            allocated_memory = torch.cuda.memory_allocated() / (1024**3)
            available_memory = total_memory - allocated_memory
            gpu_memory.append(available_memory)
    return gpu_memory


def _build_logger(
    logger_name: Optional[str],
    log_config: LoggingParameters,
    skip_stdout: bool = False,
) -> Logger:
    def _build_handler(_config: LoggingParameters) -> logging.Handler:
        # 创建TimedRotatingFileHandler，定时轮转
        _handler = DeRiskTimedRotatingFileHandler(
            filename=os.path.join(
                LOGDIR, _config.file or "derisk_default.log"
            ),  # 日志文件名
            when=log_config.when,  # 日志轮转
            interval=1,  # 间隔1个时间单位
            backupCount=_config.backup_count,  # 保留n份日志
            encoding="utf-8",  # 编码
            delay=False,  # 立即写入
            utc=False,  # 使用本地时间
        )

        # 设置日志格式
        _handler.setFormatter(
            logging.Formatter(fmt=_config.formatter, datefmt="%Y-%m-%d %H:%M:%S")
        )

        _handler.addFilter(TraceIdFilter())
        _handler.addFilter(ConvIdFilter())
        return _handler

    def _get_default_handler() -> logging.Handler:
        global default_handler
        if not default_handler:
            with _locker:
                if not default_handler:
                    default_handler = _build_handler(LoggingParameters())
        return default_handler

    def _get_stdout_handlers() -> list[logging.StreamHandler]:
        global stdout_handler, stderr_handler
        if not stdout_handler:
            with _locker:
                stdout_handler = (
                    stdout_handler
                    if stdout_handler
                    else logging.StreamHandler(sys.stdout)
                )
                stdout_handler.setFormatter(
                    logging.Formatter(
                        fmt=LoggingParameters().formatter, datefmt="%Y-%m-%d %H:%M:%S"
                    )
                )
                stdout_handler.setLevel(_get_logging_level())
        # if not stderr_handler:
        #     with _locker:
        #         stderr_handler = stderr_handler if stderr_handler else logging.StreamHandler(sys.stderr)
        #         stderr_handler.setFormatter(logging.Formatter(fmt=LoggingParameters().formatter, datefmt="%Y-%m-%d %H:%M:%S"))
        #         stderr_handler.setLevel("WARN")
        # return [stdout_handler, stderr_handler]
        return [stdout_handler]

    def _get_handler() -> logging.Handler:
        return _build_handler(log_config) if log_config.file else _get_default_handler()

    if logger_name:
        # 确保root log已初始化
        _build_logger(None, LoggingParameters(), skip_stdout=skip_stdout)

    logger = logging.getLogger(logger_name)
    global default_handler
    if logger.handlers and default_handler:
        # 已经初始化过了
        return logger

    handler = _get_handler()
    with _locker:
        # For root logger, clear any handlers that might have been added by logging.basicConfig
        # This prevents duplicate log output
        if not logger_name:
            # Remove basicConfig handlers (StreamHandler without specific formatter)
            handlers_to_remove = [
                h for h in logger.handlers
                if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
                and not isinstance(h, DeRiskTimedRotatingFileHandler)
            ]
            for h in handlers_to_remove:
                logger.removeHandler(h)

        logger.addHandler(handler)
        logger.setLevel(log_config.level if log_config.level else _get_logging_level())

        # 由于propagate=True，所有日志都会落到root logger中 因此只需root logger输出到stdout中 以免重复
        logger.propagate = log_config.propagate
        if not logger_name and not skip_stdout:  # or log_config.redirect_stdio:
            for hdlr in _get_stdout_handlers():
                logger.addHandler(hdlr)

    # Debugging to print all handlers
    logger.debug(f"Logger {logger_name} handlers: {logger.handlers}")

    return logger


def get_or_create_event_loop() -> asyncio.BaseEventLoop:
    loop = None
    try:
        loop = asyncio.get_event_loop()
        assert loop is not None
        return cast(asyncio.BaseEventLoop, loop)
    except RuntimeError as e:
        if "no running event loop" not in str(e) and "no current event loop" not in str(
            e
        ):
            raise e
        logging.warning("Cant not get running event loop, create new event loop now")
    return cast(asyncio.BaseEventLoop, asyncio.get_event_loop_policy().new_event_loop())


def logging_str_to_uvicorn_level(log_level_str):
    level_str_mapping = {
        "CRITICAL": "critical",
        "ERROR": "error",
        "WARNING": "warning",
        "INFO": "info",
        "DEBUG": "debug",
        "NOTSET": "info",
    }
    return level_str_mapping.get(log_level_str.upper(), "info")


# class EndpointFilter(logging.Filter):
#     """Disable access log on certain endpoint
#
#     source: https://github.com/encode/starlette/issues/864#issuecomment-1254987630
#     """
#
#     def __init__(
#         self,
#         path: str,
#         *args: Any,
#         **kwargs: Any,
#     ):
#         super().__init__(*args, **kwargs)
#         self._path = path
#
#     def filter(self, record: logging.LogRecord) -> bool:
#         return record.getMessage().find(self._path) == -1
#
#
# def setup_http_service_logging(exclude_paths: Optional[List[str]] = None):
#     """Setup http service logging
#
#     Now just disable some logs
#
#     Args:
#         exclude_paths (List[str]): The paths to disable log
#     """
#     if not exclude_paths:
#         # Not show heartbeat log
#         exclude_paths = ["/api/controller/heartbeat", "/api/health"]
#     uvicorn_logger = logging.getLogger("uvicorn.access")
#     if uvicorn_logger:
#         for path in exclude_paths:
#             uvicorn_logger.addFilter(EndpointFilter(path=path))
#     httpx_logger = logging.getLogger("httpx")
#     if httpx_logger:
#         httpx_logger.setLevel(logging.WARNING)


class DeRiskTimedRotatingFileHandler(TimedRotatingFileHandler):
    """优化日志的rotate逻辑 总是在时间单位的整点rotate(eg. 整天/整小时)"""

    def computeRollover(self, currentTime):
        result = super().computeRollover(currentTime)
        if self.when in ("H", "M", "S"):
            _truncate = (result + self.interval) % self.interval
            result = result - _truncate
        return result


class AsyncDigestLogger:
    def __init__(self):
        self.queue = Queue()
        self.running = True
        self.worker_thread = None

    def _ensure_worker(self):
        if self.worker_thread is None:
            self.worker_thread = threading.Thread(target=self._worker, daemon=True)
            self.worker_thread.start()

    def _worker(self):
        batch = []
        last_flush = time.time()

        while self.running:
            try:
                # 批量收集日志，最多等待0.1秒或收集100条
                # while len(batch) < 100 and (time.time() - last_flush) < 0.1:
                while len(batch) < 100:
                    try:
                        item = self.queue.get(timeout=0.01)
                        batch.append(item)
                    except Exception as e:
                        break

                    if (time.time() - last_flush) >= 0.1:
                        break

                if batch:
                    self._flush_batch(batch)
                    batch = []
                    last_flush = time.time()

            except Exception as e:
                # 错误处理
                pass

    def _flush_batch(self, batch):
        for logger, digest_name, extra, items in batch:
            logger.info(
                f"[DIGEST][{digest_name}]"
                + ",".join([f"{key}=[{value}]" for key, value in items.items()]),
                extra=extra,
            )

    def add_log(self, logger, digest_name, extra, **items):
        self._ensure_worker()
        self.queue.put((logger, digest_name, extra, items))


_async_digest_logger = AsyncDigestLogger()


def digest(logger: Optional[Logger], digest_name: str, **items):
    if not logger:
        from .log_util import DIGEST_LOGGER

        logger = DIGEST_LOGGER

    # 异步线程写入日志 需要传递当前trace_id、conv_id
    from derisk.util.tracer import root_tracer

    extra = {
        "trace_id": root_tracer.get_context_trace_id() or "",
        "conv_id": root_tracer.get_context_conv_id() or "",
    }
    if _async_digest_logger:
        _async_digest_logger.add_log(logger, digest_name, extra=extra, **items)
