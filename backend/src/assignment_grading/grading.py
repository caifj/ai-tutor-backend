from __future__ import annotations

import json
import math
from typing import Any
from uuid import uuid4

from ai_tutor_backend.models import ComparisonPolicy, GradeIssue, GradeReport, ResultPayload

_MISSING = object()


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def compare_payloads(
    *,
    actual_result_id: str,
    actual: ResultPayload,
    expected: ResultPayload,
    policy: ComparisonPolicy,
) -> GradeReport:
    issues: list[GradeIssue] = []
    ignored = set(policy.ignored_paths)

    def add_issue(path: str, code: str, message: str, exp: Any, act: Any) -> None:
        if len(issues) >= policy.max_issues:
            return
        issues.append(
            GradeIssue(
                path=path,
                code=code,
                message=message,
                expected=None if exp is _MISSING else exp,
                actual=None if act is _MISSING else act,
            )
        )

    def visit(exp: Any, act: Any, path: str) -> None:
        if path in ignored or len(issues) >= policy.max_issues:
            return
        if exp is _MISSING:
            add_issue(path, "unexpected_value", "存在不应出现的值", exp, act)
            return
        if act is _MISSING:
            add_issue(path, "missing_value", "缺少期望值", exp, act)
            return
        if isinstance(exp, dict) and isinstance(act, dict):
            for key in sorted(set(exp) | set(act)):
                visit(exp.get(key, _MISSING), act.get(key, _MISSING), f"{path}.{key}")
            return
        if isinstance(exp, list) and isinstance(act, list):
            if policy.ignore_row_order and path.endswith(".rows"):
                exp = sorted(exp, key=_canonical)
                act = sorted(act, key=_canonical)
            for index in range(max(len(exp), len(act))):
                exp_item = exp[index] if index < len(exp) else _MISSING
                act_item = act[index] if index < len(act) else _MISSING
                visit(exp_item, act_item, f"{path}[{index}]")
            return
        if policy.mode == "numeric_tolerance" and _is_number(exp) and _is_number(act):
            if math.isclose(
                float(exp),
                float(act),
                abs_tol=policy.absolute_tolerance,
                rel_tol=policy.relative_tolerance,
            ):
                return
        elif type(exp) is type(act) and exp == act:
            return
        add_issue(path, "value_mismatch", "实际值与期望值不一致", exp, act)

    expected_document = expected.model_dump(mode="json")
    actual_document = actual.model_dump(mode="json")
    visit(expected_document, actual_document, "$")

    passed = not issues
    compared_leaf_count = max(_count_leaves(expected_document), 1)
    score = 100.0 if passed else max(0.0, 100.0 * (1 - len(issues) / compared_leaf_count))
    if passed:
        explanation = "结果与标准答案一致。"
    else:
        shown = min(len(issues), policy.max_issues)
        explanation = f"发现 {shown} 处差异，请根据 issues 中的路径、期望值和实际值逐项检查。"
        if shown == policy.max_issues:
            explanation += " 差异数量已达到展示上限。"

    return GradeReport(
        grade_id=str(uuid4()),
        actual_result_id=actual_result_id,
        passed=passed,
        score=round(score, 2),
        explanation=explanation,
        issues=issues,
    )


def _count_leaves(value: Any) -> int:
    if isinstance(value, dict):
        return sum(_count_leaves(item) for item in value.values())
    if isinstance(value, list):
        return sum(_count_leaves(item) for item in value)
    return 1
