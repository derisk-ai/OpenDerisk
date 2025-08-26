from datetime import datetime


def now_ex():
    """ 格式化输出到毫秒"""
    now = datetime.now()
    return now.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]