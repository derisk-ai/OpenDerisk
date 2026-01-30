def api_key_mist_pwd(key: str) -> str:
    from derisk_ext.ant.utils.mist_utils import get_mist_secret_pwd_v2
    from derisk_ext.ant.utils.mist_utils import get_mist_secret_pwd_v3
    # Theta直接授权给deriskcore的mist key以theta_deriskcore_开头 需要以v3方式取值(直接取)
    # 手动在mist平台配置的key需要以v2方式取值(key需要添加租户/环境)
    pwd = get_mist_secret_pwd_v3(key) if key.startswith("theta_deriskcore_") \
        else get_mist_secret_pwd_v2(key)
    return pwd


def is_mist_api_key(key: str) -> bool:
    """判断是否mist key"""

    # mist key通常是类似theta_deriskcore_xxx、other_manual_xx之类的形式
    # 其明文是Theta key，通常没有下划线
    return key and "_" in key
