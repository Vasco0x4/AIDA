"""Secret crypto round-trip (Fernet, `enc::`-prefixed storage) and masking."""
from utils.crypto import decrypt_secret, encrypt_secret, mask_secret


class TestSecrets:
    def test_roundtrip(self):
        secret = "fake-zhipu-shaped-key.abcdefGH1234"
        stored = encrypt_secret(secret)
        assert stored.startswith("enc::")
        assert stored != secret
        assert decrypt_secret(stored) == secret

    def test_mask_keeps_tail(self):
        assert mask_secret("abcdefgh1234") == "…1234"

    def test_mask_short_secret(self):
        masked = mask_secret("ab")
        assert "ab" not in masked or len(masked) <= 4
