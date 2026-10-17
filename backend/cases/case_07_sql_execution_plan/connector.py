"""在线数据库连接（PyMySQL 纯 Python 驱动，无需 JDK）。

仅在 operation="live" 时才导入驱动库，离线分析不依赖它。
连接参数优先级：请求参数 > 环境变量。
db_url 支持 ``host:port/database`` 与 ``jdbc:mysql://host:port/database`` 两种写法。
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

_URL_ENV = "AI_TUTOR_SQLCASE_DB_URL"
_USER_ENV = "AI_TUTOR_SQLCASE_DB_USER"
_PASSWORD_ENV = "AI_TUTOR_SQLCASE_DB_PASSWORD"

_URL_PATTERN = re.compile(
    r"^(?:jdbc:mysql://)?(?P<host>[^:/]+)(?::(?P<port>\d+))?/(?P<database>[^?/]+)"
)


@dataclass(slots=True)
class LiveSettings:
    host: str
    database: str
    user: str
    password: str
    port: int = 3306


def resolve_live_settings(
    url: str | None = None,
    user: str | None = None,
    password: str | None = None,
    **_ignored: object,
) -> LiveSettings | None:
    """合并请求参数与环境变量；任一必填项缺失或 URL 无法解析时返回 None。"""

    raw_url = (url or os.environ.get(_URL_ENV, "")).strip()
    resolved_user = (user or os.environ.get(_USER_ENV, "")).strip()
    resolved_password = password if password is not None else os.environ.get(_PASSWORD_ENV, "")
    if not (raw_url and resolved_user):
        return None

    match = _URL_PATTERN.match(raw_url)
    if not match:
        return None
    return LiveSettings(
        host=match.group("host"),
        port=int(match.group("port") or 3306),
        database=match.group("database"),
        user=resolved_user,
        password=resolved_password,
    )


class LiveConnector:
    """只读连接，用于获取 EXPLAIN 输出与索引采样键。"""

    def __init__(self, settings: LiveSettings) -> None:
        self._settings = settings

    def get_execution_plan(self, sql: str) -> list[str]:
        """执行 EXPLAIN 并把结果行格式化为 `` -> key=value`` 文本。"""

        rows = self._query(f"EXPLAIN {sql}")
        return [
            " -> " + ", ".join(f"{key}={_format_value(value)}" for key, value in row.items())
            for row in rows
        ]

    def get_index_sample_keys(self, table: str, column: str, size: int = 50) -> list:
        """从索引列采样若干键值用于 B+ 树演示。表名/列名做标识符校验防注入。"""

        _validate_identifier(table)
        _validate_identifier(column)
        sql = f"SELECT DISTINCT {column} FROM {table} WHERE {column} IS NOT NULL LIMIT {int(size)}"
        return [row[column] for row in self._query(sql)]

    def _query(self, sql: str) -> list[dict]:
        try:
            import pymysql  # noqa: PLC0415
            import pymysql.cursors  # noqa: PLC0415
        except ImportError as exc:
            raise RuntimeError("实时分析依赖 pymysql，未安装") from exc

        connection = pymysql.connect(
            host=self._settings.host,
            port=self._settings.port,
            database=self._settings.database,
            user=self._settings.user,
            password=self._settings.password,
        )
        try:
            cursor = connection.cursor(pymysql.cursors.DictCursor)
            try:
                cursor.execute(sql)
                return list(cursor.fetchall())
            finally:
                cursor.close()
        finally:
            connection.close()


def _format_value(value: object) -> object:
    return "NULL" if value is None else value


_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")


def _validate_identifier(name: str) -> None:
    if not _IDENTIFIER.match(name):
        raise ValueError(f"非法标识符：{name!r}")
