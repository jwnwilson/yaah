from typing import Protocol

from cryptography.fernet import Fernet


class Cipher(Protocol):
    def encrypt(self, plaintext: str) -> str: ...
    def decrypt(self, token: str) -> str: ...


class FernetCipher:
    """Symmetric AEAD via Fernet. `key` is a urlsafe-base64 32-byte Fernet key
    (generate with `Fernet.generate_key().decode()`)."""

    def __init__(self, key: str):
        self._f = Fernet(key.encode() if isinstance(key, str) else key)

    def encrypt(self, plaintext: str) -> str:
        return self._f.encrypt(plaintext.encode()).decode()

    def decrypt(self, token: str) -> str:
        return self._f.decrypt(token.encode()).decode()
