from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

JsonObject = dict[str, JsonValue]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DataType(StrEnum):
    STRING = "string"
    INTEGER = "integer"
    NUMBER = "number"
    BOOLEAN = "boolean"
    DATETIME = "datetime"
    OBJECT = "object"
    ARRAY = "array"


class ExecutionStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class DiagnosticLevel(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class ColumnSpec(StrictModel):
    key: str = Field(min_length=1)
    title: str = Field(min_length=1)
    data_type: DataType
    unit: str | None = None
    description: str | None = None
    nullable: bool = False


class Dataset(StrictModel):
    """A frontend-friendly table; nested values remain valid JSON cells."""

    name: str = Field(min_length=1)
    title: str = Field(min_length=1)
    columns: list[ColumnSpec] = Field(min_length=1)
    rows: list[JsonObject] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_shape(self) -> Dataset:
        keys = [column.key for column in self.columns]
        if len(keys) != len(set(keys)):
            raise ValueError("dataset column keys must be unique")
        allowed = set(keys)
        required = {column.key for column in self.columns if not column.nullable}
        for index, row in enumerate(self.rows):
            unknown = set(row) - allowed
            if unknown:
                raise ValueError(f"row {index} contains unknown columns: {sorted(unknown)}")
            missing = required - set(row)
            if missing:
                raise ValueError(f"row {index} misses required columns: {sorted(missing)}")
            for column in self.columns:
                if column.key not in row:
                    continue
                value = row[column.key]
                if value is None and column.nullable:
                    continue
                if value is None or not _matches_data_type(value, column.data_type):
                    raise ValueError(
                        f"row {index} column '{column.key}' must be {column.data_type.value}"
                    )
        return self


class Diagnostic(StrictModel):
    code: str = Field(min_length=1)
    level: DiagnosticLevel
    message: str = Field(min_length=1)
    location: str | None = None
    details: JsonObject = Field(default_factory=dict)


class Artifact(StrictModel):
    name: str = Field(min_length=1)
    media_type: str = Field(min_length=1)
    uri: str = Field(min_length=1)
    description: str | None = None


class ResultPayload(StrictModel):
    """The case-independent portion returned by every teaching case."""

    summary: str = ""
    datasets: list[Dataset] = Field(default_factory=list)
    metrics: JsonObject = Field(default_factory=dict)
    diagnostics: list[Diagnostic] = Field(default_factory=list)
    artifacts: list[Artifact] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_dataset_names(self) -> ResultPayload:
        names = [dataset.name for dataset in self.datasets]
        if len(names) != len(set(names)):
            raise ValueError("dataset names must be unique")
        return self


class ExecutionRequest(StrictModel):
    case_id: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9][a-z0-9._-]*$")
    input: JsonObject
    parameters: JsonObject = Field(default_factory=dict)
    metadata: JsonObject = Field(default_factory=dict)


class ExecutionContext(StrictModel):
    request_id: str
    parameters: JsonObject = Field(default_factory=dict)
    metadata: JsonObject = Field(default_factory=dict)
    runtime: Any | None = Field(default=None, exclude=True, repr=False)


class ExecutionResult(StrictModel):
    schema_version: str = "1.0"
    request_id: str
    case_id: str
    status: ExecutionStatus
    payload: ResultPayload
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    duration_ms: float = Field(ge=0)


class CaseDescriptor(StrictModel):
    case_id: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9][a-z0-9._-]*$")
    name: str = Field(min_length=1)
    course: str = Field(min_length=1)
    course_number: int | None = Field(default=None, ge=1, le=99)
    catalog_visible: bool = True
    description: str = ""
    version: str = "1.0.0"
    input_schema: JsonObject = Field(default_factory=dict)
    output_datasets: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_visible_course_number(self) -> CaseDescriptor:
        if self.catalog_visible and self.course_number is None:
            raise ValueError("catalog-visible cases must declare course_number")
        return self


class CaseListResponse(StrictModel):
    schema_version: str = "1.0"
    items: list[CaseDescriptor]


class CompareMode(StrEnum):
    EXACT = "exact"
    NUMERIC_TOLERANCE = "numeric_tolerance"


class ComparisonPolicy(StrictModel):
    mode: CompareMode = CompareMode.EXACT
    absolute_tolerance: float = Field(default=0.0, ge=0)
    relative_tolerance: float = Field(default=0.0, ge=0)
    ignore_row_order: bool = False
    ignored_paths: list[str] = Field(default_factory=list)
    max_issues: int = Field(default=100, ge=1, le=1000)


class GradeRequest(StrictModel):
    actual_result_id: str
    expected: ResultPayload
    policy: ComparisonPolicy = Field(default_factory=ComparisonPolicy)


class GradeIssue(StrictModel):
    path: str
    code: str
    message: str
    expected: Any | None = None
    actual: Any | None = None


class GradeReport(StrictModel):
    schema_version: str = "1.0"
    grade_id: str
    actual_result_id: str
    passed: bool
    score: float = Field(ge=0, le=100)
    explanation: str
    issues: list[GradeIssue]
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ErrorDetail(StrictModel):
    code: str
    message: str
    request_id: str | None = None
    details: JsonObject = Field(default_factory=dict)


class ErrorResponse(StrictModel):
    schema_version: str = "1.0"
    error: ErrorDetail


def _matches_data_type(value: JsonValue, data_type: DataType) -> bool:
    if data_type == DataType.STRING:
        return isinstance(value, str)
    if data_type == DataType.INTEGER:
        return isinstance(value, int) and not isinstance(value, bool)
    if data_type == DataType.NUMBER:
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if data_type == DataType.BOOLEAN:
        return isinstance(value, bool)
    if data_type == DataType.DATETIME:
        if not isinstance(value, str):
            return False
        try:
            datetime.fromisoformat(value)
        except ValueError:
            return False
        return True
    if data_type == DataType.OBJECT:
        return isinstance(value, dict)
    if data_type == DataType.ARRAY:
        return isinstance(value, list)
    return False
