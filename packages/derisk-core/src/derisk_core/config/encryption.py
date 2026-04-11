"""加密工具模块 - 提供密钥加密和配置引用解析功能"""

import os
import base64
import hashlib
import logging
from pathlib import Path
from typing import Optional, Any, Dict

from .home import get_derisk_home

logger = logging.getLogger(__name__)

SECRETS_FILE_NAME = "secrets.enc"


class EncryptionError(Exception):
    pass


class SecretsEncryption:
    """密钥加密管理器

    使用 Fernet (AES-128-CBC) 对称加密保护敏感数据。
    主密钥来源优先级：
    1. 环境变量 DERISK_MASTER_KEY
    2. ~/.derisk/master.key 文件
    3. 自动生成并保存到 ~/.derisk/master.key
    """

    _instance = None
    _fernet = None
    _master_key: Optional[str] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._fernet is None:
            self._init_encryption()

    def _init_encryption(self):
        try:
            from cryptography.fernet import Fernet

            self._fernet = Fernet
        except ImportError:
            logger.warning("cryptography not installed, secrets will not be encrypted")
            self._fernet = None

    def _get_master_key_path(self) -> Path:
        return get_derisk_home() / "master.key"

    def _derive_key(self, password: str) -> bytes:
        """从密码派生 Fernet 密钥"""
        if self._fernet is None:
            return password.encode()

        key = hashlib.sha256(password.encode()).digest()
        return base64.urlsafe_b64encode(key)

    def get_master_key(self) -> str:
        """获取主密钥"""
        if self._master_key:
            return self._master_key

        env_key = os.environ.get("DERISK_MASTER_KEY")
        if env_key:
            self._master_key = env_key
            return env_key

        key_path = self._get_master_key_path()
        if key_path.exists():
            self._master_key = key_path.read_text().strip()
            return self._master_key

        if self._fernet:
            new_key = self._fernet.generate_key().decode()
        else:
            import secrets as sec

            new_key = sec.token_hex(32)

        key_path.parent.mkdir(parents=True, exist_ok=True)
        key_path.write_text(new_key)
        key_path.chmod(0o600)

        self._master_key = new_key
        logger.info(f"Generated new master key at {key_path}")
        return new_key

    def set_master_key(self, key: str):
        """设置主密钥"""
        self._master_key = key

    def encrypt(self, plaintext: str) -> str:
        """加密数据"""
        if not plaintext:
            return ""

        if self._fernet is None:
            return f"PLAIN:{plaintext}"

        try:
            key = self._derive_key(self.get_master_key())
            f = self._fernet(key)
            encrypted = f.encrypt(plaintext.encode())
            return f"ENC:{encrypted.decode()}"
        except Exception as e:
            raise EncryptionError(f"Encryption failed: {e}")

    def decrypt(self, ciphertext: str) -> str:
        """解密数据"""
        if not ciphertext:
            return ""

        if ciphertext.startswith("PLAIN:"):
            return ciphertext[6:]

        if not ciphertext.startswith("ENC:"):
            return ciphertext

        if self._fernet is None:
            return ciphertext[4:] if ciphertext.startswith("ENC:") else ciphertext

        try:
            key = self._derive_key(self.get_master_key())
            f = self._fernet(key)
            encrypted = ciphertext[4:].encode()
            decrypted = f.decrypt(encrypted).decode()
            logger.debug(f"Successfully decrypted data, length={len(decrypted)}")
            return decrypted
        except Exception as e:
            logger.error(f"Decryption failed: {e}, ciphertext_prefix={ciphertext[:20] if ciphertext else 'empty'}...")
            # 返回空字符串表示解密失败
            return ""


_secrets_cache: Dict[str, str] = {}


def get_secrets_file_path() -> Path:
    return get_derisk_home() / SECRETS_FILE_NAME


def load_secrets() -> Dict[str, str]:
    """从加密文件加载密钥"""
    global _secrets_cache

    if _secrets_cache:
        return _secrets_cache

    secrets_file = get_secrets_file_path()
    if not secrets_file.exists():
        return {}

    try:
        encryption = SecretsEncryption()
        content = secrets_file.read_text()

        import json

        data = json.loads(content)

        _secrets_cache = {}
        for name, encrypted_value in data.items():
            if encrypted_value:
                decrypted = encryption.decrypt(encrypted_value)
                if decrypted:
                    _secrets_cache[name] = decrypted

        return _secrets_cache
    except Exception as e:
        logger.error(f"Failed to load secrets: {e}")
        return {}


def save_secrets(secrets: Dict[str, str]) -> bool:
    """保存密钥到加密文件"""
    global _secrets_cache

    try:
        encryption = SecretsEncryption()

        data = {}
        for name, value in secrets.items():
            if value:
                data[name] = encryption.encrypt(value)

        secrets_file = get_secrets_file_path()
        secrets_file.parent.mkdir(parents=True, exist_ok=True)

        import json

        secrets_file.write_text(json.dumps(data, indent=2))
        secrets_file.chmod(0o600)

        _secrets_cache = secrets.copy()
        logger.info(f"Saved {len(secrets)} secrets to {secrets_file}")
        return True
    except Exception as e:
        logger.error(f"Failed to save secrets: {e}")
        return False


def get_secret(name: str) -> Optional[str]:
    """获取单个密钥值"""
    secrets = load_secrets()
    return secrets.get(name)


def set_secret(name: str, value: str) -> bool:
    """设置单个密钥"""
    secrets = load_secrets()
    secrets[name] = value
    return save_secrets(secrets)


def delete_secret(name: str) -> bool:
    """删除单个密钥"""
    secrets = load_secrets()
    if name in secrets:
        del secrets[name]
        return save_secrets(secrets)
    return True


def list_secrets() -> Dict[str, bool]:
    """列出所有密钥（只返回是否存在，不返回值）"""
    secrets = load_secrets()
    return {name: bool(value) for name, value in secrets.items()}


class ConfigReferenceResolver:
    """配置引用解析器

    支持的引用语法：
    - ${secrets.key_name} - 引用加密存储的密钥
    - ${env:ENV_VAR_NAME} - 引用环境变量
    - ${env:ENV_VAR_NAME:-default} - 引用环境变量，带默认值
    """

    SECRET_PATTERN = "${secrets."
    ENV_PATTERN = "${env:"

    @classmethod
    def resolve(cls, value: Any, secrets: Optional[Dict[str, str]] = None) -> Any:
        """解析配置值中的引用"""
        if value is None:
            return None

        if isinstance(value, str):
            return cls._resolve_string(value, secrets)
        elif isinstance(value, dict):
            return {k: cls.resolve(v, secrets) for k, v in value.items()}
        elif isinstance(value, list):
            return [cls.resolve(item, secrets) for item in value]
        else:
            return value

    @classmethod
    def _resolve_string(cls, s: str, secrets: Optional[Dict[str, str]] = None) -> str:
        """解析字符串中的引用"""
        if not s:
            return s

        result = s

        if cls.SECRET_PATTERN in result:
            if secrets is None:
                secrets = load_secrets()

            import re

            pattern = r"\$\{secrets\.([a-zA-Z0-9_]+)\}"

            def replace_secret(match):
                secret_name = match.group(1)
                secret_value = secrets.get(secret_name)
                if secret_value:
                    return secret_value
                logger.warning(f"Secret '{secret_name}' not found")
                return ""

            result = re.sub(pattern, replace_secret, result)

        if cls.ENV_PATTERN in result:
            import re

            pattern = r"\$\{env:([a-zA-Z0-9_]+)(?::-([^}]*))?\}"

            def replace_env(match):
                env_name = match.group(1)
                default_value = match.group(2)
                env_value = os.environ.get(env_name)
                if env_value:
                    return env_value
                if default_value is not None:
                    return default_value
                logger.warning(f"Environment variable '{env_name}' not found")
                return ""

            result = re.sub(pattern, replace_env, result)

        return result

    @classmethod
    def resolve_config(cls, config: Dict[str, Any]) -> Dict[str, Any]:
        """解析整个配置字典中的引用"""
        secrets = load_secrets()
        return cls.resolve(config, secrets)


def mask_secrets_in_json(
    config: Dict[str, Any], secrets: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """在配置中隐藏密钥值（用于导出）"""
    if secrets is None:
        secrets = load_secrets()

    def mask_value(v: Any) -> Any:
        if isinstance(v, str):
            for secret_name, secret_value in secrets.items():
                if secret_value and secret_value in v:
                    v = v.replace(secret_value, f"${{secrets.{secret_name}}}")
            return v
        elif isinstance(v, dict):
            return {k: mask_value(val) for k, val in v.items()}
        elif isinstance(v, list):
            return [mask_value(item) for item in v]
        return v

    return mask_value(config)
