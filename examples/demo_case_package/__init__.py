"""Registration entry point for the case integration example."""

from ai_tutor_backend import CaseRegistry

from .echo_case import EchoCase


def register_cases(registry: CaseRegistry) -> None:
    registry.register(EchoCase())
