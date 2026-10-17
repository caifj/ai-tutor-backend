"""案例7：SQL 执行计划可视化工具（案例适配器）。

三种工作模式：
- analyze：离线解析 EXPLAIN 文本，输出索引使用情况与全表扫描判定；
- live：通过 mysql-connector-python 连接真实 MySQL 执行 EXPLAIN 后走 analyze 管道；
- btree：基于索引样本键构建 B+ 树并模拟一次查找，输出查找路径数据。
"""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ai_tutor_backend import (
    CaseAdapter,
    CaseDescriptor,
    CaseInputError,
    ColumnSpec,
    Dataset,
    DataType,
    Diagnostic,
    DiagnosticLevel,
    ExecutionContext,
    ResultPayload,
)

from .btree import build_btree, flatten_tree, simulate_lookup
from .connector import LiveConnector, resolve_live_settings
from .plan_parser import PlanAnalysis, analyze_plan, parse_plan


class SqlCaseInput(BaseModel):
    """SQL 执行计划可视化工具的输入（只校验本案例需要的字段）。"""

    model_config = ConfigDict(extra="forbid")

    operation: Literal["analyze", "live", "btree"] = "analyze"
    sql: str | None = Field(default=None, max_length=10_000)
    plan_text: str | None = Field(default=None, max_length=50_000)
    table_name: str | None = Field(default=None, max_length=128)
    index_name: str | None = Field(default=None, max_length=128)
    sample_keys: str | None = Field(default=None, max_length=10_000)
    lookup_key: str | None = Field(default=None, max_length=256)
    btree_order: int = Field(default=5, ge=3, le=101)
    db_url: str | None = Field(default=None, max_length=512)
    db_user: str | None = Field(default=None, max_length=128)
    db_password: str | None = Field(default=None, max_length=256)


class SqlExecutionPlanCase(CaseAdapter):
    """案例7：解析 SQL 执行计划并可视化索引 B+ 树查找过程。"""

    @property
    def descriptor(self) -> CaseDescriptor:
        return CaseDescriptor(
            case_id="database.sql-execution-plan",
            name="SQL执行计划可视化工具",
            course="数据库系统",
            description=(
                "解析 MySQL/PostgreSQL 执行计划文本，输出索引使用情况与全表扫描判定，"
                "并通过 B+ 树模拟演示索引查找路径；支持在线连接真实数据库获取 EXPLAIN。"
            ),
            version="1.0.0",
            input_schema=SqlCaseInput.model_json_schema(),
            output_datasets=[
                "execution_plan",
                "index_usage",
                "full_scan_findings",
                "btree_structure",
                "btree_lookup_path",
            ],
        )

    def execute(self, input_data: dict, context: ExecutionContext) -> ResultPayload:
        try:
            case_input = SqlCaseInput.model_validate(input_data)
        except ValidationError as exc:
            raise CaseInputError(
                "案例输入不合法",
                {"errors": exc.errors(include_context=False, include_url=False)},
            ) from exc

        if case_input.operation == "btree":
            return self._execute_btree(case_input)

        plan_lines, sampled_keys = self._obtain_plan_lines(case_input)
        analysis = analyze_plan(parse_plan(plan_lines))
        if analysis.node_count == 0:
            raise CaseInputError(
                "执行计划文本为空或无法识别",
                {"operation": case_input.operation},
            )
        return self._build_analysis_result(case_input, analysis, sampled_keys)

    # ------------------------------------------------------------------ #
    # 内部实现
    # ------------------------------------------------------------------ #

    def _obtain_plan_lines(self, case_input: SqlCaseInput) -> tuple[list[str], list]:
        """返回 (执行计划文本行, 从数据库采样的索引键)。"""
        if case_input.operation == "analyze":
            if not case_input.plan_text or not case_input.plan_text.strip():
                raise CaseInputError(
                    "analyze 模式需要提供 plan_text（EXPLAIN 输出文本）",
                    {"operation": "analyze"},
                )
            return case_input.plan_text.splitlines(), []

        # live 模式
        sql = (case_input.sql or "").strip()
        if not sql:
            raise CaseInputError("live 模式需要提供 sql", {"operation": "live"})
        if not sql.upper().startswith("SELECT"):
            raise CaseInputError(
                "live 模式仅支持 SELECT 查询（只读分析）",
                {"operation": "live", "sql": sql[:100]},
            )
        settings = resolve_live_settings(
            url=case_input.db_url,
            user=case_input.db_user,
            password=case_input.db_password,
        )
        if settings is None:
            raise CaseInputError(
                "实时分析不可用：缺少数据库连接配置"
                "（db_url 形如 localhost:3306/test_db，加 db_user/db_password，或对应环境变量）",
                {"operation": "live"},
            )
        connector = LiveConnector(settings)
        try:
            plan_lines = connector.get_execution_plan(sql)
            sampled_keys: list = []
            if case_input.table_name and case_input.index_name:
                sampled_keys = connector.get_index_sample_keys(
                    case_input.table_name, case_input.index_name
                )
            return plan_lines, sampled_keys
        except Exception as exc:  # noqa: BLE001 —— 外部依赖错误统一转 CaseInputError
            raise CaseInputError(
                "实时分析不可用：连接数据库或执行 EXPLAIN 失败",
                {"operation": "live", "reason": str(exc)[:500]},
            ) from exc

    def _build_analysis_result(
        self,
        case_input: SqlCaseInput,
        analysis: PlanAnalysis,
        sampled_keys: list | None = None,
    ) -> ResultPayload:
        datasets = [
            _execution_plan_dataset(analysis),
            _index_usage_dataset(analysis),
            _full_scan_dataset(analysis),
        ]

        diagnostics: list[Diagnostic] = []
        if analysis.full_scan_findings:
            severity_rank = {"high": 3, "medium": 2, "low": 1, "info": 0}
            worst = max(
                (f["severity"] for f in analysis.full_scan_findings),
                key=lambda s: severity_rank.get(s, 0),
            )
            diagnostics.append(
                Diagnostic(
                    code="FULL_TABLE_SCAN",
                    level=DiagnosticLevel.WARNING if worst in {"high", "medium"} else DiagnosticLevel.INFO,
                    message=f"检测到 {len(analysis.full_scan_findings)} 处全表扫描，建议关注索引优化。",
                    details={"findings": len(analysis.full_scan_findings)},
                )
            )
        else:
            diagnostics.append(
                Diagnostic(
                    code="PLAN_HEALTHY",
                    level=DiagnosticLevel.INFO,
                    message="未检测到全表扫描，执行计划使用了索引访问。",
                )
            )

        # 附带 B+ 树演示（提供了样本键时）
        metrics: dict = {
            "node_count": analysis.node_count,
            "max_estimated_rows": analysis.max_estimated_rows,
            "max_cost": analysis.max_cost,
            "full_scan_count": len(analysis.full_scan_findings),
        }
        sample_keys = _parse_sample_keys(case_input.sample_keys)
        if not sample_keys and sampled_keys:
            # 数据库采样的键统一做类型转换，保证可 JSON 序列化
            sample_keys = [_coerce_key(str(key)) for key in sampled_keys]
        if sample_keys:
            btree_datasets, btree_metrics, btree_diag = self._build_btree_payload(
                sample_keys, case_input
            )
            datasets.extend(btree_datasets)
            metrics.update(btree_metrics)
            diagnostics.append(btree_diag)

        summary_parts = [
            f"已解析 {analysis.node_count} 个执行计划节点，"
            f"最大预估扫描 {analysis.max_estimated_rows} 行。"
        ]
        if analysis.issues:
            summary_parts.append(f"发现 {len(analysis.issues)} 个性能问题。")
        if analysis.suggestions:
            summary_parts.append(f"给出 {len(analysis.suggestions)} 条优化建议。")

        diagnostics.append(
            Diagnostic(
                code="PLAN_ANALYSIS_COMPLETED",
                level=DiagnosticLevel.INFO,
                message="执行计划分析完成。",
                details={
                    "issues": analysis.issues[:20],
                    "suggestions": analysis.suggestions[:20],
                    "details": analysis.details[:20],
                },
            )
        )

        return ResultPayload(
            summary="".join(summary_parts),
            datasets=datasets,
            metrics=metrics,
            diagnostics=diagnostics,
        )

    def _execute_btree(self, case_input: SqlCaseInput) -> ResultPayload:
        sample_keys = _parse_sample_keys(case_input.sample_keys)
        if not sample_keys:
            raise CaseInputError(
                "btree 模式需要提供 sample_keys（逗号分隔或 JSON 数组的索引样本键）",
                {"operation": "btree"},
            )
        datasets, metrics, diagnostic = self._build_btree_payload(sample_keys, case_input)
        lookup_key = metrics["lookup_key"]
        found = metrics["lookup_found"]
        return ResultPayload(
            summary=(
                f"已构建 B+ 树（{metrics['btree_node_count']} 个节点，"
                f"{metrics['btree_height']} 层），模拟查找键 {lookup_key}："
                f"{'找到' if found else '未找到'}，共 {metrics['lookup_steps']} 步。"
            ),
            datasets=datasets,
            metrics=metrics,
            diagnostics=[
                diagnostic,
                Diagnostic(
                    code="BTREE_LOOKUP_COMPLETED",
                    level=DiagnosticLevel.INFO,
                    message="B+ 树查找路径模拟完成。",
                ),
            ],
        )

    def _build_btree_payload(
        self, sample_keys: list[int | float | str], case_input: SqlCaseInput
    ) -> tuple[list[Dataset], dict, Diagnostic]:
        numeric = all(isinstance(key, (int, float)) for key in sample_keys)
        try:
            root = build_btree(sample_keys, order=case_input.btree_order)
        except ValueError as exc:
            raise CaseInputError("无法构建 B+ 树", {"reason": str(exc)}) from exc

        lookup_value = _resolve_lookup_key(case_input.lookup_key, sample_keys, numeric)
        found, steps = simulate_lookup(root, lookup_value, numeric=numeric)
        path_ids = {step["node_id"] for step in steps}

        structure_rows = [
            {
                "node_id": node.node_id,
                "level": node.level,
                "keys": list(node.keys),
                "is_leaf": node.is_leaf,
                "children": [child.node_id for child in node.children],
                "on_lookup_path": node.node_id in path_ids,
            }
            for node in flatten_tree(root)
        ]
        height = max(node.level for node in flatten_tree(root)) + 1

        datasets = [
            Dataset(
                name="btree_structure",
                title="B+ 树结构",
                columns=[
                    ColumnSpec(key="node_id", title="节点编号", data_type=DataType.INTEGER),
                    ColumnSpec(key="level", title="层级", data_type=DataType.INTEGER),
                    ColumnSpec(key="keys", title="节点键", data_type=DataType.ARRAY),
                    ColumnSpec(key="is_leaf", title="是否叶子", data_type=DataType.BOOLEAN),
                    ColumnSpec(key="children", title="子节点", data_type=DataType.ARRAY),
                    ColumnSpec(
                        key="on_lookup_path", title="在查找路径上", data_type=DataType.BOOLEAN
                    ),
                ],
                rows=structure_rows,
            ),
            Dataset(
                name="btree_lookup_path",
                title="B+ 树查找路径",
                columns=[
                    ColumnSpec(key="step", title="步骤", data_type=DataType.INTEGER),
                    ColumnSpec(key="node_id", title="节点编号", data_type=DataType.INTEGER),
                    ColumnSpec(key="level", title="层级", data_type=DataType.INTEGER),
                    ColumnSpec(key="node_keys", title="节点键", data_type=DataType.ARRAY),
                    ColumnSpec(key="decision", title="决策说明", data_type=DataType.STRING),
                    ColumnSpec(key="found", title="是否找到", data_type=DataType.BOOLEAN),
                ],
                rows=steps,
            ),
        ]
        metrics = {
            "btree_order": case_input.btree_order,
            "btree_node_count": len(structure_rows),
            "btree_height": height,
            "lookup_key": lookup_value,
            "lookup_found": found,
            "lookup_steps": len(steps),
        }
        diagnostic = Diagnostic(
            code="BTREE_BUILT",
            level=DiagnosticLevel.INFO,
            message=f"B+ 树构建完成：{len(structure_rows)} 个节点，{height} 层。",
            details={"numeric_keys": numeric},
        )
        return datasets, metrics, diagnostic


# ---------------------------------------------------------------------- #
# 数据集构建
# ---------------------------------------------------------------------- #


def _execution_plan_dataset(analysis: PlanAnalysis) -> Dataset:
    rows: list[dict] = []

    def visit(node) -> None:
        rows.append(
            {
                "node_id": node.node_id,
                "level": node.level,
                "operation": node.operation,
                "table_name": node.table,
                "access_type": node.access_type,
                "key_used": node.key_used or None,
                "rows_estimated": node.rows_estimated,
                "cost_start": node.cost_start,
                "cost_end": node.cost_end,
                "filter": node.filter or None,
                "raw_text": node.raw_text,
            }
        )
        for child in node.children:
            visit(child)

    for root in analysis.roots:
        visit(root)

    return Dataset(
        name="execution_plan",
        title="执行计划节点",
        columns=[
            ColumnSpec(key="node_id", title="节点编号", data_type=DataType.INTEGER),
            ColumnSpec(key="level", title="层级", data_type=DataType.INTEGER),
            ColumnSpec(key="operation", title="操作", data_type=DataType.STRING),
            ColumnSpec(key="table_name", title="表", data_type=DataType.STRING),
            ColumnSpec(key="access_type", title="访问类型", data_type=DataType.STRING),
            ColumnSpec(key="key_used", title="使用索引", data_type=DataType.STRING, nullable=True),
            ColumnSpec(
                key="rows_estimated", title="预估行数", data_type=DataType.INTEGER, nullable=True
            ),
            ColumnSpec(
                key="cost_start", title="起始成本", data_type=DataType.NUMBER, nullable=True
            ),
            ColumnSpec(key="cost_end", title="结束成本", data_type=DataType.NUMBER, nullable=True),
            ColumnSpec(key="filter", title="过滤条件", data_type=DataType.STRING, nullable=True),
            ColumnSpec(key="raw_text", title="原始文本", data_type=DataType.STRING),
        ],
        rows=rows,
    )


def _index_usage_dataset(analysis: PlanAnalysis) -> Dataset:
    return Dataset(
        name="index_usage",
        title="索引使用情况",
        columns=[
            ColumnSpec(key="table_name", title="表", data_type=DataType.STRING),
            ColumnSpec(key="access_type", title="访问类型", data_type=DataType.STRING),
            ColumnSpec(key="key_used", title="使用索引", data_type=DataType.STRING, nullable=True),
            ColumnSpec(key="used_index", title="是否用索引", data_type=DataType.BOOLEAN),
            ColumnSpec(key="assessment", title="评估", data_type=DataType.STRING),
        ],
        rows=analysis.index_usage,
    )


def _full_scan_dataset(analysis: PlanAnalysis) -> Dataset:
    return Dataset(
        name="full_scan_findings",
        title="全表扫描判定",
        columns=[
            ColumnSpec(key="table_name", title="表", data_type=DataType.STRING),
            ColumnSpec(
                key="rows_estimated", title="预估行数", data_type=DataType.INTEGER, nullable=True
            ),
            ColumnSpec(key="severity", title="严重程度", data_type=DataType.STRING),
            ColumnSpec(key="issue", title="问题", data_type=DataType.STRING),
            ColumnSpec(key="suggestion", title="建议", data_type=DataType.STRING),
        ],
        rows=analysis.full_scan_findings,
    )


# ---------------------------------------------------------------------- #
# 工具函数
# ---------------------------------------------------------------------- #


def _parse_sample_keys(raw: str | None) -> list[int | float | str]:
    """解析样本键：JSON 数组或逗号分隔字符串；能转数字的转数字。"""

    if raw is None or not raw.strip():
        return []
    text = raw.strip()
    items: list
    if text.startswith("["):
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise CaseInputError("sample_keys 不是合法的 JSON 数组", {"reason": str(exc)}) from exc
        if not isinstance(parsed, list):
            raise CaseInputError("sample_keys 必须是 JSON 数组或逗号分隔字符串")
        items = parsed
    else:
        items = [part.strip() for part in text.split(",") if part.strip()]

    keys: list[int | float | str] = []
    for item in items:
        keys.append(_coerce_key(item))
    return keys


def _coerce_key(item) -> int | float | str:
    if isinstance(item, (int, float)) and not isinstance(item, bool):
        return item
    text = str(item)
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        return text


def _resolve_lookup_key(
    raw: str | None, sample_keys: list[int | float | str], numeric: bool
) -> int | float | str:
    """查找键缺省时取样本中位键。"""

    if raw is not None and raw.strip():
        return _coerce_key(raw.strip())
    ordered = sorted(sample_keys, key=lambda v: (0, v) if isinstance(v, (int, float)) else (1, str(v)))
    return ordered[len(ordered) // 2]
