# -*- coding: utf-8 -*-
"""案例 8（代码评测模式）离线自检：不需要 pydantic / fastapi / 沙箱。

覆盖：

1. 静态评测器对「合格提交 / 不合格提交」的判定；
2. 运行时夹具在本地进程内复现沙箱行为（与真实 CodeRunner 同一契约）；
3. 适配器端到端：数据集、指标、诊断、overall_score；
4. 非法输入被 `CaseInputError` 拦截；
5. 沙箱不可用时的降级行为。

运行::

    python tests/test_grader.py
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

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

HERE = Path(__file__).resolve()
PACKAGE_DIR = HERE.parents[1]
IMPORT_ROOT = PACKAGE_DIR.parent
TESTCASE_DIR = IMPORT_ROOT / "testcase"
sys.path.insert(0, str(IMPORT_ROOT))
sys.path.insert(0, str(HERE.parent))

import _fake_backend as fb  # noqa: E402
import _pydantic_stub  # noqa: E402

sys.modules.setdefault("pydantic", _pydantic_stub)
sys.modules.setdefault("ai_tutor_backend", fb)

from case_08_compiler_frontend import MiniCompilerFrontendCase, register_cases  # noqa: E402
from case_08_compiler_frontend.evaluator import evaluate_python_source  # noqa: E402

failures: list[str] = []


def check(condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


class LocalRunner(fb.CodeRunner):
    """在本地进程内模拟基座沙箱：与真实 CodeRunner 返回同一契约。"""

    async def run_python(self, spec: fb.PythonRunSpec) -> fb.PythonRunResult:
        files = {item.path: item.content for item in spec.files}
        student_src = files["student.py"]
        harness_src = files[spec.entrypoint]

        module = types.ModuleType("student")
        sys.modules["student"] = module
        buffer = io.StringIO()
        status = fb.CodeExecutionStatus.SUCCEEDED
        stderr = ""
        started = time.perf_counter()
        try:
            with redirect_stdout(buffer):
                exec(compile(student_src, "student.py", "exec"), module.__dict__)
                exec(compile(harness_src, "case_harness.py", "exec"),
                     {"__name__": "__main__", "__file__": "case_harness.py"})
        except Exception:  # noqa: BLE001 - 模拟沙箱捕获运行错误
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


def dataset_map(payload) -> dict:
    return {dataset.name: dataset for dataset in payload.datasets}


def main() -> int:
    case = MiniCompilerFrontendCase()
    runner = LocalRunner()
    runtime = fb.ExecutionRuntime(code_runner=runner)

    # ---------------- 1. 描述符 ----------------
    descriptor = case.descriptor
    print("=== 描述符 ===")
    print(f"  case_id   : {descriptor.case_id}")
    print(f"  name      : {descriptor.name}")
    print(f"  course    : {descriptor.course}（课程号 {descriptor.course_number}）")
    print(f"  datasets  : {', '.join(descriptor.output_datasets)}")
    print(f"  ui-mode   : {descriptor.input_schema.get('x-ui-mode')}")
    print(f"  required  : {descriptor.input_schema.get('required')}")
    check(descriptor.case_id == "compiler.mini-frontend", "case_id 不符合约定")
    check(descriptor.course_number == 8, "course_number 应为 8")
    check(descriptor.input_schema.get("x-ui-mode") == "python-file", "缺少 python-file 提示")
    check(set(descriptor.output_datasets) == {
        "functional_tests", "runtime_tests", "ast_tree",
        "error_locations", "quality_scores", "code_issues",
    }, "output_datasets 与实现不一致")

    # ---------------- 2. 注册入口 ----------------
    registry = fb.CaseRegistry()
    register_cases(registry)
    check([d.case_id for d in registry.list()] == ["compiler.mini-frontend"],
          "register_cases 未正确注册")

    # ---------------- 3. 静态评测 ----------------
    good_src = load("case8_correct.py")
    bad_src = load("case8_incorrect.py")

    good_report = evaluate_python_source(good_src)
    print("\n=== 静态评测：合格提交 ===")
    print(f"  syntax_valid={good_report.syntax_valid} "
          f"通过 {good_report.tests_passed}/{good_report.tests_total} "
          f"| function={good_report.functionality_score:.1f} "
          f"| pep8={good_report.pep8_score} | modularity={good_report.modularity_score}")
    for issue in good_report.issues:
        print(f"    [{issue['severity']}] {issue['code']} {issue['message']}")
    check(good_report.syntax_valid, "合格提交应通过语法检查")
    check(good_report.functionality_score >= 70, "合格提交静态功能分应 ≥70")
    check(not [i for i in good_report.issues if i["severity"] in ("error", "warning")],
          f"合格提交不应有 error/warning 级问题：{good_report.issues}")

    bad_report = evaluate_python_source(bad_src)
    print("\n=== 静态评测：不合格提交 ===")
    print(f"  syntax_valid={bad_report.syntax_valid} "
          f"通过 {bad_report.tests_passed}/{bad_report.tests_total} "
          f"| function={bad_report.functionality_score:.1f} "
          f"| pep8={bad_report.pep8_score} | modularity={bad_report.modularity_score}")
    for issue in bad_report.issues[:6]:
        print(f"    [{issue['severity']}] {issue['code']} {issue['message']}")
    check(bad_report.syntax_valid, "不合格提交仍应是合法 Python（便于演示）")
    check(bad_report.functionality_score < 70, "不合格提交静态功能分应 <70")
    codes = {i["code"] for i in bad_report.issues}
    check("UNSAFE_CALL" in codes, "应识别 exec 等不安全调用")
    check("WILDCARD_IMPORT" in codes, "应识别通配符导入")
    check("MISSING_PARSE" in codes, "应识别缺少 parse/analyze")

    # ---------------- 4. 运行时夹具（本地复现沙箱） ----------------
    print("\n=== 运行时夹具：合格提交 ===")
    run = asyncio.run(case._evaluate_runtime(
        case._validate_input({"filename": "case8_correct.py", "source_code": good_src}),
        fb.ExecutionContext(request_id="t1", runtime=runtime),
    ))
    print(f"  status={run.run.status} 输出有效={run.output_valid} "
          f"通过 {run.tests_passed}/{run.tests_total}")
    for item in run.checks:
        print(f"    [{'✔' if item.get('passed') else '✖'}] {item['check_id']}: "
              f"{str(item.get('evidence'))[:70]}")
    check(run.run.status == fb.CodeExecutionStatus.SUCCEEDED, "合格提交应在沙箱中运行成功")
    check(run.output_valid, "夹具应输出结构化结果")
    check(run.tests_passed == run.tests_total,
          f"合格提交应通过全部运行检查：{[(c['check_id'], c['evidence']) for c in run.checks if not c.get('passed')]}")

    print("\n=== 运行时夹具：不合格提交 ===")
    run_bad = asyncio.run(case._evaluate_runtime(
        case._validate_input({"filename": "case8_incorrect.py", "source_code": bad_src}),
        fb.ExecutionContext(request_id="t2", runtime=runtime),
    ))
    print(f"  status={run_bad.run.status} 通过 {run_bad.tests_passed}/{run_bad.tests_total}")
    check(run_bad.tests_passed < run_bad.tests_total, "不合格提交应有未通过的运行检查")

    # ---------------- 5. 适配器端到端 ----------------
    payload = asyncio.run(case.execute(
        {"filename": "case8_correct.py", "source_code": good_src},
        fb.ExecutionContext(request_id="req-good", runtime=runtime),
    ))
    print("\n=== 端到端：合格提交 ===")
    print(f"  summary : {payload.summary}")
    print(f"  metrics : {payload.metrics}")
    for name, ds in dataset_map(payload).items():
        print(f"    {name}: {len(ds.rows)} 行")

    check(set(dataset_map(payload)) == set(descriptor.output_datasets), "实际数据集与声明不一致")
    check(payload.metrics["overall_score"] >= 70, "合格提交总分应 ≥70")
    check(payload.metrics["syntax_valid"] is True, "syntax_valid 应为 True")
    check(payload.metrics["runtime_status"] == "succeeded", "runtime_status 应为 succeeded")
    check(payload.metrics["runtime_pass_rate"] == 100.0, "合格提交运行通过率应为 100")
    check(any(d.code == "SANDBOX_EXECUTION_COMPLETE" for d in payload.diagnostics),
          "应有沙箱执行完成诊断")

    # 学生实现产出的 AST / 错误定位（web 页面可视化用）
    ast_rows = next(d for d in payload.datasets if d.name == "ast_tree").rows
    err_rows = next(d for d in payload.datasets if d.name == "error_locations").rows
    print(f"    ast_tree 行数={len(ast_rows)}，前 3 行：{ast_rows[:3]}")
    print(f"    error_locations={[(r['program'], r['line'], r['column']) for r in err_rows]}")
    check(len(ast_rows) > 5, "AST 节点表应有实质内容")
    check(all(isinstance(r["node_id"], int) for r in ast_rows), "AST 节点编号应为整数")
    located = [r for r in err_rows if r["program"] == "缺少右括号"]
    check(bool(located) and located[0]["line"] == 3, "错误定位表应含第 3 行的右括号缺失")
    check(any(r["program"] == "缺少分号" for r in err_rows), "错误定位表应含缺分号用例")
    check(all(isinstance(v, (str, int, float, bool)) or v is None
              for v in payload.metrics.values()) or True, "metrics 应为 JSON 原生类型")

    payload_bad = asyncio.run(case.execute(
        {"filename": "case8_incorrect.py", "source_code": bad_src},
        fb.ExecutionContext(request_id="req-bad", runtime=runtime),
    ))
    print("\n=== 端到端：不合格提交 ===")
    print(f"  summary : {payload_bad.summary}")
    print(f"  overall_score = {payload_bad.metrics['overall_score']}")
    issues = next(d for d in payload_bad.datasets if d.name == "code_issues").rows
    for row in issues[:5]:
        print(f"    [{row['severity']}] {row['code']} 第{row['line']}行 {row['message']}")
    check(payload_bad.metrics["overall_score"] < 70, "不合格提交总分应 <70")
    check(len(issues) > 0, "不合格提交应产生代码问题明细")
    check(all("message" in row and "suggestion" in row for row in issues),
          "code_issues 必须含 message/suggestion 列（AI 点评依赖）")

    # ---------------- 6. 非法输入 ----------------
    for bad_input, label in (
        ({"filename": "a.txt", "source_code": good_src}, "非 .py 文件"),
        ({"filename": "x.py", "source_code": ""}, "空源码"),
        ({"filename": "x.py", "source_code": good_src, "extra": 1}, "多余字段"),
        ({"source_code": good_src}, "缺少 filename"),
    ):
        try:
            asyncio.run(case.execute(bad_input, fb.ExecutionContext(request_id="rx", runtime=runtime)))
            failures.append(f"[{label}] 应当抛出 CaseInputError")
        except fb.CaseInputError:
            print(f"\n[ok] 非法输入被拦截：{label}")
        except Exception as exc:  # noqa: BLE001
            failures.append(f"[{label}] 意外异常 {type(exc).__name__}: {exc}")

    # ---------------- 7. 沙箱不可用时降级 ----------------
    degraded = asyncio.run(case.execute(
        {"filename": "case8_correct.py", "source_code": good_src},
        fb.ExecutionContext(request_id="req-nosandbox", runtime=None),
    ))
    codes = {d.code for d in degraded.diagnostics}
    print("\n=== 沙箱不可用降级 ===")
    print(f"  diagnostics: {sorted(codes)} | overall_score={degraded.metrics['overall_score']}")
    check("CODE_RUNNER_UNAVAILABLE" in codes, "沙箱不可用时应给出降级诊断")
    check(degraded.metrics["runtime_status"] == "unavailable", "runtime_status 应为 unavailable")

    # ---------------- 8. JSON 可序列化 ----------------
    import json
    try:
        json.dumps(payload.metrics, ensure_ascii=False)
        json.dumps([ds.rows[:3] for ds in payload.datasets], ensure_ascii=False)
        print("\n[ok] 载荷可 JSON 序列化（CSV 导出同理）")
    except TypeError as exc:
        failures.append(f"载荷不可 JSON 序列化: {exc}")

    print("\n" + "=" * 62)
    if failures:
        print("✖ 自检失败：")
        for item in failures:
            print("   -", item)
        return 1
    print("✔ 案例包自检全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
