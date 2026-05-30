from cryptography.fernet import Fernet

from app.services import crypto


def test_roundtrip_with_key(monkeypatch):
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())
    enc = crypto.encrypt("ya29.secret")
    assert enc.startswith("enc:")
    assert "ya29.secret" not in enc
    assert crypto.decrypt(enc) == "ya29.secret"


def test_roundtrip_without_key(monkeypatch):
    monkeypatch.delenv("TOKEN_ENCRYPTION_KEY", raising=False)
    enc = crypto.encrypt("token")
    assert enc == "plain:token"
    assert crypto.decrypt(enc) == "token"


def test_none_passthrough():
    assert crypto.encrypt(None) is None
    assert crypto.decrypt(None) is None


def test_decrypt_requires_key_for_encrypted(monkeypatch):
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())
    enc = crypto.encrypt("x")
    monkeypatch.delenv("TOKEN_ENCRYPTION_KEY", raising=False)
    try:
        crypto.decrypt(enc)
        assert False, "should raise without key"
    except RuntimeError:
        pass
