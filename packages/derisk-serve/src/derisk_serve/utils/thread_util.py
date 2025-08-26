import logging
from threading import Lock
logger = logging.getLogger(__name__)

# 模块级锁和状态变量
lock = Lock()
last_dump_time = None  # 用于保存上一次成功转储的时间


def dump_threads_to_file():

    import datetime
    import faulthandler
    import os
    from derisk.configs.model_config import LOGDIR
    global last_dump_time  # 需要声明 global 以便在函数中修改
    now = datetime.datetime.now()

    with lock:
        try:
            # 检查是否在一小时内已转储过
            if last_dump_time is not None and (now - last_dump_time) < datetime.timedelta(hours=1):
                logger.info("一小时内已转储过线程信息，跳过此次操作。")
                return

            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

            dump_dir = LOGDIR
            os.makedirs(dump_dir, exist_ok=True)
            dump_file = os.path.join(dump_dir, f"thread_dump_{timestamp}.txt")

            # 使用 faulthandler 将当前所有线程的堆栈写入文件
            with open(dump_file, "w", encoding="utf-8") as f:
                faulthandler.dump_traceback(file=f)

            logger.info(f"线程信息已转储至: {dump_file}")
            # 更新最后转储时间
            last_dump_time = now
        except Exception as e:
            logger.error(f"转储线程信息失败: {e}")