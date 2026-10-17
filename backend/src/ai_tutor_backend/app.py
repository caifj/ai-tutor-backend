from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from .assistant import (
    AssistantChatRequest,
    AssistantProviderError,
    AssistantReply,
    AssistantService,
    AssistantStatus,
    AssistantUnavailableError,
    CodeReviewRequest,
    ModuleIntroductionRequest,
)
from .csv_export import execution_to_csv, grade_to_csv
from .grading import compare_payloads
from .models import (
    CaseDescriptor,
    CaseListResponse,
    ErrorDetail,
    ErrorResponse,
    ExecutionRequest,
    ExecutionResult,
    GradeReport,
    GradeRequest,
)
from .registry import CaseInputError, CaseNotFoundError, CaseRegistry
from .repository import ResultNotFoundError, SQLiteResultRepository
from .service import ExecutionService


def _csv_response(content: str, filename: str) -> Response:
    return Response(
        content=content.encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def create_app(
    *,
    registry: CaseRegistry | None = None,
    repository: SQLiteResultRepository | None = None,
    assistant_service: AssistantService | None = None,
) -> FastAPI:
    app = FastAPI(
        title="AI Tutor Backend",
        version="0.1.0",
        description="案例无关的 AI 助教标准化执行、结果读取、校对与错误讲解底座",
    )
    cors_origins = [
        origin.strip()
        for origin in os.getenv(
            "AI_TUTOR_CORS_ORIGINS",
            "http://127.0.0.1:5500,http://localhost:5500",
        ).split(",")
        if origin.strip()
    ]
    if cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_credentials=False,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Content-Type"],
        )
    app.state.registry = registry or CaseRegistry()
    backend_directory = Path(__file__).resolve().parents[2]
    default_db = Path(
        os.getenv("AI_TUTOR_DB_PATH", str(backend_directory / "var" / "ai_tutor.db"))
    )
    app.state.repository = repository or SQLiteResultRepository(default_db)
    app.state.execution_service = ExecutionService(app.state.registry, app.state.repository)
    app.state.assistant_service = assistant_service or AssistantService()

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        error = ErrorResponse(
            error=ErrorDetail(
                code="request_validation_error",
                message="请求数据不符合接口约束",
                details={"errors": jsonable_encoder(exc.errors())},
            )
        )
        return JSONResponse(status_code=422, content=error.model_dump(mode="json"))

    @app.exception_handler(Exception)
    async def internal_error_handler(request: Request, exc: Exception) -> JSONResponse:
        error = ErrorResponse(
            error=ErrorDetail(
                code="internal_error",
                message="服务处理请求时发生内部错误",
            )
        )
        return JSONResponse(status_code=500, content=error.model_dump(mode="json"))

    @app.exception_handler(CaseNotFoundError)
    async def case_not_found_handler(request: Request, exc: CaseNotFoundError) -> JSONResponse:
        case_id = str(exc).strip("'")
        error = ErrorResponse(
            error=ErrorDetail(
                code="case_not_found",
                message=f"未注册案例：{case_id}",
                details={"case_id": case_id},
            )
        )
        return JSONResponse(status_code=404, content=error.model_dump(mode="json"))

    @app.exception_handler(ResultNotFoundError)
    async def result_not_found_handler(request: Request, exc: ResultNotFoundError) -> JSONResponse:
        result_id = str(exc).strip("'")
        error = ErrorResponse(
            error=ErrorDetail(
                code="result_not_found",
                message=f"未找到执行结果：{result_id}",
                details={"request_id": result_id},
            )
        )
        return JSONResponse(status_code=404, content=error.model_dump(mode="json"))

    @app.exception_handler(CaseInputError)
    async def case_input_error_handler(request: Request, exc: CaseInputError) -> JSONResponse:
        error = ErrorResponse(
            error=ErrorDetail(
                code="case_input_error",
                message=str(exc),
                details=exc.details,
            )
        )
        return JSONResponse(status_code=422, content=error.model_dump(mode="json"))

    @app.exception_handler(AssistantUnavailableError)
    async def assistant_unavailable_handler(
        request: Request, exc: AssistantUnavailableError
    ) -> JSONResponse:
        error = ErrorResponse(
            error=ErrorDetail(code="assistant_unavailable", message=str(exc))
        )
        return JSONResponse(status_code=503, content=error.model_dump(mode="json"))

    @app.exception_handler(AssistantProviderError)
    async def assistant_provider_error_handler(
        request: Request, exc: AssistantProviderError
    ) -> JSONResponse:
        error = ErrorResponse(
            error=ErrorDetail(code="assistant_provider_error", message=str(exc))
        )
        return JSONResponse(status_code=502, content=error.model_dump(mode="json"))

    @app.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "schema_version": "1.0"}

    @app.get("/api/v1/cases", response_model=CaseListResponse, tags=["cases"])
    async def list_cases() -> CaseListResponse:
        return CaseListResponse(items=app.state.registry.list())

    @app.get("/api/v1/cases/{case_id}", response_model=CaseDescriptor, tags=["cases"])
    async def get_case(case_id: str) -> CaseDescriptor:
        return app.state.registry.get(case_id).descriptor

    @app.get(
        "/api/v1/assistant/status",
        response_model=AssistantStatus,
        tags=["assistant"],
    )
    async def assistant_status() -> AssistantStatus:
        return app.state.assistant_service.status()

    @app.post(
        "/api/v1/assistant/chat",
        response_model=AssistantReply,
        tags=["assistant"],
    )
    async def assistant_chat(body: AssistantChatRequest) -> AssistantReply:
        case = app.state.registry.get(body.case_id).descriptor if body.case_id else None
        return await app.state.assistant_service.chat(body.messages, case)

    @app.post(
        "/api/v1/assistant/module-introduction",
        response_model=AssistantReply,
        tags=["assistant"],
    )
    async def assistant_module_introduction(
        body: ModuleIntroductionRequest,
    ) -> AssistantReply:
        case = app.state.registry.get(body.case_id).descriptor
        return await app.state.assistant_service.introduce(case)

    @app.post(
        "/api/v1/assistant/code-review",
        response_model=AssistantReply,
        tags=["assistant"],
    )
    async def assistant_code_review(body: CodeReviewRequest) -> AssistantReply:
        result = app.state.repository.get(body.request_id)
        case = app.state.registry.get(result.case_id).descriptor
        return await app.state.assistant_service.review_code(result, case)

    @app.post("/api/v1/executions", response_model=ExecutionResult, tags=["execution"])
    async def execute_case(
        body: ExecutionRequest,
        format: str = Query(default="json", pattern="^(json|csv)$"),
    ) -> ExecutionResult | Response:
        result = await app.state.execution_service.execute(body)
        if format == "csv":
            return _csv_response(execution_to_csv(result), f"{result.request_id}.csv")
        return result

    @app.get("/api/v1/results/{request_id}", response_model=ExecutionResult, tags=["results"])
    async def get_result(
        request_id: str,
        format: str = Query(default="json", pattern="^(json|csv)$"),
    ) -> ExecutionResult | Response:
        result = app.state.repository.get(request_id)
        if format == "csv":
            return _csv_response(execution_to_csv(result), f"{request_id}.csv")
        return result

    @app.post("/api/v1/grades", response_model=GradeReport, tags=["grading"])
    async def grade_result(
        body: GradeRequest,
        format: str = Query(default="json", pattern="^(json|csv)$"),
    ) -> GradeReport | Response:
        actual = app.state.repository.get(body.actual_result_id)
        report = compare_payloads(
            actual_result_id=body.actual_result_id,
            actual=actual.payload,
            expected=body.expected,
            policy=body.policy,
        )
        if format == "csv":
            return _csv_response(grade_to_csv(report), f"grade-{report.grade_id}.csv")
        return report

    project_directory = backend_directory.parent
    frontend_directory = Path(
        os.getenv(
            "AI_TUTOR_FRONTEND_DIR",
            str(project_directory / "frontend" / "dist"),
        )
    )
    serve_frontend = os.getenv("AI_TUTOR_SERVE_FRONTEND", "1").lower() not in {
        "0",
        "false",
        "no",
    }
    if serve_frontend and frontend_directory.is_dir():
        app.mount("/", StaticFiles(directory=frontend_directory, html=True), name="frontend")

    return app
