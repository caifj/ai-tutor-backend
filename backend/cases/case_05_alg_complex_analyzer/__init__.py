"""Registration entry point for the algorithm complexity analysis platform."""
from ai_tutor_backend import CaseRegistry

from .code_grader import AlgorithmComplexityAnalyzerCase

__all__ = ["AlgorithmComplexityAnalyzerCase"]


def register_cases(registry: CaseRegistry) -> None:
    registry.register(AlgorithmComplexityAnalyzerCase())
