from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"


def _python_source(package: str) -> str:
    return "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((SOURCE_ROOT / package).rglob("*.py"))
    )


def test_ai_package_does_not_import_backend_or_grading_packages() -> None:
    source = _python_source("course_assistant_ai")

    assert "ai_tutor_backend" not in source
    assert "assignment_grading" not in source


def test_grading_package_does_not_import_ai_package() -> None:
    source = _python_source("assignment_grading")

    assert "course_assistant_ai" not in source
