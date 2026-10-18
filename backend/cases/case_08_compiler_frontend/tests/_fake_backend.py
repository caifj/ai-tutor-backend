# -*- coding: utf-8 -*-
"""离线测试用的「假后端」：按 ai_tutor_backend/models.py 的真实规则做校验。

它不是官方实现，只复刻了会影响本案例的约束：

* ``Dataset``：列 key 唯一；每行的未知列、缺失必填列、值类型都必须过关；
* ``ResultPayload``：数据集名称唯一；
* ``CaseDescriptor``：``case_id`` 必须匹配 ``^[a-z0-9][a-z0-9._-]*$``；
  ``catalog_visible=True`` 时必须提供 ``course_number``；
* ``Diagnostic``：``code`` 与 ``message`` 非空，``level`` 只能是 info/warning/error。

因此本文件能让映射逻辑在没有 pydantic 的机器上被验证。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class DataType(str, Enum):
    """与真实 models.py 一样是 StrEnum，因此 ``DataType("integer")`` 可用。"""

    STRING = "string"
    INTEGER = "integer"
    NUMBER = "number"
    BOOLEAN = "boolean"
    DATETIME = "datetime"
    OBJECT = "object"
    ARRAY = "array"


class DiagnosticLevel(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


def _matches(value: Any, data_type: str) -> bool:
    if data_type == DataType.STRING:
        return isinstance(value, str)
    if data_type == DataType.INTEGER:
        return isinstance(value, int) and not isinstance(value, bool)
    if data_type == DataType.NUMBER:
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if data_type == DataType.BOOLEAN:
        return isinstance(value, bool)
    if data_type == DataType.DATETIME:
        return isinstance(value, str)
    if data_type == DataType.OBJECT:
        return isinstance(value, dict)
    if data_type == DataType.ARRAY:
        return isinstance(value, list)
    return False


@dataclass
class ColumnSpec:
    key: str
    title: str
    data_type: str
    unit: str | None = None
    description: str | None = None
    nullable: bool = False

    def __post_init__(self) -> None:
        if not self.key or not self.title:
            raise ValueError("ColumnSpec.key / title 不能为空")
        try:
            self.data_type = DataType(self.data_type)
        except ValueError as exc:
            raise ValueError(f"未知的 data_type: {self.data_type}") from exc


@dataclass
class Dataset:
    name: str
    title: str
    columns: list[ColumnSpec]
    rows: list[dict] = field(default_factory=list)

    def __post_init__(self) -> None:
        keys = [c.key for c in self.columns]
        if len(keys) != len(set(keys)):
            raise ValueError("dataset column keys 必须唯一")
        allowed = set(keys)
        required = {c.key for c in self.columns if not c.nullable}
        for index, row in enumerate(self.rows):
            unknown = set(row) - allowed
            if unknown:
                raise ValueError(f"第 {index} 行含未知列: {sorted(unknown)}")
            missing = required - set(row)
            if missing:
                raise ValueError(f"第 {index} 行缺少必填列: {sorted(missing)}")
            for column in self.columns:
                if column.key not in row:
                    continue
                value = row[column.key]
                if value is None and column.nullable:
                    continue
                if value is None or not _matches(value, column.data_type):
                    raise ValueError(
                        f"第 {index} 行 '{column.key}' 必须是 {column.data_type}，实际 {value!r}"
                    )


@dataclass
class Diagnostic:
    code: str
    level: str
    message: str
    location: str | None = None
    details: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.code or not self.message:
            raise ValueError("Diagnostic.code / message 不能为空")
        try:
            self.level = DiagnosticLevel(self.level)
        except ValueError as exc:
            raise ValueError(f"非法 level: {self.level}") from exc


@dataclass
class ResultPayload:
    summary: str = ""
    datasets: list[Dataset] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)
    diagnostics: list[Diagnostic] = field(default_factory=list)
    artifacts: list = field(default_factory=list)

    def __post_init__(self) -> None:
        names = [d.name for d in self.datasets]
        if len(names) != len(set(names)):
            raise ValueError("数据集名称必须唯一")


_CASE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


@dataclass
class CaseDescriptor:
    case_id: str
    name: str
    course: str
    course_number: int | None = None
    catalog_visible: bool = True
    description: str = ""
    version: str = "1.0.0"
    input_schema: dict = field(default_factory=dict)
    output_datasets: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not _CASE_ID_RE.match(self.case_id):
            raise ValueError(f"case_id 不合法: {self.case_id}")
        if self.catalog_visible and self.course_number is None:
            raise ValueError("catalog_visible 的案例必须声明 course_number")


@dataclass
class ExecutionContext:
    request_id: str
    parameters: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)
    runtime: Any = None


class CaseInputError(ValueError):
    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__(message)
        self.details = details or {}


class CaseAdapter:
    @property
    def descriptor(self) -> CaseDescriptor:  # pragma: no cover - 抽象
        raise NotImplementedError

    def execute(self, input_data: dict, context: ExecutionContext) -> ResultPayload:  # pragma: no cover
        raise NotImplementedError


class CaseRegistry:
    def __init__(self) -> None:
        self._adapters: dict[str, CaseAdapter] = {}

    def register(self, adapter: CaseAdapter) -> None:
        case_id = adapter.descriptor.case_id
        if case_id in self._adapters:
            raise ValueError(f"case 重复注册: {case_id}")
        self._adapters[case_id] = adapter

    def get(self, case_id: str) -> CaseAdapter:
        return self._adapters[case_id]

    def list(self) -> list[CaseDescriptor]:
        return [a.descriptor for a in self._adapters.values()]


# ---------------------------------------------------------------------------
# 代码运行器契约（对应 ai_tutor_backend.code_execution）
# ---------------------------------------------------------------------------
class CodeExecutionStatus(str, Enum):
    SUCCEEDED = "succeeded"
    COMPILE_ERROR = "compile_error"
    RUNTIME_ERROR = "runtime_error"
    TIMED_OUT = "timed_out"
    UNAVAILABLE = "unavailable"
    INTERNAL_ERROR = "internal_error"


@dataclass
class CodeFile:
    path: str
    content: str


@dataclass
class PythonRunSpec:
    files: list[CodeFile]
    entrypoint: str
    argv: list[str] = field(default_factory=list)
    stdin: str = ""
    timeout_seconds: float = 5.0
    memory_limit_mb: int = 128
    max_output_bytes: int = 128_000


@dataclass
class PythonRunResult:
    """字段与 ai_tutor_backend.code_execution.PythonRunResult 保持一致。"""

    status: CodeExecutionStatus
    compile_succeeded: bool
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    duration_ms: float = 0.0
    output_truncated: bool = False


class CodeRunner:
    async def run_python(self, spec: PythonRunSpec) -> PythonRunResult:  # pragma: no cover
        raise NotImplementedError


@dataclass
class ExecutionRuntime:
    code_runner: CodeRunner
