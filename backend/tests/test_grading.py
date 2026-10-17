from __future__ import annotations

from ai_tutor_backend.models import (
    ColumnSpec,
    ComparisonPolicy,
    Dataset,
    DataType,
    ResultPayload,
)
from assignment_grading import compare_payloads


def payload(value: float, rows: list[dict] | None = None) -> ResultPayload:
    return ResultPayload(
        summary="done",
        metrics={"answer": value},
        datasets=[
            Dataset(
                name="values",
                title="Values",
                columns=[ColumnSpec(key="value", title="Value", data_type=DataType.NUMBER)],
                rows=rows or [{"value": value}],
            )
        ],
    )


def test_exact_comparison_reports_a_precise_path() -> None:
    report = compare_payloads(
        actual_result_id="r1",
        actual=payload(9),
        expected=payload(10),
        policy=ComparisonPolicy(),
    )

    assert report.passed is False
    assert report.score < 100
    assert {issue.path for issue in report.issues} == {
        "$.datasets[0].rows[0].value",
        "$.metrics.answer",
    }


def test_numeric_tolerance_and_ignored_row_order() -> None:
    actual = payload(10.001, [{"value": 2}, {"value": 1}])
    expected = payload(10.0, [{"value": 1}, {"value": 2}])
    report = compare_payloads(
        actual_result_id="r2",
        actual=actual,
        expected=expected,
        policy=ComparisonPolicy(
            mode="numeric_tolerance",
            absolute_tolerance=0.01,
            ignore_row_order=True,
        ),
    )

    assert report.passed is True
    assert report.score == 100
