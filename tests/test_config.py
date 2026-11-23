"""配置解析单测：只读写临时 .env，不使用真实凭据或网络。"""

from annual_semi_corpus.config import Settings, load_settings, parse_dotenv


def test_parse_dotenv_ignores_comments_and_quotes(tmp_path):
    dotenv = tmp_path / ".env"
    dotenv.write_text(
        "# comment\n"
        "\n"
        "export DATABASE_URL=postgresql://u@127.0.0.1:5432/db\n"
        'RUSTFS_ENDPOINT_URL="http://s3.internal"\n'
        "BROKEN_LINE_WITHOUT_EQUAL\n"
        "EMPTY=\n",
        encoding="utf-8",
    )
    parsed = parse_dotenv(dotenv)
    assert parsed["DATABASE_URL"] == "postgresql://u@127.0.0.1:5432/db"
    assert parsed["RUSTFS_ENDPOINT_URL"] == "http://s3.internal"
    assert parsed["EMPTY"] == ""
    assert "BROKEN_LINE_WITHOUT_EQUAL" not in parsed


def test_load_settings_precedence_args_env_dotenv_defaults(tmp_path):
    dotenv = tmp_path / ".env"
    dotenv.write_text(
        "DATABASE_URL=from-dotenv\n"
        "RUSTFS_ACCESS_KEY=dotenv-key\n"
        "RUSTFS_SECRET_KEY=dotenv-secret\n"
        "CORPUS_RUSTFS_BUCKET=dotenv-bucket\n",
        encoding="utf-8",
    )
    environ = {"DATABASE_URL": "from-env", "RUSTFS_ACCESS_KEY": "env-key"}

    settings = load_settings(dotenv_path=dotenv, environ=environ, dsn="from-arg")

    assert settings.dsn == "from-arg"
    assert settings.access_key == "env-key"
    assert settings.secret_key == "dotenv-secret"
    assert settings.bucket == "dotenv-bucket"
    assert settings.endpoint == "http://s3.rustfs.pro.neuralj.com"
    assert settings.prefix == "published/"


def test_settings_missing_names_only_field_names():
    settings = Settings(dsn="", endpoint="", access_key="k", secret_key="", bucket="b")
    assert settings.missing() == ("DATABASE_URL", "RUSTFS_ENDPOINT_URL", "RUSTFS_SECRET_KEY")
