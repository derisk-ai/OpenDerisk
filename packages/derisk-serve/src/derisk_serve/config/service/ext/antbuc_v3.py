import json
import logging
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, Type
import base64
import datetime
import hmac
import time
import requests
from hashlib import sha256
from collections import OrderedDict
from Crypto.Cipher import PKCS1_v1_5
from Crypto.PublicKey import RSA
import binascii

from derisk import SystemApp
from derisk.util.i18n_utils import _
from derisk_serve.config.service.base_upload import BaseConfigUpdater, UpdaterConfig

logger = logging.getLogger(__name__)


@dataclass
class BucConfig:
    """BUC配置类"""
    buc_url: str
    app_key: str
    secret_key: str
    app_id: str
    pub_key: str

    domain_account: str
    domain_pwd: str
    domain_staff_no: str


@dataclass
class CommonAntAccountConfig(UpdaterConfig):
    """Common Ant Account  configuration"""

    __type__ = "ant_cookie"
    __cfg_type__ = "utils"

    buc_url: Optional[str] = field(
        default=None,
        metadata={"help": _("Ant Buc Server Url")},
    )
    app_key: Optional[str] = field(
        default=None,
        metadata={"help": _("Ant Buc App Key")},
    )

    secret_key: Optional[str] = field(
        default=None,
        metadata={"help": _("Ant Buc Secret Key")},
    )
    app_id: Optional[str] = field(
        default=None,
        metadata={"help": _("Ant Buc App Id")},
    )
    pub_key: Optional[str] = field(
        default=None,
        metadata={"help": _("Ant Buc Pub Key")},
    )
    # domain_account: Optional[str] = field(
    #     default=None,
    #     metadata={"help": _("Ant Buc  common account value")},
    # )
    # domain_pwd: Optional[str] = field(
    #     default=None,
    #     metadata={"help": _("Ant Buc  common account pwd")},
    # )
    # domain_staff_no: Optional[str] = field(
    #     default=None,
    #     metadata={"help": _("Ant Buc  common account staff no")},
    # )



class SignUtils:
    """签名工具类"""

    @staticmethod
    def sign(method, timestamp, uri, nonce, params, app_secret):
        sb = []
        sb.append(method + "\n")
        sb.append(timestamp + "\n")
        sb.append(nonce + "\n")
        sb.append(uri + "\n")

        sign_params = {}
        for key, value in params.items():
            if value is not None and value != "":
                sign_params[key] = [value]

        join_params = SignUtils.join_params(sign_params)
        sb.append(join_params)

        try:
            content = "".join(sb).encode('utf-8')
            key = base64.b64decode(app_secret)
            hmac_obj = hmac.new(key, content, sha256)
            hash_result = SignUtils.byte_array_to_hex_string(hmac_obj.digest())
            signature = base64.b64encode(hash_result.encode('utf-8')).decode('utf-8')
            return signature
        except Exception as err:
            logger.exception(f"签名失败!")
            return ""

    @staticmethod
    def byte_array_to_hex_string(b):
        return ''.join([f'{x:02x}' for x in b])

    @staticmethod
    def join_params(params):
        new_params = OrderedDict(sorted(params.items(), key=lambda x: x[0]))
        for key, values in new_params.items():
            if values is None:
                new_params[key] = [""]
            if len(values) > 1:
                values.sort()

        parts = []
        for key, values in new_params.items():
            for value in values:
                parts.append(f"{key}={value}")

        return "&".join(parts)


class RSAUtils:
    MAX_ENCRYPT_BLOCK = 117

    @staticmethod
    def encrypt_by_public_key(input_str: str, pub_key: str) -> str:
        try:
            # 处理公钥中的下划线
            pub_key = pub_key.replace('_', '/').replace('-', '+')

            # 确保base64字符串长度是4的倍数
            padding = 4 - (len(pub_key) % 4) if len(pub_key) % 4 != 0 else 0
            pub_key = pub_key + "=" * padding

            # 解码base64
            key_der = base64.b64decode(pub_key)

            # 创建RSA密钥对象
            public_key = RSA.importKey(key_der)

            # 创建加密器
            cipher = PKCS1_v1_5.new(public_key)

            # 获取需要加密的字节数据
            data = input_str.encode('utf-8')
            data_length = len(data)

            # 分段加密
            offset = 0
            crypto_bytes = []

            while data_length - offset > 0:
                if data_length - offset > RSAUtils.MAX_ENCRYPT_BLOCK:
                    cache = cipher.encrypt(data[offset:offset + RSAUtils.MAX_ENCRYPT_BLOCK])
                else:
                    cache = cipher.encrypt(data[offset:])
                crypto_bytes.append(cache)
                offset += RSAUtils.MAX_ENCRYPT_BLOCK

            # 将所有加密段拼接
            crypto_data = b''.join(crypto_bytes)

            # 转换为十六进制字符串
            return binascii.hexlify(crypto_data).decode('utf-8').lower()

        except Exception as e:
            raise Exception(f"Encryption error: {str(e)}")


def generate_sdvt(app_id: str, domain_staff_no: str, app_secret: str) -> str:
    """生成SDVT"""

    def java_string_hashcode(s):
        h = 0
        for c in s:
            h = (31 * h + ord(c)) & 0xFFFFFFFF
        return ((h + 0x80000000) & 0xFFFFFFFF) - 0x80000000

    current_time = int(time.time() / 60)

    # 计算第一部分
    app_id_hash = java_string_hashcode(str(app_id))
    first_part = format(app_id_hash & 0xFFFFFFFF, 'x')

    # 计算第二部分
    combined_string = str(app_id) + str(domain_staff_no) + str(app_secret) + str(current_time)
    combined_hash = java_string_hashcode(combined_string)
    second_part = format(combined_hash & 0xFFFFFFFF, 'x')

    return first_part + second_part



class BucClient:
    """BUC客户端类"""

    def __init__(self, config: BucConfig):
        self.config = config

    def login(self, operator: str, target_app: Optional[str] = None,
              goto_url: Optional[str] = None, ) -> Dict[str, Any]:
        """
        标准登录接口
        Args:
            operator: 操作者
            target_app: 目标应用
            goto_url: 目标地址
        Returns:
            登录响应结果
        """
        url = f"{self.config.buc_url}/api/v1/login/sso"

        # 生成登录参数
        payload = {
            "appName": target_app or "deriskcore",
            "gotoUrl": goto_url or "https://derisk.alipay.com",
            "userName": self.config.domain_account,
            "userAgent": f"{self.config.app_id}_auto_login",
            "password": RSAUtils.encrypt_by_public_key(self.config.domain_pwd, self.config.pub_key),
            "clientId": self._get_local_host(),
            "operator": operator,
            "sourceIp": self._get_local_host(),
            "cookieId": self._generate_sdvt(self.config.domain_staff_no)
        }

        # 获取请求头
        headers = self._get_headers("/api/v1/login/sso", payload)

        # 发送请求
        response = requests.post(url, data=payload, headers=headers)
        data = response.json()

        return data

    def get_user(self, staff_no: str) -> Dict[str, Any]:
        """获取用户信息"""
        url = f"{self.config.buc_url}/api/v1/users"
        params = {"staffNo": staff_no}
        headers = self._get_headers("/api/v1/users", params)
        response = requests.get(url, params=params, headers=headers)
        return response.json()

    def get_permission(self, userid: str, permission_code: str) -> Dict[str, Any]:
        """获取权限信息"""
        url = f"{self.config.buc_url}/api/v1/users/permissions"
        params = {
            "permissionCodes": permission_code,
            "userId": userid
        }
        headers = self._get_headers("/api/v1/users/permissions", params)
        response = requests.post(url, data=params, headers=headers)
        return response.json()

    def _get_headers(self, uri: str, params: dict) -> Dict[str, str]:
        """生成请求头"""
        timestamp = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "+0800"
        nonce = str(int(time.time() * 1000)) + "1234"

        return {
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Antbuservice-Api-Timestamp": timestamp,
            "X-Antbuservice-Api-Version": "1.0",
            "X-Antbuservice-Api-Nonce": nonce,
            "X-Antbuservice-Api-Host": self._get_local_host(),
            "X-Antbuservice-Api-App-Id": self.config.app_key,
            "X-Antbuservice-Api-Signature": SignUtils.sign(
                "POST", timestamp, uri, nonce, params, self.config.secret_key
            )
        }

    def _generate_sdvt(self, domain_staff_no: str) -> str:
        """生成SDVT"""
        return generate_sdvt(self.config.app_id, domain_staff_no, self.config.secret_key)

    @staticmethod
    def _get_local_host() -> str:
        """获取本地主机信息"""
        from derisk.util.host_util import get_local_host
        host, ip = get_local_host()
        return f"{host}({ip})"


class AntBucCookieUpdater(BaseConfigUpdater):
    def __init__(self, system_app: SystemApp, config: CommonAntAccountConfig):
        super().__init__(system_app, config)
        self._account_config = config

    @property
    def description(self):
        return "公共账户Cookie配置自动更新器"

    @property
    def account_config(self):
        return self._account_config
    @classmethod
    def config_type(cls) -> str:
        return CommonAntAccountConfig.__type__

    async def get_value(self, **kwargs):

        domain_account = kwargs.get("domain_account", "pub_derisk_test1")
        domain_pwd = kwargs.get("domain_pwd", "${mist:other_manual_deriskcore_domain_pwd1}")
        if domain_pwd and domain_pwd.startswith("${mist:"):
            logger.info(f"antbuc use mist key:{domain_pwd}")
            import re
            from derisk_ext.ant.utils.mist_utils import get_mist_secret_pwd_v2,get_mist_secret_pwd_v3
            match = re.search(r'\$\{mist:([^}]+)}', domain_pwd)
            if match:
                domain_pwd = get_mist_secret_pwd_v3(match.group(1))

        domain_staff_no = kwargs.get("domain_staff_no", "ANT_WORK_122813")

        config = BucConfig(
            buc_url=self.account_config.buc_url,
            app_key=self.account_config.app_key,
            secret_key=self.account_config.secret_key,
            app_id=self.account_config.app_id,
            pub_key=self.account_config.pub_key,
            domain_account=domain_account,
            domain_pwd=domain_pwd,
            domain_staff_no=domain_staff_no,
        )

        # 创建客户端
        client = BucClient(config)
        # 执行登录
        operator = kwargs.get("operator", "derisk")
        target_app = kwargs.get("target_app", "deriskcore")
        goto_url = kwargs.get("goto_url", "https://derisk.alipay.com")
        result = client.login( operator=operator, target_app=target_app, goto_url=goto_url)
        if result.get('success', False):
            return result.get('content')
        else:
            raise ValueError(f"更新Cookie异常!{json.dumps(result, ensure_ascii=False)}")

# 使用示例
def main():
    # 配置信息
    config = BucConfig(
        buc_url="http://antbuservice.stable.alipay.net",
        app_key="deriskcore",
        secret_key="{{mist:other_manual_deriskcore_antbuc_secret_key}}",
        app_id="deriskcore",
        pub_key="MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQCC7_Bml-eeRjW744Q0g7jW4MJ4Qcj4zLVz0pASr2pGivNpTVPrHMWHpBflcMZO4imb1KVdju2ulwCwWzX4ETYUrNx3Zr0BX7CLrkLSpe16nDGZb5VrtiaRogdjzWlDjdj7QdvZZ8w5-VzblSqTLQSQ49ZQmQboQonRsEL43BvI7QIDAQAB",
        domain_account="pub_derisk_test",
        domain_pwd="{{mist:other_manual_deriskcore_domain_pwd}}",
        domain_staff_no="ANT_WORK_122813"
    )


    prod_config = BucConfig(
        buc_url="https://antbuservice-pre.alipay.com",
        app_key="deriskcore",
        secret_key="{{mist:other_manual_deriskcore_antbuc_secret_key}}",
        app_id="deriskcore",
        pub_key="MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQCl7XEdQqCvGsx-rN8yuccN4j0ecsdI5UyoXwPp1wIJa7vwmdu4Fcli5eLwNzszFzeP1mSdy2zN-DJ2vhT46YAPznpNV5-_Y4oA20bncK5xSGpnGDFH60BG2Sr93R5U3glYwbWCPtUE99Q-__CqFLoPkhsWzO8DNpwyPxdx7mpuBwIDAQAB",
        domain_account="pub_derisk_test",
        domain_pwd="&{{mist:other_manual_deriskcore_domain_pwd}}",
        domain_staff_no="ANT_WORK_122813"
    )

    # 创建客户端
    client = BucClient(prod_config)

    # 执行登录
    result = client.login( "tuyang.yhj")
    print(result)


if __name__ == "__main__":
    main()
    print(BucClient._get_local_host())
