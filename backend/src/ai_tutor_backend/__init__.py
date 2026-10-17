"""AI teaching assistant backend foundation."""

from .app import create_app
from .models import (
    CaseDescriptor,
    ColumnSpec,
    Dataset,
    DataType,
    Diagnostic,
    DiagnosticLevel,
    ExecutionContext,
    ResultPayload,
)
from .registry import CaseAdapter, CaseInputError, CaseRegistry

__all__ = [
    "CaseAdapter",
    "CaseDescriptor",
    "CaseInputError",
    "CaseRegistry",
    "ColumnSpec",
    "DataType",
    "Dataset",
    "Diagnostic",
    "DiagnosticLevel",
    "ExecutionContext",
    "ResultPayload",
    "create_app",
]
