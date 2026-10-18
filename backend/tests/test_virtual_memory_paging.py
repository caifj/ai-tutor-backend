"""案例2 虚拟内存分页模拟器代码评测测试。"""

import itertools
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ai_tutor_backend import CaseInputError, CaseRegistry, DataType, ExecutionContext
from ai_tutor_backend.app import create_app
from ai_tutor_backend.repository import SQLiteResultRepository

from cases import register_cases
from cases.case_02_virtual_memory_paging import VirtualMemoryPagingCase
from cases.case_02_virtual_memory_paging import paging_reference as reference
from cases.case_02_virtual_memory_paging.evaluator import (
    FUNCTIONALITY_MAX_SCORE,
    evaluate_python_source,
)

CONTEXT = ExecutionContext(request_id="test-request")
TESTCASE_DIR = Path(__file__).resolve().parents[1] / "testcase"

MINIMAL_SOURCE = """
def simulate(sequence):
    frames = [None] * 4
    for page in sequence:
        if page not in frames:
            frames[0] = page
    return frames
"""


def _execute(source: str) -> object:
    return VirtualMemoryPagingCase().execute(
        {"filename": "student.py", "source_code": source},
        CONTEXT,
    )


def _dataset(payload, name: str) -> dict:
    return next(dataset for dataset in payload.datasets if dataset.name == name)


def _client() -> TestClient:
    registry = CaseRegistry()
    register_cases(registry)
    return TestClient(
        create_app(registry=registry, repository=SQLiteResultRepository(":memory:"))
    )


def _submit(source: str, submitter: str = "student-a") -> dict:
    response = _client().post(
        "/api/v1/executions",
        json={
            "case_id": "os.virtual-memory-paging",
            "input": {"filename": "student.py", "source_code": source},
            "metadata": {"submitter": submitter},
        },
    )
    assert response.status_code == 200
    return response.json()["payload"]


class TestPagingReference:
    """参考分页模拟器测试。"""

    def test_reference_sequence_is_deterministic(self):
        """参考序列必须完全确定，且覆盖预期逻辑页。"""

        assert reference.REFERENCE_SEQUENCE == reference.build_reference_sequence()
        assert len(reference.REFERENCE_SEQUENCE) == 96
        assert set(reference.REFERENCE_SEQUENCE) == set(range(reference.REFERENCE_PAGE_SPAN))

    def test_no_page_fault_when_memory_is_large_enough(self):
        """内存足够容纳整个工作集时每次访问都要调页。"""

        result = reference.simulate((0, 1, 2, 3), 4, reference.ALGORITHM_FIFO)
        assert result.page_faults == 4
        assert result.frame_hits == 0
        assert result.page_fault_rate == 100.0

    def test_hit_when_page_stays_resident(self):
        """页面在内存中驻留时不产生缺页。"""

        result = reference.simulate((0, 1, 2, 0, 1, 0), 3, reference.ALGORITHM_LRU)
        assert result.page_faults == 3
        assert result.page_fault_rate == 50.0

    def test_belady_reference_values(self):
        """复现教材中 Belady 异常引用串的经典缺页次数。"""

        core = reference.BELADY_CORE
        assert reference.simulate(core, 3, reference.ALGORITHM_FIFO).page_faults == 9
        assert reference.simulate(core, 3, reference.ALGORITHM_LRU).page_faults == 10
        assert reference.simulate(core, 3, reference.ALGORITHM_OPT).page_faults == 7
        assert reference.simulate(core, 4, reference.ALGORITHM_FIFO).page_faults == 10
        assert reference.simulate(core, 4, reference.ALGORITHM_LRU).page_faults == 8
        assert reference.simulate(core, 4, reference.ALGORITHM_OPT).page_faults == 6

    def test_optimal_never_worse_than_others(self):
        """OPT 是最优策略，缺页次数不应多于 FIFO 与 LRU。"""

        for frame_count in reference.FRAME_COUNT_RANGE:
            optimal = reference.simulate(
                reference.REFERENCE_SEQUENCE, frame_count, reference.ALGORITHM_OPT
            )
            fifo = reference.simulate(
                reference.REFERENCE_SEQUENCE, frame_count, reference.ALGORITHM_FIFO
            )
            lru = reference.simulate(
                reference.REFERENCE_SEQUENCE, frame_count, reference.ALGORITHM_LRU
            )
            assert optimal.page_faults <= fifo.page_faults
            assert optimal.page_faults <= lru.page_faults

    def test_fault_rate_curve_is_monotonic(self):
        """页框数增加时缺页率不应上升。"""

        for algorithm in reference.ALGORITHMS:
            rates = [
                sample.page_fault_rate
                for sample in reference.fault_rate_curve()
                if sample.algorithm == algorithm
            ]
            assert rates == sorted(rates, reverse=True)
            assert rates[-1] < rates[0]

    def test_curve_covers_every_algorithm_and_frame_count(self):
        """曲线数据覆盖三种算法与全部页框档位。"""

        samples = reference.fault_rate_curve()
        assert len(samples) == len(reference.ALGORITHMS) * len(reference.FRAME_COUNT_RANGE)
        assert {sample.algorithm for sample in samples} == set(reference.ALGORITHMS)
        assert {sample.frame_count for sample in samples} == set(reference.FRAME_COUNT_RANGE)

    def test_average_fault_rate_selects_optimal(self):
        """全区间平均缺页率最低的应是 OPT。"""

        averages = reference.average_fault_rates()
        assert averages[reference.ALGORITHM_OPT] < averages[reference.ALGORITHM_FIFO]
        assert reference.best_algorithm()[0] == reference.ALGORITHM_OPT

    def test_belady_anomaly_detected(self):
        """参考序列应能复现 FIFO 反优于 LRU 的 Belady 异常。"""

        anomaly = reference.find_belady_anomaly(reference.fault_rate_curve())
        assert anomaly is not None
        frame_count, fifo_rate, lru_rate = anomaly
        assert fifo_rate < lru_rate
        assert frame_count in reference.FRAME_COUNT_RANGE

    def test_occupancy_timeline_covers_every_step(self):
        """页框占用时间线连续覆盖整个访问序列。"""

        segments = reference.occupancy_timeline()
        assert segments
        by_frame: dict[int, list] = {}
        for segment in segments:
            by_frame.setdefault(segment.frame_index, []).append(segment)
        for frame_segments in by_frame.values():
            assert frame_segments[0].start == 0
            assert frame_segments[-1].end == len(reference.REFERENCE_SEQUENCE)
            for previous, current in itertools.pairwise(frame_segments):
                assert previous.end == current.start

    @pytest.mark.parametrize(
        ("frame_count", "algorithm"),
        [(0, reference.ALGORITHM_FIFO), (-1, reference.ALGORITHM_LRU), (2, "UNKNOWN")],
    )
    def test_invalid_parameters_rejected(self, frame_count: int, algorithm: str):
        """非法页框数或未知算法必须报错。"""

        with pytest.raises(ValueError):
            reference.simulate((0, 1), frame_count, algorithm)


class TestEvaluator:
    """静态分析器测试。"""

    def test_reference_sample_passes_all_checks(self):
        """仓库中的正确示例应通过全部功能检查且没有代码问题。"""

        source = (TESTCASE_DIR / "case2_correct.py").read_text(encoding="utf-8")
        report = evaluate_python_source(source)
        assert report.syntax_valid is True
        assert report.tests_total == 8
        assert report.tests_passed == 8
        assert report.functionality_score == 80.0
        assert report.overall_score == 80.0
        assert report.overall_score == FUNCTIONALITY_MAX_SCORE
        assert report.issues == []

    def test_failed_sample_reports_missing_features(self):
        """未通过示例应报告缺失的置换算法与曲线扫描。"""

        source = (TESTCASE_DIR / "case2_incorrect.py").read_text(encoding="utf-8")
        report = evaluate_python_source(source)
        assert report.syntax_valid is True
        failed = {item["check_id"] for item in report.functional_checks if not item["passed"]}
        assert {"FIFO_REPLACEMENT", "LRU_REPLACEMENT", "OPT_REPLACEMENT"} <= failed
        assert "FRAME_SWEEP" in failed
        codes = {issue["code"] for issue in report.issues}
        assert "NO_REPLACEMENT_ALGORITHM" in codes
        assert "UNSAFE_DYNAMIC_EXECUTION" in codes
        assert report.overall_score < 70

    def test_syntax_error(self):
        """语法错误应中断静态分析。"""

        report = evaluate_python_source("def simulate(sequence):\n    return {")
        assert report.syntax_valid is False
        assert report.functional_checks == []
        assert report.issues[0]["severity"] == "error"
        assert report.issues[0]["code"] == "SYNTAX_ERROR"

    def test_docstring_keywords_do_not_count_as_implementation(self):
        """只在文档字符串里提到算法名不应算作已实现。"""

        source = (
            '"""本模块声称实现 FIFO 先进先出、LRU 与 OPT 最佳置换，并维护页表 page_table。"""\n'
            "\n"
            "\n"
            "def run(sequence, frame_count):\n"
            '    """docstring 中提到 belady 与 next_use"""\n'
            "    return len(sequence)\n"
        )
        report = evaluate_python_source(source)
        failed = {item["check_id"] for item in report.functional_checks if not item["passed"]}
        assert {"FIFO_REPLACEMENT", "LRU_REPLACEMENT", "OPT_REPLACEMENT"} <= failed

    def test_minimal_code_fails_feature_checks(self):
        """只有单一固定页框的实现无法通过多档扫描检查。"""

        report = evaluate_python_source(MINIMAL_SOURCE)
        assert report.syntax_valid is True
        assert report.check("FRAME_SWEEP")["passed"] is False
        codes = {issue["code"] for issue in report.issues}
        assert "FIXED_FRAME_COUNT" in codes
        assert "NO_FRAME_SWEEP" in codes

    def test_address_translation_records_integer_split(self):
        """地址转换检查会记录是否使用整除或取模拆分页号。"""

        source = (
            "def translate_address(logical_address, page_size):\n"
            "    page_no = logical_address // page_size\n"
            "    offset = logical_address % page_size\n"
            "    return page_no, offset\n"
        )
        report = evaluate_python_source(source)
        check = report.check("ADDRESS_TRANSLATION")
        assert check["passed"] is True
        assert "整除" in check["evidence"]

    def test_float_only_division_is_reported(self):
        """全文只有浮点除法且实现了页表时给出告警。"""

        source = (
            "def build_page_table(frame_count):\n"
            "    page_table = {}\n"
            "    for page in range(frame_count):\n"
            "        page_table[page] = page / 2\n"
            "    return page_table\n"
        )
        report = evaluate_python_source(source)
        codes = {issue["code"] for issue in report.issues}
        assert "FLOAT_DIVISION_FOR_PAGE" in codes

    def test_case_does_not_duplicate_base_quality_scoring(self):
        """PEP8 与模块化已上移基座，案例评测器不再自行评分。"""

        source = (TESTCASE_DIR / "case2_correct.py").read_text(encoding="utf-8")
        report = evaluate_python_source(source)
        assert not hasattr(report, "quality_scores")
        assert report.overall_score == FUNCTIONALITY_MAX_SCORE


class TestAdapter:
    """适配器测试。"""

    def test_descriptor(self):
        """描述符字段与基座约定一致。"""

        descriptor = VirtualMemoryPagingCase().descriptor
        assert descriptor.case_id == "os.virtual-memory-paging"
        assert descriptor.course_number == 2
        assert descriptor.input_schema["x-ui-mode"] == "python-file"
        assert descriptor.input_schema["x-accepted-extension"] == ".py"
        assert "fault_rate_curve" in descriptor.output_datasets
        assert "frame_fault_rate_table" in descriptor.output_datasets
        assert "paging_issues" in descriptor.output_datasets
        assert descriptor.python_static_evaluation is True
        # 基座统一注入 quality_scores 与 code_issues，案例不自行声明。
        assert "quality_scores" not in descriptor.output_datasets
        assert "code_issues" not in descriptor.output_datasets

    def test_validate_input_valid(self):
        """合法输入应被接受。"""

        submission = VirtualMemoryPagingCase()._validate_input(
            {"filename": "student.py", "source_code": "def simulate(sequence):\n    return []"}
        )
        assert submission.filename == "student.py"

    def test_validate_input_invalid_extension(self):
        """非 .py 文件应被拒绝。"""

        with pytest.raises(CaseInputError, match="代码文件输入不合法"):
            VirtualMemoryPagingCase()._validate_input(
                {"filename": "student.txt", "source_code": "print(1)"}
            )

    def test_validate_input_missing_field(self):
        """缺少源代码字段应被拒绝。"""

        with pytest.raises(CaseInputError):
            VirtualMemoryPagingCase()._validate_input({"filename": "student.py"})

    def test_payload_contains_reference_paging_datasets(self):
        """评测结果必须包含缺页率对应表与曲线数据。"""

        payload = _execute("def simulate(sequence):\n    return []\n")
        assert len(_dataset(payload, "frame_fault_rate_table").rows) == 27
        assert len(_dataset(payload, "fault_rate_curve").rows) == 27
        assert _dataset(payload, "frame_occupancy_timeline").rows
        assert _dataset(payload, "functional_tests").rows

    def test_fault_rate_curve_matches_reference(self):
        """曲线数据与参考模拟器逐点一致。"""

        payload = _execute("def simulate(sequence):\n    return []\n")
        rows = _dataset(payload, "fault_rate_curve").rows
        expected = {
            (sample.algorithm, sample.frame_count): sample.page_fault_rate
            for sample in reference.fault_rate_curve()
        }
        assert len(rows) == len(expected)
        for row in rows:
            key = (row["algorithm_name"], row["frame_count"])
            assert expected[key] == row["page_fault_rate"]

    def test_fault_rate_table_columns_are_consistent(self):
        """对应表的列类型与行数据一致。"""

        payload = _execute("def simulate(sequence):\n    return []\n")
        dataset = _dataset(payload, "frame_fault_rate_table")
        types = {column.key: column.data_type for column in dataset.columns}
        assert types["algorithm_name"] == DataType.STRING
        assert types["frame_count"] == DataType.INTEGER
        assert types["page_fault_rate"] == DataType.NUMBER
        for row in dataset.rows:
            assert isinstance(row["frame_count"], int)
            assert isinstance(row["page_fault_rate"], float)
            assert row["page_faults"] + row["frame_hits"] == row["reference_length"]

    def test_metrics_contain_overall_score(self):
        """查重扣分依赖 metrics 中的总分。"""

        source = (TESTCASE_DIR / "case2_correct.py").read_text(encoding="utf-8")
        payload = _execute(source)
        assert payload.metrics["overall_score"] == FUNCTIONALITY_MAX_SCORE
        assert payload.metrics["best_algorithm"] == reference.ALGORITHM_OPT
        assert payload.metrics["curve_sample_count"] == 27
        assert payload.metrics["reference_sequence_length"] == len(
            reference.REFERENCE_SEQUENCE
        )

    def test_syntax_error_payload_reports_error(self):
        """语法错误时给出错误诊断而不是静默返回空数据。"""

        payload = _execute("def simulate(sequence:\n    return []\n")
        assert _dataset(payload, "functional_tests").rows == []
        assert "语法解析失败" in payload.summary
        assert payload.diagnostics[0].code == "STATIC_ANALYSIS_ONLY"

    def test_statically_never_executes_student_code(self):
        """评测不依赖运行上下文，只做静态分析。"""

        payload = _execute("def simulate(sequence):\n    raise SystemExit(1)\n")
        codes = {item.code for item in payload.diagnostics}
        assert "STATIC_ANALYSIS_ONLY" in codes
        assert "CODE_RUNNER_UNAVAILABLE" not in codes

    def test_missing_frame_sweep_warning(self):
        """未扫描多档页框数时给出警告。"""

        payload = _execute(MINIMAL_SOURCE)
        codes = {item.code for item in payload.diagnostics}
        assert "MISSING_FRAME_SWEEP" in codes

    def test_results_are_reproducible(self):
        """相同输入重复执行必须得到完全一致的缺页率数据。"""

        source = (TESTCASE_DIR / "case2_correct.py").read_text(encoding="utf-8")
        first = _execute(source)
        second = _execute(source)
        assert first.metrics == second.metrics
        assert [dataset.rows for dataset in first.datasets] == [
            dataset.rows for dataset in second.datasets
        ]


class TestIntegration:
    """与基座的集成测试。"""

    def test_register_cases(self):
        """案例应能在统一注册入口中按课程 2 暴露。"""

        registry = CaseRegistry()
        register_cases(registry)
        adapter = registry.get("os.virtual-memory-paging")
        assert isinstance(adapter, VirtualMemoryPagingCase)
        assert adapter.descriptor.course_number == 2
        assert adapter.descriptor.catalog_visible is True

    def test_base_static_evaluation_adds_quality_scores(self):
        """基座应为声明 python_static_evaluation 的案例注入质量与通用问题数据集。"""

        source = (TESTCASE_DIR / "case2_correct.py").read_text(encoding="utf-8")
        payload = _submit(source)
        names = {dataset["name"] for dataset in payload["datasets"]}
        assert "quality_scores" in names
        assert "code_issues" in names
        assert "paging_issues" in names
        quality_rows = next(
            dataset["rows"]
            for dataset in payload["datasets"]
            if dataset["name"] == "quality_scores"
        )
        assert {"PEP8 规范", "模块化程度"} <= {row["dimension"] for row in quality_rows}
        assert payload["metrics"]["syntax_valid"] is True
        assert payload["metrics"]["case_score"] == FUNCTIONALITY_MAX_SCORE
        assert payload["metrics"]["overall_score"] == 100.0
        assert payload["metrics"]["pep8_score"] > 0
        assert "基座静态测评" in payload["summary"]

    def test_base_static_evaluation_reports_syntax_error(self):
        """语法错误由基座统一报告为 PYTHON_SYNTAX_ERROR。"""

        payload = _submit("def simulate(sequence:\n    return []\n")
        codes = {item["code"] for item in payload["diagnostics"]}
        assert "PYTHON_SYNTAX_ERROR" in codes
        assert payload["metrics"]["syntax_valid"] is False
        assert payload["metrics"]["overall_score"] == 0.0

    def test_catalog_exposes_case_for_course_two(self):
        """课程目录中应能按课程号看到案例 2。"""

        response = _client().get("/api/v1/cases")
        assert response.status_code == 200
        item = next(
            case
            for case in response.json()["items"]
            if case["case_id"] == "os.virtual-memory-paging"
        )
        assert item["course_number"] == 2
        assert "fault_rate_curve" in item["output_datasets"]