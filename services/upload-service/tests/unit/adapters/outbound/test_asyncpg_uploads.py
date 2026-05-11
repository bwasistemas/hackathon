"""Unit tests for upload-service asyncpg adapter."""
import pytest

from app.adapters.outbound.asyncpg_uploads import parse_asyncpg_dsn


def test_parse_asyncpg_dsn_parses_standard_url():
    url = "postgresql+asyncpg://myuser:mypass@db.example.com:5432/mydb"
    out = parse_asyncpg_dsn(url)
    assert out == {
        "host": "db.example.com",
        "port": 5432,
        "user": "myuser",
        "password": "mypass",
        "database": "mydb",
    }


def test_parse_asyncpg_dsn_preserves_colons_in_password():
    url = "postgresql+asyncpg://u:pa:ss@h:5432/db"
    out = parse_asyncpg_dsn(url)
    assert out["user"] == "u"
    assert out["password"] == "pa:ss"
    assert out["host"] == "h"
    assert out["port"] == 5432
    assert out["database"] == "db"


def test_parse_asyncpg_dsn_rejects_invalid_url():
    with pytest.raises(ValueError):
        parse_asyncpg_dsn("invalid://missing")
