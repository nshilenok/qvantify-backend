from typing import Optional
from cryptography.fernet import Fernet, InvalidToken
from config import cfg


def _get_share_cipher() -> Optional[Fernet]:
    if not cfg.share_link_enc_key:
        return None
    try:
        return Fernet(cfg.share_link_enc_key.encode("utf-8"))
    except Exception:
        return None


def _encrypt_share_value(value: str) -> Optional[str]:
    cipher = _get_share_cipher()
    if not cipher:
        return None
    return cipher.encrypt(value.encode("utf-8")).decode("utf-8")


def _decrypt_share_value(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    cipher = _get_share_cipher()
    if not cipher:
        return None
    try:
        return cipher.decrypt(value.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        return None
