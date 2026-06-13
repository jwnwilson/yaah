import pytest
from cryptography.fernet import Fernet

from adapters.secrets.cipher import FernetCipher


def test_round_trip():
    key = Fernet.generate_key().decode()
    c = FernetCipher(key)
    token = c.encrypt("s3cret")
    assert token != "s3cret"
    assert c.decrypt(token) == "s3cret"


def test_wrong_key_cannot_decrypt():
    token = FernetCipher(Fernet.generate_key().decode()).encrypt("x")
    with pytest.raises(Exception):
        FernetCipher(Fernet.generate_key().decode()).decrypt(token)
