import logging
import os
from logging.handlers import TimedRotatingFileHandler
import re
from derisk.configs.model_config import LOGDIR

MCP_LOGGER = logging.getLogger("mcp")

if not os.path.exists(LOGDIR):
    os.mkdir(LOGDIR)
    
# 创建TimedRotatingFileHandler，每天午夜轮转
handler = TimedRotatingFileHandler(
    filename=os.path.join(LOGDIR, "mcp.log"),  # 基础日志文件名
    when="midnight",  # 每天午夜轮转
    interval=1,  # 间隔1天
    backupCount=7,  # 保留7天日志
    encoding="utf-8",  # 编码
    delay=False,  # 立即写入
    utc=False,  # 使用本地时间
)
# 自定义文件名后缀（格式为yyyymmdd）
handler.suffix = "%Y%m%d"
# 更新正则表达式以匹配新后缀格式（确保自动删除旧文件）
handler.extMatch = re.compile(r"^\d{8}$", re.ASCII)

# 设置日志格式
file_formatter = logging.Formatter(
    "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
handler.setFormatter(file_formatter)

# 添加处理器
MCP_LOGGER.addHandler(handler)
