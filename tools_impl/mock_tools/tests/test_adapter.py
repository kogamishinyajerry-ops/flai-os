"""mock_echo 适配器契约测试：正常回显 / 缺字段 failed / 永不抛裸异常。"""

from tools_impl.mock_tools.adapter import run


def test_echo_roundtrip() -> None:
    out = run({"message": {"name": "世界"}})
    assert out["status"] == "success"
    assert out["echoed"] == {"name": "世界"}


def test_missing_message_is_failed_not_exception() -> None:
    out = run({})
    assert out["status"] == "failed"
    assert "message" in out["error_message"]


def test_wrong_type_is_failed() -> None:
    out = run({"message": "不是object"})
    assert out["status"] == "failed"
    assert out["echoed"] == {}
