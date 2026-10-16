# AI 助教基础后端

这是一个面向多种计算机课程案例的 Python 后端底座。它实现统一执行、结果读取、
JSON/CSV 导出、自动校对和结构化错误讲解；**不包含题目中 8 个具体案例的算法实现**。
案例算法以后作为 `CaseAdapter` 插件接入，核心接口无需修改。

## 能力边界

- 统一 JSON 结果信封，内含数据集、指标、诊断和产物。
- 稳定的长表 CSV，可表达普通表格、曲线、时间线、树/图结构及嵌套 JSON。
- SQLite 结果持久化，可按 `request_id` 读取或再次导出。
- 通用自动校对：精确比较、浮点容差、忽略行序、忽略指定路径。
- 结构化差异定位与中文错误说明。
- 案例注册表和抽象适配器；当前注册表默认为空，明确不夹带具体案例。
- FastAPI 自动生成 OpenAPI 文档和统一错误响应。
- 同源展示前端，自动发现已注册案例并生成模块入口和输入表单。

完整契约见 [interface.md](interface.md)，案例开发步骤见
[case-integration-guide.md](case-integration-guide.md)。

## 启动

需要 Python 3.11 或更高版本。

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
uvicorn ai_tutor_backend.main:app --reload
```

打开 `http://127.0.0.1:8000/` 使用展示前端，或访问 `http://127.0.0.1:8000/docs`
调试接口。默认数据库是 `var/ai_tutor.db`，可用环境变量
`AI_TUTOR_DB_PATH` 修改。

运行验证：

```powershell
pytest
ruff check .
```

## 接入一个新案例

每个案例只负责声明元数据、校验自身输入并返回统一 `ResultPayload`：

```python
from ai_tutor_backend import (
    CaseAdapter,
    CaseDescriptor,
    ExecutionContext,
    ResultPayload,
)


class MyCase(CaseAdapter):
    @property
    def descriptor(self) -> CaseDescriptor:
        return CaseDescriptor(
            case_id="course.my-case",
            name="案例名称",
            course="课程名称",
            input_schema={"type": "object"},
            output_datasets=["main"],
        )

    def execute(self, input_data: dict, context: ExecutionContext) -> ResultPayload:
        # 在这里实现该案例自己的算法；输入不合法时抛出 CaseInputError。
        return ResultPayload(summary="执行完成", datasets=[], metrics={})
```

案例包暴露一个注册钩子：

```python
# my_cases/__init__.py
def register_cases(registry):
    registry.register(MyCase())
```

再设置 `AI_TUTOR_CASE_MODULES=my_cases` 后启动服务。多个案例包使用英文逗号分隔。
这样案例代码位于独立包中，本项目继续保持案例无关；测试或嵌入式使用也可以直接调用
`registry.register(MyCase())`。

## 目录

```text
src/ai_tutor_backend/
  app.py          HTTP API 与统一错误处理
  bootstrap.py    外部案例包加载
  models.py       JSON 数据契约
  registry.py     案例插件接口与注册表
  service.py      执行编排
  repository.py   SQLite 结果存储
  grading.py      自动校对与差异解释
  csv_export.py   标准长表 CSV 导出
tests/            注册、导出、校对和端到端接口测试
docs/             接口契约
examples/         不默认加载的接入演示插件
frontend/dist/    由 FastAPI 同源托管的模块化展示前端
```

