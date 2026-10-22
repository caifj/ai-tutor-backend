from pathlib import Path

from cases.case_01_process_scheduler import ProcessSchedulerCase
from cases.case_03_network_protocol_analyzer import NetworkProtocolAnalyzerCase
from cases.case_05_alg_complex_analyzer import AlgorithmComplexityAnalyzerCase
from cases.case_07_sql_execution_plan import SqlExecutionPlanCase
from cases.case_08_compiler_frontend import MiniCompilerFrontendCase
from cases.examples.demo_case_package import EchoCase

CASES = (
    ProcessSchedulerCase,
    NetworkProtocolAnalyzerCase,
    AlgorithmComplexityAnalyzerCase,
    SqlExecutionPlanCase,
    MiniCompilerFrontendCase,
    EchoCase,
)


def test_every_case_declares_input_and_output_templates() -> None:
    for case_type in CASES:
        descriptor = case_type().descriptor
        assert descriptor.input_template.strip(), descriptor.case_id
        assert descriptor.output_summary.strip(), descriptor.case_id
        assert descriptor.output_template.strip(), descriptor.case_id
        assert descriptor.starter_code.strip(), descriptor.case_id
        assert descriptor.starter_filename, descriptor.case_id


def test_python_cases_explain_parameters_and_returns() -> None:
    for case_type in CASES[:-1]:
        descriptor = case_type().descriptor
        assert len(descriptor.input_template) >= 300, descriptor.case_id
        assert "返回" in descriptor.input_template, descriptor.case_id
        assert descriptor.starter_filename.endswith(".py"), descriptor.case_id
        assert "NotImplementedError" in descriptor.starter_code, descriptor.case_id
        compile(descriptor.starter_code, descriptor.starter_filename, "exec")


def test_demo_case_downloads_json_template() -> None:
    descriptor = EchoCase().descriptor
    assert descriptor.starter_filename.endswith(".json")


def test_frontend_renders_templates_as_text() -> None:
    root = Path(__file__).resolve().parents[2]
    html = (root / "frontend/dist/index.html").read_text(encoding="utf-8")
    script = (root / "frontend/dist/assets/app.js").read_text(encoding="utf-8")

    assert 'id="case-input-template"' in html
    assert 'id="case-output-summary"' in html
    assert 'id="case-output-template"' in html
    assert 'id="case-output-example"' in html
    assert 'id="download-starter-template"' in html
    assert 'class="case-template-grid"' in html
    assert "caseInputTemplate.textContent" in script
    assert "caseOutputSummary.textContent" in script
    assert "caseOutputTemplate.textContent" in script
    assert "downloadStarterTemplate" in script


def test_homepage_uses_direct_project_name_without_section_numbers() -> None:
    root = Path(__file__).resolve().parents[2]
    html = (root / "frontend/dist/index.html").read_text(encoding="utf-8")

    assert '<h1 id="hero-title">知行课程助手</h1>' in html
    assert "overview-strip" not in html
    assert '<p class="eyebrow"><span>' not in html
    assert 'id="refresh-cases"' not in html
    assert 'querySelector("#refresh-cases")' not in (
        root / "frontend/dist/assets/app.js"
    ).read_text(encoding="utf-8")
