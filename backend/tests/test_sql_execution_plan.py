"""案例7 SQL执行计划可视化工具代码评测测试。"""

import pytest

from ai_tutor_backend import CaseInputError, CaseRegistry, ExecutionContext

from cases import register_cases
from cases.case_07_sql_execution_plan import SqlExecutionPlanCase
from cases.case_07_sql_execution_plan.evaluator import evaluate_python_source


CONTEXT = ExecutionContext(request_id="test-request")


class TestEvaluator:
    """静态分析器测试。"""

    def test_valid_code_with_all_functions(self):
        """测试包含所有必需函数的代码。"""
        source = '''
def parse_explain(plan_text):
    """解析 SQL 执行计划"""
    return {"nodes": [], "index_usage": [], "full_scan_findings": []}

def build_btree(keys, order=3):
    """构建 B+ 树"""
    return {"keys": keys}

def lookup(root, key):
    """B+ 树查找"""
    return [key]
'''
        report = evaluate_python_source(source)
        assert report.syntax_valid is True
        assert report.tests_total == 5
        assert report.tests_passed == 5

    def test_missing_parse_explain(self):
        """测试缺少 parse_explain 函数。"""
        source = '''
def build_btree(keys, order=3):
    return {"keys": keys}

def lookup(root, key):
    return [key]
'''
        report = evaluate_python_source(source)
        assert report.syntax_valid is True
        parse_check = next(c for c in report.functional_checks if c["check_id"] == "PARSE_EXPLAIN")
        assert parse_check["passed"] is False

    def test_syntax_error(self):
        """测试语法错误。"""
        source = "def parse_explain(plan_text):\n    return {"  # 语法错误
        report = evaluate_python_source(source)
        assert report.syntax_valid is False
        assert len(report.issues) > 0
        assert report.issues[0]["severity"] == "error"

    def test_index_analysis_detection(self):
        """测试索引分析逻辑检测。"""
        source = '''
def parse_explain(plan_text):
    # 检查 type 字段，判断索引使用情况
    if "type" in plan_text and "index" in plan_text:
        return {"index_used": True}
    return {"index_used": False}
'''
        report = evaluate_python_source(source)
        index_check = next(c for c in report.functional_checks if c["check_id"] == "INDEX_ANALYSIS")
        assert index_check["passed"] is True

    def test_full_scan_detection(self):
        """测试全表扫描检测。"""
        source = '''
def parse_explain(plan_text):
    # 检测 type=ALL 表示全表扫描
    if "ALL" in plan_text:
        return {"scan_type": "full_scan"}
    return {"scan_type": "index"}
'''
        report = evaluate_python_source(source)
        scan_check = next(c for c in report.functional_checks if c["check_id"] == "FULL_SCAN")
        assert scan_check["passed"] is True


class TestAdapter:
    """适配器测试。"""

    def test_descriptor(self):
        """测试描述符。"""
        case = SqlExecutionPlanCase()
        descriptor = case.descriptor
        assert descriptor.case_id == "database.sql-execution-plan"
        assert descriptor.name == "SQL执行计划可视化工具代码评测"
        assert descriptor.course == "数据库系统"
        assert descriptor.course_number == 7
        assert "functional_tests" in descriptor.output_datasets
        assert "runtime_tests" in descriptor.output_datasets

    def test_validate_input_valid(self):
        """测试有效输入。"""
        case = SqlExecutionPlanCase()
        input_data = {
            "filename": "student.py",
            "source_code": "def parse_explain(plan_text):\n    return {}",
        }
        submission = case._validate_input(input_data)
        assert submission.filename == "student.py"
        assert submission.source_code.startswith("def parse_explain")

    def test_validate_input_invalid_extension(self):
        """测试非法文件扩展名。"""
        case = SqlExecutionPlanCase()
        input_data = {
            "filename": "student.txt",
            "source_code": "def parse_explain(plan_text):\n    return {}",
        }
        with pytest.raises(CaseInputError, match="代码文件输入不合法"):
            case._validate_input(input_data)

    def test_validate_input_missing_field(self):
        """测试缺少必需字段。"""
        case = SqlExecutionPlanCase()
        input_data = {"filename": "student.py"}
        with pytest.raises(CaseInputError):
            case._validate_input(input_data)


class TestIntegration:
    """集成测试。"""

    def test_register_cases(self):
        """测试案例注册。"""
        registry = CaseRegistry()
        register_cases(registry)
        adapter = registry.get("database.sql-execution-plan")
        assert isinstance(adapter, SqlExecutionPlanCase)
        assert adapter.descriptor.course_number == 7


class TestRuntimeHarness:
    """运行时夹具测试。"""

    def test_harness_source_contains_marker(self):
        """测试夹具包含结果标记。"""
        from cases.case_07_sql_execution_plan.runtime_harness import HARNESS_SOURCE
        assert "__AI_TUTOR_CASE7_RESULT__" in HARNESS_SOURCE

    def test_harness_source_contains_tests(self):
        """测试夹具包含测试函数。"""
        from cases.case_07_sql_execution_plan.runtime_harness import HARNESS_SOURCE
        assert "test_parse_explain" in HARNESS_SOURCE
        assert "test_btree" in HARNESS_SOURCE
