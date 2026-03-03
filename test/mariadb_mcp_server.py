import os
from configparser import ConfigParser
from pathlib import Path
from typing import Any, Iterable, Optional

import mysql.connector
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("mariadb-mcp")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_db_config() -> dict[str, Any]:
    config_path = os.getenv("MCP_DB_CONFIG", str(_repo_root() / "config.ini"))
    parser = ConfigParser()
    read_ok = parser.read(config_path, encoding="utf-8")
    if not read_ok or not parser.has_section("database"):
        raise RuntimeError(f"Missing [database] section in {config_path}")

    section = parser["database"]
    db_name = os.getenv("MCP_DB_NAME")
    if not db_name:
        db_name = section.get("database_jp") or section.get("database_kr") or section.get("database")

    return {
        "host": os.getenv("MCP_DB_HOST", section.get("host")),
        "port": int(os.getenv("MCP_DB_PORT", section.get("port", "3306"))),
        "user": os.getenv("MCP_DB_USER", section.get("user")),
        "password": os.getenv("MCP_DB_PASSWORD", section.get("password")),
        "database": db_name,
    }


def _connect():
    cfg = _load_db_config()
    if not cfg["database"]:
        raise RuntimeError("No database name configured. Set MCP_DB_NAME or database_* in config.ini.")
    return mysql.connector.connect(
        host=cfg["host"],
        port=cfg["port"],
        user=cfg["user"],
        password=cfg["password"],
        database=cfg["database"],
    )


def _is_select(sql: str) -> bool:
    head = sql.strip().lower()
    return head.startswith("select") or head.startswith("with")


@mcp.tool()
def mariadb_list_tables() -> list[str]:
    """List tables in the configured MariaDB database."""
    with _connect() as conn:
        cur = conn.cursor()
        cur.execute("SHOW TABLES")
        return [row[0] for row in cur.fetchall()]


@mcp.tool()
def mariadb_describe_table(table: str) -> list[dict[str, Any]]:
    """Describe a table's columns."""
    with _connect() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(f"DESCRIBE `{table}`")
        return list(cur.fetchall())


@mcp.tool()
def mariadb_query(sql: str, params: Optional[Iterable[Any]] = None) -> list[dict[str, Any]]:
    """Run a SELECT query and return rows as dicts."""
    if not _is_select(sql):
        raise ValueError("mariadb_query only allows SELECT/CTE statements.")
    with _connect() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(sql, params or ())
        return list(cur.fetchall())


@mcp.tool()
def mariadb_execute(sql: str, params: Optional[Iterable[Any]] = None) -> dict[str, Any]:
    """Run a non-SELECT statement and commit."""
    if _is_select(sql):
        raise ValueError("mariadb_execute does not allow SELECT statements.")
    with _connect() as conn:
        cur = conn.cursor()
        cur.execute(sql, params or ())
        conn.commit()
        return {"rowcount": cur.rowcount}


if __name__ == "__main__":
    mcp.run()
