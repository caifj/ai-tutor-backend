"""Registration entry point for production teaching cases."""

from ai_tutor_backend import CaseRegistry

from .case_01_process_scheduler import ProcessSchedulerCase
from .case_03_network_protocol_analyzer import NetworkProtocolAnalyzerCase
from .case_05_alg_complex_analyzer import AlgorithmComplexityAnalyzerCase
from .case_07_sql_execution_plan import SqlExecutionPlanCase
from .case_08_compiler_frontend import MiniCompilerFrontendCase
from .examples.demo_case_package import EchoCase


def register_cases(registry: CaseRegistry) -> None:
    """Register every production case shipped in this repository."""

    registry.register(ProcessSchedulerCase())
    registry.register(NetworkProtocolAnalyzerCase())
    registry.register(AlgorithmComplexityAnalyzerCase())
    registry.register(SqlExecutionPlanCase())
    registry.register(MiniCompilerFrontendCase())
    registry.register(EchoCase())
