from __future__ import annotations

from ai_tutor_backend.static_evaluation import evaluate_python_static


def test_generic_python_static_evaluation_only_reports_quality_rules() -> None:
    evaluation = evaluate_python_static(
        '''
def parse_value(value):
    """Normalize one value."""
    return value.strip()


def format_value(value):
    """Format one value."""
    return parse_value(value).upper()
'''
    )

    assert evaluation.syntax_valid is True
    assert {row["dimension"] for row in evaluation.quality_scores} == {
        "PEP8 规范",
        "模块化程度",
    }
    assert all(issue["code"] != "SEC001" for issue in evaluation.issues)


def test_generic_python_static_evaluation_reports_syntax_line() -> None:
    evaluation = evaluate_python_static("def broken(:\n    pass\n", "answer.py")

    assert evaluation.syntax_valid is False
    assert evaluation.pep8_score == 0.0
    assert evaluation.modularity_score == 0.0
    assert evaluation.issues[0]["code"] == "E999"
    assert evaluation.issues[0]["line"] == 1
