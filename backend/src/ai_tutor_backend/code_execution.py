from __future__ import annotations

import asyncio
import math
import os
import signal
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath
from time import perf_counter
from typing import Protocol

import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CodeExecutionStatus(StrEnum):
    SUCCEEDED = "succeeded"
    COMPILE_ERROR = "compile_error"
    RUNTIME_ERROR = "runtime_error"
    TIMED_OUT = "timed_out"
    UNAVAILABLE = "unavailable"
    INTERNAL_ERROR = "internal_error"


class CodeFile(_StrictModel):
    path: str = Field(min_length=1, max_length=240)
    content: str = Field(max_length=500_000)

    @field_validator("path")
    @classmethod
    def validate_relative_path(cls, value: str) -> str:
        normalized = value.replace("\\", "/")
        parsed = PurePosixPath(normalized)
        if parsed.is_absolute() or ".." in parsed.parts or normalized.endswith("/"):
            raise ValueError("code file path must be a safe relative path")
        if any(part in {"", "."} for part in parsed.parts):
            raise ValueError("code file path contains an invalid segment")
        return normalized


class PythonRunSpec(_StrictModel):
    files: list[CodeFile] = Field(min_length=1, max_length=30)
    entrypoint: str = Field(min_length=1, max_length=240)
    argv: list[str] = Field(default_factory=list, max_length=20)
    stdin: str = Field(default="", max_length=100_000)
    timeout_seconds: float = Field(default=5.0, ge=0.1, le=15.0)
    memory_limit_mb: int = Field(default=128, ge=32, le=512)
    max_output_bytes: int = Field(default=128_000, ge=1_024, le=1_000_000)

    @field_validator("entrypoint")
    @classmethod
    def validate_entrypoint(cls, value: str) -> str:
        return CodeFile.validate_relative_path(value)

    @model_validator(mode="after")
    def validate_files(self) -> PythonRunSpec:
        paths = [item.path for item in self.files]
        if len(paths) != len(set(paths)):
            raise ValueError("code file paths must be unique")
        if self.entrypoint not in paths:
            raise ValueError("entrypoint must reference one of the submitted files")
        return self


class PythonRunResult(_StrictModel):
    status: CodeExecutionStatus
    compile_succeeded: bool
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    duration_ms: float = Field(default=0.0, ge=0)
    output_truncated: bool = False


class CodeRunner(Protocol):
    async def run_python(self, spec: PythonRunSpec) -> PythonRunResult: ...


@dataclass(frozen=True)
class ExecutionRuntime:
    code_runner: CodeRunner


class UnavailableCodeRunner:
    def __init__(self, reason: str = "代码运行沙箱未配置") -> None:
        self.reason = reason

    async def run_python(self, spec: PythonRunSpec) -> PythonRunResult:
        del spec
        return PythonRunResult(
            status=CodeExecutionStatus.UNAVAILABLE,
            compile_succeeded=False,
            stderr=self.reason,
        )


class UnixSocketPythonRunner:
    """Client for the isolated runner service connected through a Unix socket."""

    def __init__(self, socket_path: str, request_timeout_seconds: float = 20.0) -> None:
        self.socket_path = socket_path
        self.request_timeout_seconds = request_timeout_seconds

    async def run_python(self, spec: PythonRunSpec) -> PythonRunResult:
        transport = httpx.AsyncHTTPTransport(uds=self.socket_path)
        try:
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://sandbox",
                timeout=self.request_timeout_seconds,
            ) as client:
                response = await client.post(
                    "/v1/python/run",
                    json=spec.model_dump(mode="json"),
                )
                response.raise_for_status()
                return PythonRunResult.model_validate(response.json())
        except (httpx.HTTPError, ValueError) as exc:
            return PythonRunResult(
                status=CodeExecutionStatus.UNAVAILABLE,
                compile_succeeded=False,
                stderr=f"无法连接代码运行沙箱：{exc}",
            )


class LocalPythonRunner:
    """Runs Python in the current machine.

    This class belongs in the dedicated sandbox service. The main web process must
    not enable it in production because student code would share its container.
    """

    def __init__(self, *, drop_uid: int | None = None, drop_gid: int | None = None) -> None:
        self.drop_uid = drop_uid
        self.drop_gid = drop_gid

    async def run_python(self, spec: PythonRunSpec) -> PythonRunResult:
        if os.name == "posix" and self.drop_uid is not None:
            # preexec_fn must run outside a worker thread; the sandbox uses one worker.
            return self._run_python(spec)
        return await asyncio.to_thread(self._run_python, spec)

    def _run_python(self, spec: PythonRunSpec) -> PythonRunResult:
        started = perf_counter()
        try:
            with tempfile.TemporaryDirectory(prefix="ai-tutor-run-") as temporary:
                workspace = Path(temporary)
                for item in spec.files:
                    target = workspace.joinpath(*PurePosixPath(item.path).parts)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(item.content, encoding="utf-8")
                self._prepare_workspace_permissions(workspace)

                python_files = [str(workspace / item.path) for item in spec.files if item.path.endswith(".py")]
                compile_result = self._run_process(
                    [
                        sys.executable,
                        "-I",
                        "-X",
                        "utf8",
                        "-m",
                        "py_compile",
                        *python_files,
                    ],
                    workspace,
                    spec,
                    stdin="",
                )
                if compile_result.timed_out:
                    return self._result(
                        CodeExecutionStatus.TIMED_OUT,
                        False,
                        compile_result,
                        started,
                    )
                if compile_result.exit_code != 0:
                    return self._result(
                        CodeExecutionStatus.COMPILE_ERROR,
                        False,
                        compile_result,
                        started,
                    )

                bootstrap = (
                    "import runpy,sys;"
                    "root=sys.argv.pop(1);entry=sys.argv.pop(1);"
                    "sys.path.insert(0,root);"
                    "runpy.run_path(entry,run_name='__main__')"
                )
                run_result = self._run_process(
                    [
                        sys.executable,
                        "-I",
                        "-X",
                        "utf8",
                        "-c",
                        bootstrap,
                        str(workspace),
                        str(workspace / spec.entrypoint),
                        *spec.argv,
                    ],
                    workspace,
                    spec,
                    stdin=spec.stdin,
                )
                if run_result.timed_out:
                    status = CodeExecutionStatus.TIMED_OUT
                elif run_result.exit_code == 0:
                    status = CodeExecutionStatus.SUCCEEDED
                else:
                    status = CodeExecutionStatus.RUNTIME_ERROR
                return self._result(status, True, run_result, started)
        except Exception as exc:  # noqa: BLE001  # pragma: no cover - isolation boundary
            return PythonRunResult(
                status=CodeExecutionStatus.INTERNAL_ERROR,
                compile_succeeded=False,
                stderr=f"代码运行器内部错误：{type(exc).__name__}: {exc}",
                duration_ms=(perf_counter() - started) * 1000,
            )

    def _prepare_workspace_permissions(self, workspace: Path) -> None:
        if os.name != "posix" or self.drop_uid is None:
            return
        gid = self.drop_gid if self.drop_gid is not None else self.drop_uid
        for path in [workspace, *workspace.rglob("*")]:
            os.chown(path, self.drop_uid, gid)

    def _preexec(self, spec: PythonRunSpec):
        if os.name != "posix":
            return None

        def configure() -> None:
            import resource

            cpu_seconds = max(1, math.ceil(spec.timeout_seconds))
            memory_bytes = spec.memory_limit_mb * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds + 1))
            resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
            resource.setrlimit(
                resource.RLIMIT_FSIZE,
                (spec.max_output_bytes, spec.max_output_bytes),
            )
            resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
            if hasattr(resource, "RLIMIT_NPROC"):
                resource.setrlimit(resource.RLIMIT_NPROC, (16, 16))
            os.setsid()
            if self.drop_uid is not None:
                gid = self.drop_gid if self.drop_gid is not None else self.drop_uid
                os.setgroups([])
                os.setgid(gid)
                os.setuid(self.drop_uid)

        return configure

    def _run_process(
        self,
        command: list[str],
        workspace: Path,
        spec: PythonRunSpec,
        *,
        stdin: str,
    ) -> _ProcessResult:
        stdout_path = workspace / ".stdout"
        stderr_path = workspace / ".stderr"
        process_started = perf_counter()
        with stdout_path.open("wb") as stdout_file, stderr_path.open("wb") as stderr_file:
            process = subprocess.Popen(
                command,
                cwd=workspace,
                stdin=subprocess.PIPE,
                stdout=stdout_file,
                stderr=stderr_file,
                env=_clean_environment(),
                start_new_session=os.name != "posix",
                preexec_fn=self._preexec(spec),  # noqa: PLW1509
            )
            timed_out = False
            try:
                process.communicate(input=stdin.encode("utf-8"), timeout=spec.timeout_seconds)
            except subprocess.TimeoutExpired:
                timed_out = True
                if os.name == "posix":
                    os.killpg(process.pid, signal.SIGKILL)
                else:  # pragma: no cover - Windows-only cleanup
                    process.kill()
                process.wait(timeout=2)

        stdout, stdout_truncated = _read_limited(stdout_path, spec.max_output_bytes)
        stderr, stderr_truncated = _read_limited(stderr_path, spec.max_output_bytes)
        return _ProcessResult(
            exit_code=process.returncode,
            stdout=stdout,
            stderr=stderr,
            timed_out=timed_out,
            output_truncated=stdout_truncated or stderr_truncated,
            duration_ms=(perf_counter() - process_started) * 1000,
        )

    @staticmethod
    def _result(
        status: CodeExecutionStatus,
        compile_succeeded: bool,
        process: _ProcessResult,
        started: float,
    ) -> PythonRunResult:
        return PythonRunResult(
            status=status,
            compile_succeeded=compile_succeeded,
            exit_code=process.exit_code,
            stdout=process.stdout,
            stderr=process.stderr,
            duration_ms=(perf_counter() - started) * 1000,
            output_truncated=process.output_truncated,
        )


@dataclass(frozen=True)
class _ProcessResult:
    exit_code: int | None
    stdout: str
    stderr: str
    timed_out: bool
    output_truncated: bool
    duration_ms: float


def _read_limited(path: Path, limit: int) -> tuple[str, bool]:
    with path.open("rb") as handle:
        content = handle.read(limit + 1)
    truncated = len(content) > limit
    return content[:limit].decode("utf-8", errors="replace"), truncated


def _clean_environment() -> dict[str, str]:
    environment = {"PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"}
    if os.name == "nt":  # pragma: no cover - platform-specific compatibility
        for name in ("SYSTEMROOT", "WINDIR", "TEMP", "TMP"):
            if value := os.getenv(name):
                environment[name] = value
    return environment


def create_code_runner_from_env() -> CodeRunner:
    mode = os.getenv("AI_TUTOR_CODE_RUNNER", "disabled").strip().lower()
    if mode == "unix":
        socket_path = os.getenv(
            "AI_TUTOR_CODE_RUNNER_SOCKET",
            "/run/ai-tutor-sandbox/runner.sock",
        )
        return UnixSocketPythonRunner(socket_path)
    if mode == "local":
        return LocalPythonRunner()
    return UnavailableCodeRunner()
