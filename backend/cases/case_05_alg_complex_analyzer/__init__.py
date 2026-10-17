"""Registration entry point for the algorithm complexity analyzer case."""

from ai_tutor_backend import CaseRegistry

from .adapter import AlgorithmComplexityAnalyzerCase

__all__ = ["AlgorithmComplexityAnalyzerCase"]


def register_cases(registry: CaseRegistry) -> None:
    registry.register(AlgorithmComplexityAnalyzerCase())
