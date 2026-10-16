from __future__ import annotations

import os

import uvicorn

from .app import create_app
from .bootstrap import load_case_modules
from .registry import CaseRegistry


def build_app():
    registry = CaseRegistry()
    configured_modules = os.getenv("AI_TUTOR_CASE_MODULES", "")
    load_case_modules(registry, configured_modules.split(","))
    return create_app(registry=registry)


app = build_app()


def run() -> None:
    uvicorn.run("ai_tutor_backend.main:app", host="0.0.0.0", port=8000, reload=False)


if __name__ == "__main__":
    run()
