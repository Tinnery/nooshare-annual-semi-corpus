"""Runtime configuration for the corpus CLI.

Responsibility: resolve check-command settings from explicit arguments, process
environment and an optional .env file. This Unit owns no network IO and never
logs or returns secret values in error messages.

Contract:
- inputs: optional explicit overrides, environ mapping, .env path
- outputs: frozen Settings; Settings.missing() names empty required fields
- dependencies: os.environ (read-only), filesystem (.env read-only)
- side effects: none
- failures: unreadable/malformed .env lines are ignored; required values are
  reported as empty strings for the CLI to reject with a clear message
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

DEFAULT_DOTENV = ".env"
DEFAULT_ENDPOINT = "http://s3.rustfs.pro.neuralj.com"
DEFAULT_BUCKET = "nooshare-dev"
DEFAULT_PREFIX = "published/"


@dataclass(frozen=True)
class Settings:
    """Resolved runtime configuration. Secret fields are carried but never echoed."""

    dsn: str
    endpoint: str
    access_key: str
    secret_key: str
    bucket: str
    prefix: str = DEFAULT_PREFIX

    def missing(self) -> tuple[str, ...]:
        """Return names of required settings that are empty."""
        absent: list[str] = []
        if not self.dsn:
            absent.append("DATABASE_URL")
        if not self.endpoint:
            absent.append("RUSTFS_ENDPOINT_URL")
        if not self.access_key:
            absent.append("RUSTFS_ACCESS_KEY")
        if not self.secret_key:
            absent.append("RUSTFS_SECRET_KEY")
        return tuple(absent)


def parse_dotenv(path: str | Path) -> dict[str, str]:
    """Parse KEY=VALUE lines from a .env file.

    Ignores blank lines, comments, optional ``export `` prefix and lines
    without ``=``. Quotes around values are stripped. Returns a plain mapping;
    callers decide precedence.
    """
    values: dict[str, str] = {}
    source = Path(path)
    if not source.is_file():
        return values
    for raw in source.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def load_settings(
    *,
    dotenv_path: str | Path = DEFAULT_DOTENV,
    environ: dict[str, str] | None = None,
    dsn: Optional[str] = None,
    endpoint: Optional[str] = None,
    bucket: Optional[str] = None,
    prefix: Optional[str] = None,
) -> Settings:
    """Resolve settings with precedence: explicit args > env > .env > defaults.

    Does not raise on missing values; use ``Settings.missing()`` for diagnostics
    so the CLI can produce one clear error without exposing secrets.
    """
    env = environ if environ is not None else dict(os.environ)
    file_values = parse_dotenv(dotenv_path)

    def pick(name: str, default: str = "") -> str:
        value = env.get(name)
        if value:
            return value
        return file_values.get(name, default)

    return Settings(
        dsn=dsn or pick("DATABASE_URL"),
        endpoint=endpoint or pick("RUSTFS_ENDPOINT_URL", DEFAULT_ENDPOINT),
        access_key=pick("RUSTFS_ACCESS_KEY"),
        secret_key=pick("RUSTFS_SECRET_KEY"),
        bucket=bucket or pick("CORPUS_RUSTFS_BUCKET", DEFAULT_BUCKET),
        prefix=prefix or pick("CORPUS_PREFIX", DEFAULT_PREFIX),
    )
