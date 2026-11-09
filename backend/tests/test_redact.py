"""
E2 — PII/secret redaction patterns (utils/redact.py).
"""
from utils.redact import redact_obj, redact_text

JWT = ("eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIx"
       "MjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N65IWDJacobN1XHRqAPyKM")


def test_jwt_redacted():
    out = redact_text(f"Authorization: Bearer {JWT}")
    assert JWT not in out
    assert "REDACTED" in out


def test_bearer_shape_redacted():
    out = redact_text("bearer someopaquestringvalue123")
    assert "someopaquestringvalue123" not in out


def test_known_key_shapes():
    assert "sk-abcdefghij1234567890" not in redact_text("key sk-abcdefghij1234567890")
    assert "ghp_" not in redact_text("ghp_" + "a" * 36)
    # Zhipu/GLM style: 32 hex + '.' + 16 alnum (synthetic token, same shape)
    zhipu = "aa1234bb5678cc90dd1122ee334455ff.Xy0987AbCdEfZz12"
    assert zhipu not in redact_text(f"token = {zhipu}")


def test_private_key_block_redacted():
    pem = "-----BEGIN RSA PRIVATE KEY-----\nMIIEow\n-----END RSA PRIVATE KEY-----"
    assert "MIIEow" not in redact_text(pem)


def test_email_keeps_domain():
    out = redact_text("contact john.doe@corp.example about it")
    assert "john.doe" not in out
    assert "@corp.example" in out


def test_ssn_redacted():
    assert "123-45" not in redact_text("ssn 123-45-6789")


def test_luhn_card_redacted_keeps_last4():
    out = redact_text("card 4111111111111111")
    assert "4111111111111111" not in out
    assert "1111" in out  # last 4 kept


def test_non_luhn_digits_untouched():
    # 16 digits that fail Luhn are probably an order/trace id, not a card
    assert redact_text("ref 4111111111111112") == "ref 4111111111111112"


def test_redact_obj_recursive():
    payload = {"token": JWT, "nested": {"keys": ["sk-abcdefghij1234567890"]},
               "n": 5, "ok": "plain text"}
    out = redact_obj(payload)
    assert JWT not in out["token"]
    assert "sk-abcdefghij1234567890" not in out["nested"]["keys"][0]
    assert out["n"] == 5 and out["ok"] == "plain text"


def test_redact_obj_depth_capped():
    deep = cur = {}
    for _ in range(10):
        cur["x"] = {}
        cur = cur["x"]
    cur["leaf"] = "sk-abcdefghij1234567890"
    out = redact_obj(deep)
    node, levels = out, 0
    while isinstance(node, dict):  # walk until the sentinel replaces a subtree
        node = node["x"]
        levels += 1
    assert node == "***MAX_DEPTH***"
    assert levels <= 8  # cap fires at depth > 6
