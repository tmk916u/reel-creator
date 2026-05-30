"""連携トークンの暗号化（design D5）。

TOKEN_ENCRYPTION_KEY（Fernet 鍵）が設定されていれば暗号化して保存する。
未設定の場合はローカル開発向けに平文で保存し warning を出す（degraded）。
保存値には "enc:" / "plain:" の接頭辞を付け、鍵の有無が変わっても復号できる。
"""
import logging
import os

from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)

_ENC_PREFIX = "enc:"
_PLAIN_PREFIX = "plain:"
_warned = False


def _get_fernet() -> Fernet | None:
    key = os.getenv("TOKEN_ENCRYPTION_KEY", "").strip()
    if not key:
        return None
    try:
        return Fernet(key.encode())
    except Exception:
        logger.warning("TOKEN_ENCRYPTION_KEY が不正です。平文保存にフォールバックします")
        return None


def encrypt(value: str | None) -> str | None:
    global _warned
    if value is None:
        return None
    f = _get_fernet()
    if f is None:
        if not _warned:
            logger.warning("TOKEN_ENCRYPTION_KEY 未設定: 連携トークンを平文で保存します（本番では設定してください）")
            _warned = True
        return _PLAIN_PREFIX + value
    return _ENC_PREFIX + f.encrypt(value.encode()).decode()


def decrypt(stored: str | None) -> str | None:
    if stored is None:
        return None
    if stored.startswith(_PLAIN_PREFIX):
        return stored[len(_PLAIN_PREFIX):]
    if stored.startswith(_ENC_PREFIX):
        f = _get_fernet()
        if f is None:
            raise RuntimeError("暗号化トークンの復号に TOKEN_ENCRYPTION_KEY が必要です")
        return f.decrypt(stored[len(_ENC_PREFIX):].encode()).decode()
    return stored  # 接頭辞なしの旧値はそのまま
