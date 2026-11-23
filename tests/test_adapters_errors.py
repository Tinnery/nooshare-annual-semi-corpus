"""异常脱敏单测：第三方异常原文不得进入 RuntimeError 消息。

用假模块替换惰性导入的 psycopg / boto3，不连网络、不使用真实凭据。
"""

import sys
import types

import pytest

from annual_semi_corpus.adapters import fetch_rows, list_published_keys


class _ThirdPartyError(Exception):
    pass


def test_pg_error_hides_original_message(monkeypatch):
    """PG 异常原文（可能含 DSN / 密码）不回显，只保留类型名。"""

    def exploding_connect(*args, **kwargs):
        raise _ThirdPartyError("dsn=postgresql://user:supersecret@host/db token=leakme")

    fake = types.ModuleType("psycopg")
    fake.connect = exploding_connect
    monkeypatch.setitem(sys.modules, "psycopg", fake)

    with pytest.raises(RuntimeError) as caught:
        fetch_rows("postgresql://user:supersecret@host/db", "SELECT 1", [], "ju.pub_date")

    message = str(caught.value)
    assert "supersecret" not in message
    assert "leakme" not in message
    assert "dsn=" not in message
    assert "_ThirdPartyError" in message
    assert "ju.pub_date" in message


def test_rustfs_error_hides_original_message(monkeypatch):
    """S3 异常原文（可能含 endpoint / 请求细节）不回显，只保留类型名。"""

    class ExplodingClient:
        def list_objects_v2(self, **kwargs):
            raise _ThirdPartyError("secret=leakme http://internal-endpoint/signed?x=abc")

    fake_boto3 = types.ModuleType("boto3")
    fake_boto3.client = lambda *args, **kwargs: ExplodingClient()
    fake_config = types.ModuleType("botocore.config")
    fake_config.Config = lambda **kwargs: None
    fake_botocore = types.ModuleType("botocore")
    fake_botocore.config = fake_config
    monkeypatch.setitem(sys.modules, "boto3", fake_boto3)
    monkeypatch.setitem(sys.modules, "botocore", fake_botocore)
    monkeypatch.setitem(sys.modules, "botocore.config", fake_config)

    with pytest.raises(RuntimeError) as caught:
        list_published_keys("http://endpoint", "ak", "sk", "bucket", "published/")

    message = str(caught.value)
    assert "leakme" not in message
    assert "internal-endpoint" not in message
    assert "signed" not in message
    assert "_ThirdPartyError" in message
    assert "bucket=bucket" in message
