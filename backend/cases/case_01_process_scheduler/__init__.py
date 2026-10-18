"""Case 1: grade student scheduling implementations through the foundation runner."""

from .adapter import ProcessSchedulerCase


def register_cases(registry):
    registry.register(ProcessSchedulerCase())
