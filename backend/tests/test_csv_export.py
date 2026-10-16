from __future__ import annotations

import csv
from io import StringIO

import pytest
from pydantic import ValidationError

from ai_tutor_backend.csv_export import execution_to_csv
from ai_tutor_backend.models import (
    ColumnSpec,
    Dataset,
    DataType,
    ExecutionResult,
    ExecutionStatus,
    ResultPayload,
)


def test_csv_export_uses_stable_long_form_and_preserves_nested_json() -> None:
    result = ExecutionResult(
        request_id="request-1",
        case_id="stub",
        status=ExecutionStatus.SUCCEEDED,
        duration_ms=1.5,
        payload=ResultPayload(
            summary="完成",
            metrics={"count": 1},
            datasets=[
                Dataset(
                    name="tree",
                    title="Tree",
                    columns=[ColumnSpec(key="node", title="Node", data_type=DataType.OBJECT)],
                    rows=[{"node": {"type": "root", "children": []}}],
                )
            ],
        ),
    )

    rows = list(csv.DictReader(StringIO(execution_to_csv(result))))

    assert [row["record_type"] for row in rows] == ["summary", "metric", "data"]
    assert rows[-1]["dataset"] == "tree"
    assert rows[-1]["value_type"] == "object"
    assert '"type":"root"' in rows[-1]["value"]


def test_dataset_rejects_values_that_do_not_match_column_type() -> None:
    with pytest.raises(ValidationError, match="must be integer"):
        Dataset(
            name="invalid",
            title="Invalid",
            columns=[ColumnSpec(key="count", title="Count", data_type=DataType.INTEGER)],
            rows=[{"count": "one"}],
        )
