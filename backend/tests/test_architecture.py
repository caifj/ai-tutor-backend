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


def test_backend_app_uses_the_decoupled_ai_package() -> None:
    source = (SOURCE_ROOT / "ai_tutor_backend" / "app.py").read_text(encoding="utf-8")

    assert "from course_assistant_ai import" in source
    assert "from .assistant import" not in source


def test_production_wheel_includes_the_ai_package() -> None:
    pyproject = (SOURCE_ROOT.parent / "pyproject.toml").read_text(encoding="utf-8")

    assert '"src/course_assistant_ai"' in pyproject
