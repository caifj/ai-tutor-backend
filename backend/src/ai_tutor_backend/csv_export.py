from __future__ import annotations

import csv
import json
from collections.abc import Iterable
from io import StringIO
from typing import Any

from .models import ExecutionResult, GradeReport

EXECUTION_HEADERS = [
    "schema_version",
    "request_id",
    "case_id",
    "status",
    "record_type",
    "dataset",
    "row_index",
    "field",
    "value",
    "value_type",
    "unit",
]


def _value_and_type(value: Any) -> tuple[str, str]:
    if value is None:
        return "", "null"
    if isinstance(value, bool):
        return ("true" if value else "false"), "boolean"
    if isinstance(value, int):
        return str(value), "integer"
    if isinstance(value, float):
        return repr(value), "number"
    if isinstance(value, str):
        return value, "string"
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")), (
        "array" if isinstance(value, list) else "object"
    )


def execution_to_csv(result: ExecutionResult) -> str:
    buffer = StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=EXECUTION_HEADERS)
    writer.writeheader()

    def write(
        record_type: str,
        field: str,
        value: Any,
        *,
        dataset: str = "",
        row_index: int | str = "",
        unit: str = "",
    ) -> None:
        encoded, value_type = _value_and_type(value)
        writer.writerow(
            {
                "schema_version": result.schema_version,
                "request_id": result.request_id,
                "case_id": result.case_id,
                "status": result.status.value,
                "record_type": record_type,
                "dataset": dataset,
                "row_index": row_index,
                "field": field,
                "value": encoded,
                "value_type": value_type,
                "unit": unit,
            }
        )

    write("summary", "summary", result.payload.summary)
    for key, value in sorted(result.payload.metrics.items()):
        write("metric", key, value)
    for dataset in result.payload.datasets:
        units = {column.key: column.unit or "" for column in dataset.columns}
        for row_index, row in enumerate(dataset.rows):
            for column in dataset.columns:
                write(
                    "data",
                    column.key,
                    row.get(column.key),
                    dataset=dataset.name,
                    row_index=row_index,
                    unit=units[column.key],
                )
    for index, diagnostic in enumerate(result.payload.diagnostics):
        write("diagnostic", "diagnostic", diagnostic.model_dump(mode="json"), row_index=index)
    for index, artifact in enumerate(result.payload.artifacts):
        write("artifact", "artifact", artifact.model_dump(mode="json"), row_index=index)
    return buffer.getvalue()


def grade_to_csv(report: GradeReport) -> str:
    buffer = StringIO(newline="")
    headers = [
        "schema_version",
        "grade_id",
        "actual_result_id",
        "passed",
        "score",
        "explanation",
        "issue_index",
        "path",
        "code",
        "message",
        "expected",
        "actual",
    ]
    writer = csv.DictWriter(buffer, fieldnames=headers)
    writer.writeheader()
    issues: Iterable[Any] = report.issues or [None]
    for index, issue in enumerate(issues):
        writer.writerow(
            {
                "schema_version": report.schema_version,
                "grade_id": report.grade_id,
                "actual_result_id": report.actual_result_id,
                "passed": str(report.passed).lower(),
                "score": report.score,
                "explanation": report.explanation,
                "issue_index": index if issue is not None else "",
                "path": issue.path if issue else "",
                "code": issue.code if issue else "",
                "message": issue.message if issue else "",
                "expected": _value_and_type(issue.expected)[0] if issue else "",
                "actual": _value_and_type(issue.actual)[0] if issue else "",
            }
        )
    return buffer.getvalue()
