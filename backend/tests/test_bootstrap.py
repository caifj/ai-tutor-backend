from __future__ import annotations

import sys
from types import ModuleType

import pytest

from ai_tutor_backend.bootstrap import load_case_modules
from ai_tutor_backend.models import CaseDescriptor, ExecutionContext, ResultPayload
from ai_tutor_backend.registry import CaseAdapter, CaseRegistry


class LoadedAdapter(CaseAdapter):
    @property
    def descriptor(self) -> CaseDescriptor:
        return CaseDescriptor(case_id="loaded", name="Loaded", course="Tests")

    def execute(self, input_data: dict, context: ExecutionContext) -> ResultPayload:
        return ResultPayload()


def test_load_case_modules_calls_registration_hook(monkeypatch: pytest.MonkeyPatch) -> None:
    module = ModuleType("fake_case_package")
    module.register_cases = lambda registry: registry.register(LoadedAdapter())
    monkeypatch.setitem(sys.modules, module.__name__, module)
    registry = CaseRegistry()

    load_case_modules(registry, ["fake_case_package"])

    assert registry.get("loaded").descriptor.name == "Loaded"


def test_load_case_modules_requires_registration_hook(monkeypatch: pytest.MonkeyPatch) -> None:
    module = ModuleType("invalid_case_package")
    monkeypatch.setitem(sys.modules, module.__name__, module)

    with pytest.raises(TypeError, match="register_cases"):
        load_case_modules(CaseRegistry(), ["invalid_case_package"])
