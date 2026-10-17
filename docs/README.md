# AI 助教基础后端

这是一个面向多种计算机课程案例的 Python 后端底座。它实现统一执行、结果读取、
JSON/CSV 导出、自动校对和结构化错误讲解。当前已接入案例 3“网络协议分析仪”，其余案例
尚未实现；后续案例继续作为 `CaseAdapter` 插件接入，核心接口无需修改。

## 能力边界

- 统一 JSON 结果信封，内含数据集、指标、诊断和产物。
- 稳定的长表 CSV，可表达普通表格、曲线、时间线、树/图结构及嵌套 JSON。
- SQLite 结果持久化，可按 `request_id` 读取或再次导出。
- 通用自动校对：精确比较、浮点容差、忽略行序、忽略指定路径。
- 结构化差异定位与中文错误说明。
- 案例注册表和抽象适配器；正式案例统一放在独立的 `backend/cases/` 目录。
- FastAPI 自动生成 OpenAPI 文档和统一错误响应。
- 同源展示前端，自动发现已注册案例并生成模块入口和输入表单。
- 独立 AI 课程助手，支持浏览器端上下文、删除聊天记录和选中模块后的知识点引导。
- 按案例保存 Python 源码并与不同学生的历史提交查重，超过阈值后自动扣减总分。
- 默认注册案例 3“网络协议分析仪代码评测”，仅接收 `.py` 文件，以静态分析检查 ARP、
  ICMP、TCP 构造/解析、抓包和异常检测逻辑；浏览器用 IndexedDB 保存本机提交时间线。

完整契约见 [interface.md](interface.md)，案例开发步骤见
[case-integration-guide.md](case-integration-guide.md)，AI 配置与安全边界见
[assistant-integration.md](assistant-integration.md)，查重标准、扣分和数据边界见
[code-similarity.md](code-similarity.md)。

已接入正式案例：

- [案例 3：网络协议分析仪代码评测](cases/network-protocol-analyzer.md)

## 启动

需要 Python 3.11 或更高版本。

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e "backend[dev]"
uvicorn ai_tutor_backend.main:app --reload
```

启用 AI 课程助手时，在启动前设置服务端环境变量（不要提交真实 Key）：

```powershell
$env:SPARK_API_KEY = "在此填写控制台生成的 Key"
```

打开 `http://127.0.0.1:8000/` 使用展示前端，或访问 `http://127.0.0.1:8000/docs`
调试接口。默认数据库是 `backend/var/ai_tutor.db`，可用环境变量
`AI_TUTOR_DB_PATH` 修改。

运行验证：

```powershell
python -m pytest backend/tests
python -m ruff check backend
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
backend/
  src/ai_tutor_backend/     HTTP API、执行、存储、数据契约与组合根
  src/course_assistant_ai/  独立 AI 问答、模型客户端与行为规范
  src/assignment_grading/   独立作业批改与代码相似度检查
  cases/                 正式案例及 examples/ 接入演示案例
  tests/                 后端自动化测试
  testcase/              学生代码测试样例
  var/                   SQLite 运行数据，不进入 Git
  pyproject.toml         Python 项目与依赖配置
frontend/
  dist/                  可独立部署的 HTML/CSS/JavaScript 前端
docs/                    共享接口与接入说明
```

默认由 FastAPI 兼容托管 `frontend/dist/`。设置 `AI_TUTOR_SERVE_FRONTEND=0` 可关闭静态
托管，将前端独立部署；前端 API 地址在 `frontend/dist/config.js` 配置，跨域来源通过
`AI_TUTOR_CORS_ORIGINS` 配置。

