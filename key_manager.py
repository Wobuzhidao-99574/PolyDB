import os
import json
from cryptography.fernet import Fernet

KEYS_FILE = ".keys.enc"
MASTER_KEY_ENV = "MASTER_KEY"


def _get_fernet() -> Fernet:
    master_key = os.environ.get(MASTER_KEY_ENV)
    if not master_key:
        raise EnvironmentError("环境变量 MASTER_KEY 未设置")
    return Fernet(master_key.encode())


def generate_master_key() -> str:
    """首次运行，生成主密钥，打印出来后手动写入环境变量"""
    return Fernet.generate_key().decode()


def save_key(name: str, api_key: str) -> None:
    """加密保存一个 API key"""
    f = _get_fernet()
    keys = {}
    if os.path.exists(KEYS_FILE):
        with open(KEYS_FILE, "rb") as fp:
            keys = json.loads(f.decrypt(fp.read()))
    keys[name] = api_key
    with open(KEYS_FILE, "wb") as fp:
        fp.write(f.encrypt(json.dumps(keys).encode()))
    print(f"✅ {name} 已加密保存")


def get_key(name: str) -> str:
    """读取并解密一个 API key"""
    f = _get_fernet()
    if not os.path.exists(KEYS_FILE):
        raise FileNotFoundError(f"{KEYS_FILE} 不存在，请先用 save_key() 存入密钥")
    with open(KEYS_FILE, "rb") as fp:
        keys = json.loads(f.decrypt(fp.read()))
    if name not in keys:
        raise KeyError(f"未找到密钥：{name}")
    return keys[name]
