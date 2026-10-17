from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable
from threading import RLock

from .models import CaseDescriptor, ExecutionContext, JsonObject, ResultPayload


class CaseNotFoundError(KeyError):
    pass


class DuplicateCaseError(ValueError):
    pass


class CaseInputError(ValueError):
    """Raised by an adapter when submitted case input is invalid."""

    def __init__(self, message: str, details: JsonObject | None = None) -> None:
        super().__init__(message)
        self.details = details or {}


class CaseAdapter(ABC):
    """Extension point implemented by each future teaching case."""

    @property
    @abstractmethod
    def descriptor(self) -> CaseDescriptor:
        raise NotImplementedError

    @abstractmethod
    def execute(
        self, input_data: JsonObject, context: ExecutionContext
    ) -> ResultPayload | Awaitable[ResultPayload]:
        raise NotImplementedError


class CaseRegistry:
    def __init__(self) -> None:
        self._adapters: dict[str, CaseAdapter] = {}
        self._lock = RLock()

    def register(self, adapter: CaseAdapter) -> None:
        case_id = adapter.descriptor.case_id
        with self._lock:
            if case_id in self._adapters:
                raise DuplicateCaseError(f"case already registered: {case_id}")
            self._adapters[case_id] = adapter

    def unregister(self, case_id: str) -> None:
        with self._lock:
            if case_id not in self._adapters:
                raise CaseNotFoundError(case_id)
            del self._adapters[case_id]

    def get(self, case_id: str) -> CaseAdapter:
        with self._lock:
            try:
                return self._adapters[case_id]
            except KeyError as exc:
                raise CaseNotFoundError(case_id) from exc

    def list(self) -> list[CaseDescriptor]:
        with self._lock:
            return sorted(
                (adapter.descriptor for adapter in self._adapters.values()),
                key=lambda item: item.case_id,
            )
