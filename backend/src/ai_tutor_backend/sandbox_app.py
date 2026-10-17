from __future__ import annotations

import os

from fastapi import FastAPI

from .code_execution import LocalPythonRunner, PythonRunResult, PythonRunSpec


def _optional_int(name: str) -> int | None:
    value = os.getenv(name)
    return int(value) if value else None


app = FastAPI(
    title="AI Tutor Python Sandbox",
    version="0.1.0",
    description="Internal-only isolated Python compilation and execution service.",
)
runner = LocalPythonRunner(
    drop_uid=_optional_int("AI_TUTOR_SANDBOX_UID"),
    drop_gid=_optional_int("AI_TUTOR_SANDBOX_GID"),
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/python/run", response_model=PythonRunResult)
async def run_python(spec: PythonRunSpec) -> PythonRunResult:
    return await runner.run_python(spec)
