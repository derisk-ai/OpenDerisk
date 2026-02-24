import socket
from typing import Tuple


def get_local_host() -> Tuple[str, str]:
    """获取本地主机信息"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # 通过连接外部地址获取本机IP
            s.connect(('8.8.8.8', 80))
            ip = s.getsockname()[0]
        finally:
            s.close()
        hostname = socket.gethostname()
        return hostname, ip
    except Exception as e:
        return "unknown_host", "unknown_ip"


ip = ""


def get_host_ip():
    global ip
    if ip:
        return ip
    try:
        # Using host name to get the IP
        _ip = socket.gethostbyname(socket.gethostname())
        if _ip:
            ip = _ip
    except Exception as e:
        pass

    return ip or "error: ip not found"
