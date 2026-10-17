from __future__ import annotations

import asyncio

from ai_tutor_backend.code_execution import (
    CodeExecutionStatus,
    CodeFile,
    LocalPythonRunner,
    PythonRunSpec,
)


def run(spec: PythonRunSpec):
    return asyncio.run(LocalPythonRunner().run_python(spec))


def test_python_runner_compiles_and_collects_output() -> None:
    result = run(
        PythonRunSpec(
            files=[CodeFile(path="main.py", content='print("structured-output")\n')],
            entrypoint="main.py",
        )
    )

    assert result.status == CodeExecutionStatus.SUCCEEDED
    assert result.compile_succeeded is True
    assert result.exit_code == 0
    assert result.stdout.strip() == "structured-output"


def test_python_runner_preserves_unicode_output() -> None:
    result = run(
        PythonRunSpec(
            files=[CodeFile(path="main.py", content='print("运行验证：构造报文")\n')],
            entrypoint="main.py",
        )
    )

    assert result.status == CodeExecutionStatus.SUCCEEDED
    assert result.stdout.strip() == "运行验证：构造报文"


def test_python_runner_reports_compile_error() -> None:
    result = run(
        PythonRunSpec(
            files=[CodeFile(path="main.py", content="def broken(:\n    pass\n")],
            entrypoint="main.py",
        )
    )

    assert result.status == CodeExecutionStatus.COMPILE_ERROR
    assert result.compile_succeeded is False
    assert "SyntaxError" in result.stderr


def test_python_runner_supports_multiple_project_files() -> None:
    result = run(
        PythonRunSpec(
            files=[
                CodeFile(path="main.py", content="from helper import answer\nprint(answer())\n"),
                CodeFile(path="helper.py", content="def answer():\n    return 42\n"),
            ],
            entrypoint="main.py",
        )
    )

    assert result.status == CodeExecutionStatus.SUCCEEDED
    assert result.stdout.strip() == "42"


def test_python_runner_terminates_timeout() -> None:
    result = run(
        PythonRunSpec(
            files=[CodeFile(path="main.py", content="while True:\n    pass\n")],
            entrypoint="main.py",
            timeout_seconds=0.2,
        )
    )

    assert result.status == CodeExecutionStatus.TIMED_OUT
    assert result.compile_succeeded is True
