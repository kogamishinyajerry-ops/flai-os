"""密码哈希（ADR-0019 D2）：stdlib PBKDF2-HMAC-SHA256。

不引入 bcrypt/argon2——内网离线装包是硬约束（PM-M11 C3），stdlib 零装包风险。
存储格式自描述：`pbkdf2_sha256$<iterations>$<salt_hex>$<hash_hex>`，迭代数
写进记录，将来上调后新旧格式可共存校验。
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

_ALGO = "pbkdf2_sha256"
_ITERATIONS = 600_000  # OWASP 2023 建议值（PBKDF2-SHA256）
_SALT_BYTES = 16
# 存储字段合法边界（Codex R4 审 P2）：损坏/导入的超大 iterations 会让 pbkdf2_hmac
# 抛未捕获 OverflowError 或算数分钟占满校验槽——一条坏记录变成反复 500 或登录
# 服务耗尽。哈希前先拒非法边界，绝不把畸形值喂给 pbkdf2_hmac。
_ITER_MIN, _ITER_MAX = 1_000, 10_000_000
_SALT_HEX_MAX, _HASH_HEX_MAX = 256, 256  # 十六进制字符数上限（宽松但有界）


def hash_password(password: str) -> str:
    if not password:
        raise ValueError("密码不得为空")
    salt = secrets.token_bytes(_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITERATIONS)
    return f"{_ALGO}${_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """校验口径 fail-closed：格式不识别/字段残缺/非法十六进制一律 False，绝不抛错放行。"""
    try:
        algo, iters_s, salt_hex, hash_hex = stored.split("$")
        if algo != _ALGO:
            return False
        # 边界先于哈希（Codex R4 审 P2）：iterations 越界一律拒，绝不喂给
        # pbkdf2_hmac 触发 OverflowError 或分钟级算数；salt/hash 十六进制长度亦有界。
        if len(salt_hex) > _SALT_HEX_MAX or len(hash_hex) > _HASH_HEX_MAX:
            return False
        iterations = int(iters_s)
        if not (_ITER_MIN <= iterations <= _ITER_MAX):
            return False
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except (ValueError, AttributeError, OverflowError):
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(digest, expected)
