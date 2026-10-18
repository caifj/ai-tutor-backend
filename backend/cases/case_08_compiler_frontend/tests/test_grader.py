"""Case 8 offline contract check for the case-specific runtime layer.

The real backend service owns PEP8, modularity and similarity evaluation. This
script verifies that the case adapter returns only compiler-course runtime
results and an 80-point case score.
"""
from __future__ import annotations

import asyncio
import io
import sys
import time
import traceback
import types
from contextlib import redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve()
PACKAGE_DIR = HERE.parents[1]
IMPORT_ROOT = PACKAGE_DIR.parent
TESTCASE_DIR = IMPORT_ROOT.parent / "testcase"
sys.path.insert(0, str(IMPORT_ROOT))
sys.path.insert(0, str(HERE.parent))

import _fake_backend as fb
import _pydantic_stub

sys.modules.setdefault("pydantic", _pydantic_stub)
sys.modules.setdefault("ai_tutor_backend", fb)

from case_08_compiler_frontend import MiniCompilerFrontendCase


class LocalRunner(fb.CodeRunner):
    """Run the shared Case 8 harness with the fake backend contract."""

    async def run_python(self, spec: fb.PythonRunSpec) -> fb.PythonRunResult:
        files = {item.path: item.content for item in spec.files}
        module = types.ModuleType("student")
        sys.modules["student"] = module
        buffer = io.StringIO()
        status = fb.CodeExecutionStatus.SUCCEEDED
        stderr = ""
        started = time.perf_counter()
        try:
            with redirect_stdout(buffer):
                exec(  # noqa: S102 - emulate the isolated runner contract
                    compile(files["student.py"], "student.py", "exec"), module.__dict__
                )
                exec(  # noqa: S102 - execute the trusted Case 8 harness
                    compile(files[spec.entrypoint], "case_harness.py", "exec"),
                    {"__name__": "__main__", "__file__": "case_harness.py"},
                )
        except Exception:  # noqa: BLE001 - emulate runner failure capture
            status = fb.CodeExecutionStatus.RUNTIME_ERROR
            stderr = traceback.format_exc()
        finally:
            sys.modules.pop("student", None)
        return fb.PythonRunResult(
            status=status,
            compile_succeeded=status == fb.CodeExecutionStatus.SUCCEEDED,
            stdout=buffer.getvalue(),
            stderr=stderr,
            duration_ms=(time.perf_counter() - started) * 1000,
        )


def load(name: str) -> str:
    return (TESTCASE_DIR / name).read_text(encoding="utf-8")


def main() -> int:
    case = MiniCompilerFrontendCase()
    descriptor = case.descriptor
    assert descriptor.version == "2.0.0"
    assert descriptor.python_static_evaluation is True
    assert descriptor.output_datasets == [
        "runtime_tests",
        "ast_tree",
        "error_locations",
        "quality_scores",
        "code_issues",
    ]

    runtime = fb.ExecutionRuntime(code_runner=LocalRunner())
    payload = asyncio.run(
        case.execute(
            {"filename": "case8_correct.py", "source_code": load("case8_correct.py")},
            fb.ExecutionContext(request_id="case8-offline", runtime=runtime),
        )
    )

    assert [dataset.name for dataset in payload.datasets] == [
        "runtime_tests",
        "ast_tree",
        "error_locations",
    ]
    assert payload.metrics["functionality_score"] == 80.0
    assert payload.metrics["overall_score"] == 80.0
    assert payload.metrics["runtime_pass_rate"] == 100.0
    assert "pep8_score" not in payload.metrics
    assert "modularity_score" not in payload.metrics
    print("Case 8 runtime-only contract check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
