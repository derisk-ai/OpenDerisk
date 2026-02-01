from derisk.util.logger import setup_logging, LoggingParameters

MCP_LOGGER = setup_logging(
    "mcp",
    LoggingParameters(
        file="mcp.log",
        formatter="%(asctime)s.%(msecs)03d - %(name)s - %(levelname)s - [%(trace_id)s]%(message)s",
    ),
)
CHAT_LOGGER = setup_logging("chat", LoggingParameters(file="chat.log"))
DIGEST_LOGGER = setup_logging("digest-detail", LoggingParameters(file="digest.log", propagate=False))
# # 创建TimedRotatingFileHandler，每天午夜轮转
# handler = TimedRotatingFileHandler(
#     filename=os.path.join(LOGDIR, "mcp.log"),  # 基础日志文件名
#     when="midnight",  # 每天午夜轮转
#     interval=1,  # 间隔1天
#     backupCount=7,  # 保留7天日志
#     encoding="utf-8",  # 编码
#     delay=False,  # 立即写入
#     utc=False,  # 使用本地时间
# )
# # 自定义文件名后缀（格式为yyyymmdd）
# handler.suffix = "%Y%m%d"
# # 更新正则表达式以匹配新后缀格式（确保自动删除旧文件）
# handler.extMatch = re.compile(r"^\d{8}$", re.ASCII)
#
# # 设置日志格式
# file_formatter = logging.Formatter(
#     "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
# )
# handler.setFormatter(file_formatter)
#
# # 添加处理器
# MCP_LOGGER.addHandler(handler)
