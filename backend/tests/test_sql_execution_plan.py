from __future__ import annotations

import pytest

from ai_tutor_backend.models import ExecutionContext
from ai_tutor_backend.registry import CaseInputError, CaseRegistry
from cases import register_cases
from cases.case_07_sql_execution_plan import SqlExecutionPlanCase
from cases.case_07_sql_execution_plan.btree import build_btree, simulate_lookup
from cases.case_07_sql_execution_plan.plan_parser import analyze_plan, parse_plan

CONTEXT = ExecutionContext(request_id="test-request")

MYSQL_FULL_SCAN_PLAN = (
    " -> id=1, select_type=SIMPLE, table=tb_task, type=ALL, key=NULL, rows=15000, Extra=NULL"
)
MYSQL_INDEX_PLAN = (
    " -> id=1, select_type=SIMPLE, table=tb_task, type=ref, key=idx_status, "
    "rows=20, Extra=Using where"
)
POSTGRES_PLAN = """Seq Scan on orders  (cost=0.00..183.34 rows=10000 width=4)
  Filter: (amount > 100)"""


def _dataset(result, name):
    return next(ds for ds in result.datasets if ds.name == name)


def test_parse_mysql_full_scan_line() -> None:
    roots = parse_plan([MYSQL_FULL_SCAN_PLAN])
    assert len(roots) == 1
    node = roots[0]
    assert node.table == "tb_task"
    assert node.access_type == "ALL"
    assert node.key_used == ""
    assert node.rows_estimated == 15000
    assert node.operation == "Seq Scan"

    analysis = analyze_plan(roots)
    assert analysis.full_scan_findings[0]["severity"] == "high"
    assert analysis.index_usage[0]["used_index"] is False


def test_parse_mysql_index_line() -> None:
    analysis = analyze_plan(parse_plan([MYSQL_INDEX_PLAN]))
    assert analysis.full_scan_findings == []
    usage = analysis.index_usage[0]
    assert usage["used_index"] is True
    assert usage["key_used"] == "idx_status"


def test_parse_postgres_nested_plan() -> None:
    roots = parse_plan(POSTGRES_PLAN.splitlines())
    assert len(roots) == 1
    node = roots[0]
    assert node.operation == "Seq Scan"
    assert node.table == "orders"
    assert node.rows_estimated == 10000
    assert node.cost_end == pytest.approx(183.34)
    assert "Filter:" in node.filter

    analysis = analyze_plan(roots)
    assert analysis.full_scan_findings[0]["severity"] == "medium"


def test_adapter_analyze_end_to_end() -> None:
    result = SqlExecutionPlanCase().execute(
        {"operation": "analyze", "plan_text": MYSQL_FULL_SCAN_PLAN},
        CONTEXT,
    )
    plan_ds = _dataset(result, "execution_plan")
    assert plan_ds.rows[0]["access_type"] == "ALL"
    assert _dataset(result, "index_usage").rows[0]["used_index"] is False
    assert _dataset(result, "full_scan_findings").rows[0]["severity"] == "high"
    assert result.metrics["full_scan_count"] == 1
    assert any(diag.code == "FULL_TABLE_SCAN" for diag in result.diagnostics)


def test_adapter_analyze_requires_plan_text() -> None:
    with pytest.raises(CaseInputError, match="plan_text"):
        SqlExecutionPlanCase().execute({"operation": "analyze"}, CONTEXT)


def test_adapter_analyze_rejects_unparseable_text() -> None:
    with pytest.raises(CaseInputError, match="为空或无法识别"):
        SqlExecutionPlanCase().execute(
            {"operation": "analyze", "plan_text": "Filter: (amount > 100)"}, CONTEXT
        )


def test_adapter_btree_end_to_end() -> None:
    result = SqlExecutionPlanCase().execute(
        {
            "operation": "btree",
            "sample_keys": "10,20,30,40,50,60,70,80,90,100",
            "lookup_key": "40",
            "btree_order": 4,
        },
        CONTEXT,
    )
    structure = _dataset(result, "btree_structure")
    path = _dataset(result, "btree_lookup_path")
    assert result.metrics["lookup_found"] is True
    assert result.metrics["lookup_key"] == 40
    assert structure.rows[0]["node_id"] == 0
    assert structure.rows[0]["is_leaf"] is False
    path_ids = {row["node_id"] for row in path.rows}
    assert all(
        row["on_lookup_path"] == (row["node_id"] in path_ids) for row in structure.rows
    )
    assert path.rows[-1]["found"] is True


def test_adapter_btree_requires_sample_keys() -> None:
    with pytest.raises(CaseInputError, match="sample_keys"):
        SqlExecutionPlanCase().execute({"operation": "btree"}, CONTEXT)


def test_adapter_live_without_config_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in (
        "AI_TUTOR_SQLCASE_DB_URL",
        "AI_TUTOR_SQLCASE_DB_USER",
        "AI_TUTOR_SQLCASE_DB_PASSWORD",
    ):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(CaseInputError, match="实时分析不可用"):
        SqlExecutionPlanCase().execute(
            {"operation": "live", "sql": "SELECT * FROM tb_task"},
            CONTEXT,
        )


def test_adapter_live_rejects_non_select() -> None:
    with pytest.raises(CaseInputError, match="仅支持 SELECT"):
        SqlExecutionPlanCase().execute(
            {"operation": "live", "sql": "DELETE FROM tb_task"}, CONTEXT
        )


def test_connector_rejects_bad_identifier() -> None:
    from cases.case_07_sql_execution_plan.connector import LiveConnector, LiveSettings

    connector = LiveConnector(
        LiveSettings(host="localhost", database="test_db", user="root", password="root")
    )
    with pytest.raises(ValueError, match="非法标识符"):
        connector.get_index_sample_keys("orders; DROP TABLE users", "id")


def test_btree_lookup_finds_and_misses() -> None:
    root = build_btree([5, 15, 25, 35, 45, 55, 65], order=3)
    found, steps = simulate_lookup(root, 35)
    assert found is True
    assert steps[-1]["found"] is True

    found, steps = simulate_lookup(root, 36)
    assert found is False
    assert steps[-1]["found"] is False


def test_register_cases_includes_sql_case() -> None:
    registry = CaseRegistry()
    register_cases(registry)
    adapter = registry.get("database.sql-execution-plan")
    assert isinstance(adapter, SqlExecutionPlanCase)
