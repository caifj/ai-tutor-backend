from __future__ import annotations

import inspect
from time import perf_counter
from uuid import uuid4

from .models import (
    ExecutionContext,
    ExecutionRequest,
    ExecutionResult,
    ExecutionStatus,
)
from .registry import CaseRegistry
from .repository import SQLiteResultRepository


class ExecutionService:
    def __init__(self, registry: CaseRegistry, repository: SQLiteResultRepository) -> None:
        self.registry = registry
        self.repository = repository

    async def execute(self, request: ExecutionRequest) -> ExecutionResult:
        adapter = self.registry.get(request.case_id)
        request_id = str(uuid4())
        context = ExecutionContext(
            request_id=request_id,
            parameters=request.parameters,
            metadata=request.metadata,
        )
        started = perf_counter()
        payload = adapter.execute(request.input, context)
        if inspect.isawaitable(payload):
            payload = await payload
        duration_ms = (perf_counter() - started) * 1000
        result = ExecutionResult(
            request_id=request_id,
            case_id=request.case_id,
            status=ExecutionStatus.SUCCEEDED,
            payload=payload,
            duration_ms=duration_ms,
        )
        self.repository.save(result)
        return result
