from __future__ import annotations

from importlib import import_module
from typing import Protocol, cast

from .registry import CaseRegistry


class RegistrationHook(Protocol):
    def __call__(self, registry: CaseRegistry) -> None: ...


def load_case_modules(registry: CaseRegistry, module_names: list[str]) -> None:
    """Load external case packages without coupling them to the core backend."""

    for module_name in module_names:
        normalized = module_name.strip()
        if not normalized:
            continue
        module = import_module(normalized)
        hook = getattr(module, "register_cases", None)
        if not callable(hook):
            raise TypeError(f"case module '{normalized}' must expose register_cases(registry)")
        cast(RegistrationHook, hook)(registry)
