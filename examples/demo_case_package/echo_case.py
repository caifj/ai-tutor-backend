from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ai_tutor_backend import (
    CaseAdapter,
    CaseDescriptor,
    CaseInputError,
    ColumnSpec,
    Dataset,
    DataType,
    Diagnostic,
    DiagnosticLevel,
    ExecutionContext,
    ResultPayload,
)


class EchoInput(BaseModel):
    """Only the demonstration case knows and validates its own input."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=200)
    repeat: int = Field(default=1, ge=1, le=20)


class EchoCase(CaseAdapter):
    """A tiny case used solely to demonstrate the extension contract."""

    @property
    def descriptor(self) -> CaseDescriptor:
        return CaseDescriptor(
            case_id="demo.echo",
            name="文本重复演示",
            course="底座接入示例",
            description="验证输入后重复文本，用于演示案例插件的完整接入流程。",
            version="1.0.0",
            input_schema=EchoInput.model_json_schema(),
            output_datasets=["messages"],
        )

    def execute(self, input_data: dict, context: ExecutionContext) -> ResultPayload:
        try:
            case_input = EchoInput.model_validate(input_data)
        except ValidationError as exc:
            raise CaseInputError(
                "示例案例输入不合法",
                {"errors": exc.errors(include_context=False, include_url=False)},
            ) from exc

        rows = [
            {"sequence": index + 1, "text": case_input.text} for index in range(case_input.repeat)
        ]
        return ResultPayload(
            summary=f"已生成 {case_input.repeat} 条文本。",
            datasets=[
                Dataset(
                    name="messages",
                    title="生成结果",
                    columns=[
                        ColumnSpec(
                            key="sequence",
                            title="序号",
                            data_type=DataType.INTEGER,
                        ),
                        ColumnSpec(
                            key="text",
                            title="文本",
                            data_type=DataType.STRING,
                        ),
                    ],
                    rows=rows,
                )
            ],
            metrics={
                "repeat_count": case_input.repeat,
                "source_character_count": len(case_input.text),
            },
            diagnostics=[
                Diagnostic(
                    code="DEMO_COMPLETED",
                    level=DiagnosticLevel.INFO,
                    message="示例案例执行成功。",
                    details={"request_id": context.request_id},
                )
            ],
        )
