# Case 接入开发文档

本文以当前基座架构为准，说明如何接入普通数据分析型 Case 和 Python
代码评测型 Case。现有 Case 1、Case 3、Case 5、Case 7 均遵循本文约定；`demo.echo` 仅用于验证
最小插件机制，不作为代码评测案例参考。

接入目标是让新 Case 自动获得统一 HTTP 接口、JSON/CSV 输出、结果持久化、前端模块入口、
代码隔离运行、通用静态质量评分和按 Case 隔离的重复代码检测，而不修改基座核心接口。

## 一、接入关系

### 基座负责

- 请求 ID、执行耗时、HTTP/OpenAPI、统一错误响应。
- `ResultPayload` 的 JSON/CSV 输出与 SQLite 持久化。
- 案例注册、查询和前端模块入口生成。
- Python 代码编译、隔离运行、超时和输出限制。
- PEP8 规范、模块化程度、语法错误定位。
- 按 `case_id` 保存源码并在不同提交人之间进行重复代码检测和扣分。
- AI 学习助手和基于结构化评测结果的点评；不会把学生源码发送给模型。

### Case 负责

一个 Case 包只需要完成以下内容：

1. 用 Pydantic 或等价方式校验自己的输入。
2. 实现 `CaseAdapter`，把课程专属结果转换为统一 `ResultPayload`。
3. 代码评测型 Case 提供隔离运行夹具，真实调用学生代码并输出结构化检查结果。
4. 计算课程专属指标，例如协议报文、复杂度曲线、执行计划节点或查找路径。
5. 在统一入口中注册适配器，并为正常、错误和边界输入编写测试。

Case 不得重复实现 PEP8、模块化、查重、源码持久化、HTTP 接口或独立数据库，也不得通过
AST 关键词代替真实功能测试。

## 二、建议目录

```text
backend/cases/case_nn_my_case/
  __init__.py       # 导出 CaseAdapter
  adapter.py        # CaseAdapter 实现
  runtime_harness.py # 代码评测型 Case 的隔离运行夹具
  analyzer.py       # 可选：课程专属结果解析/指标计算

backend/testcase/
  case_nn_correct.py   # 可直接上传的正确样例
  case_nn_incorrect.py # 可选：用于演示未通过状态

backend/tests/
  test_my_case.py      # 自动化测试
```

推荐参考：

```text
Case 1：backend/cases/case_01_process_scheduler/
Case 3：backend/cases/case_03_network_protocol_analyzer/
Case 5：backend/cases/case_05_alg_complex_analyzer/
Case 7：backend/cases/case_07_sql_execution_plan/
```

## 三、声明并校验输入

每个案例拥有不同输入结构，所以输入模型放在案例包内，而不是加入底座公共模型：

```python
from pydantic import BaseModel, ConfigDict, Field


class MyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: int = Field(ge=0)
```

将 `MyInput.model_json_schema()` 填入 `CaseDescriptor.input_schema`。前端可读取该 schema
生成表单或提前检查输入；适配器仍需在执行时做服务端校验。校验失败统一抛出
`CaseInputError`，底座会返回 HTTP 422：

```python
try:
    data = MyInput.model_validate(input_data)
except ValidationError as exc:
    raise CaseInputError(
        "案例输入不合法",
        {"errors": exc.errors(include_context=False, include_url=False)},
    ) from exc
```

## 四、实现适配器

```python
from ai_tutor_backend import (
    CaseAdapter,
    CaseDescriptor,
    ColumnSpec,
    DataType,
    Dataset,
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
            course_number=4,
            version="1.0.0",
            input_schema=MyInput.model_json_schema(),
            output_datasets=["main"],
        )

    def execute(self, input_data: dict, context: ExecutionContext) -> ResultPayload:
        data = MyInput.model_validate(input_data)
        algorithm_result = run_algorithm(data.value)
        return ResultPayload(
            summary="计算完成",
            datasets=[
                Dataset(
                    name="main",
                    title="计算结果",
                    columns=[
                        ColumnSpec(
                            key="answer",
                            title="结果",
                            data_type=DataType.NUMBER,
                        )
                    ],
                    rows=[{"answer": algorithm_result}],
                )
            ],
            metrics={"input_value": data.value},
        )
```

`course_number` 是首页课程编号。所有公开展示的案例都必须声明该字段；前端会根据接口返回值
自动按课程号升序排列，因此后续新增案例无需再修改前端。若案例仅用于底座联调、不应出现在学生
首页，请设置 `catalog_visible=False`，此时可以不填写 `course_number`。

代码评测型 Case 必须设置 `python_static_evaluation=True`，同时把 `quality_scores` 与
`code_issues` 加入 `output_datasets`。基座会在 Case 执行完成后覆盖同名数据集并统一追加
PEP8、模块化程度和重复代码检测结果。Case 自身只保留课程特有的运行测试和指标分析。
Case 1、Case 3、Case 5、Case 7 均采用此模式。

### CaseDescriptor 字段

| 字段 | 必填 | 说明 |
|---|---:|---|
| `case_id` | 是 | 全局唯一稳定标识，只允许小写字母、数字、点、下划线和连字符 |
| `name` | 是 | 学生页面模块名称 |
| `course` | 是 | 课程分类名称 |
| `course_number` | 公开案例是 | 首页“课程 XX”编号，也是动态升序排序依据 |
| `catalog_visible` | 否 | 默认 `True`；联调案例可设为 `False` |
| `description` | 否 | 模块介绍和 AI 知识点上下文 |
| `version` | 否 | Case 行为或结果契约变化时升级 |
| `input_schema` | 是 | Pydantic 生成的 JSON Schema，可附加前端扩展字段 |
| `output_datasets` | 是 | 预期输出数据集名称列表 |
| `python_static_evaluation` | 代码评测型是 | 启用基座 Python 静态质量和查重结果展示 |

### 输出字段选择

- `summary`：给学生看的简短结论。
- `datasets`：前端主要展示数据。曲线用“横坐标/纵坐标”行，时间线用“开始/结束/标签”行，
  树或图可用节点表和边表。复杂单元格可声明为 `object` 或 `array`。
- `metrics`：少量汇总指标，不要放大规模数组。
- `diagnostics`：提示、警告、错误定位，可用于错误讲解。
- `artifacts`：图片或下载文件的 URI 与媒体类型。

`ColumnSpec.data_type` 必须与每行实际值一致；底座会拒绝类型不匹配、缺列、未知列或重复
数据集名称。时间使用 ISO 8601 字符串。

### 使用基座代码运行器

需要执行学生 Python 代码的案例，不得自行调用 `subprocess`。案例只负责构造运行请求，并
解释基座返回的通用结果：

```python
from ai_tutor_backend import CodeFile, PythonRunSpec


async def execute(self, input_data, context):
    run = await context.runtime.code_runner.run_python(
        PythonRunSpec(
            files=[
                CodeFile(path="student.py", content=input_data["source_code"]),
                CodeFile(path="case_harness.py", content=CASE_HARNESS),
            ],
            entrypoint="case_harness.py",
            timeout_seconds=5,
        )
    )
    # 在案例内解析 run.stdout/run.stderr，并生成本案例的数据集、指标和评分。
```

`CodeRunner` 只返回编译状态、退出码、输出和耗时等通用信息，不包含课程业务判断。生产环境
必须使用独立沙箱；`local` 运行模式只允许用于开发和自动化测试。完整边界见
[code-execution.md](code-execution.md)。

## 五、代码评测型 Case 标准

### 5.1 输入契约

Web 页面只接收 `.py` 文件时，输入模型统一使用 `filename` 和 `source_code`：

```python
from pydantic import BaseModel, ConfigDict, Field, model_validator


class CodeSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filename: str = Field(min_length=4, max_length=255)
    source_code: str = Field(min_length=1, max_length=500_000)

    @model_validator(mode="after")
    def validate_python_file(self):
        if not self.filename.lower().endswith(".py"):
            raise ValueError("仅允许提交 .py 文件")
        return self
```

在 schema 中加入前端扩展字段：

```python
schema = CodeSubmission.model_json_schema()
schema["x-ui-mode"] = "python-file"
schema["x-accepted-extension"] = ".py"
schema["x-max-file-bytes"] = 500_000
```

提交请求必须携带提交人。底座对任何包含 `source_code` 的请求强制校验
`metadata.submitter`，缺失时返回 HTTP 422：

```json
{
  "case_id": "course.my-code-case",
  "input": {
    "filename": "answer.py",
    "source_code": "def solve(...): ..."
  },
  "parameters": {},
  "metadata": {
    "submitter": "20260001"
  }
}
```

### 5.2 描述符模板

```python
return CaseDescriptor(
    case_id="course.my-code-case",
    name="课程项目代码评测",
    course="课程名称",
    course_number=8,
    description="提交 Python 文件，在隔离环境中验证课程专属功能。",
    version="1.0.0",
    input_schema=schema,
    output_datasets=[
        "runtime_tests",
        "domain_results",
        "quality_scores",
        "code_issues",
    ],
    python_static_evaluation=True,
)
```

不要声明或生成旧的 `functional_tests` 静态功能推断数据集。课程功能必须由
`runtime_tests` 中的真实调用结果判定。

### 5.3 运行夹具输出协议

运行夹具与学生代码一起交给基座：

```text
student.py       学生上传源码
case_harness.py  Case 提供的测试夹具
```

建议为每个 Case 定义唯一结果标记，并在标准输出最后写入一行紧凑 JSON：

```python
import json
import runpy

MARKER = "__AI_TUTOR_MY_CASE_RESULT__"
submitted = runpy.run_path("student.py")

checks = [
    {
        "check_id": "SOLVE_BASIC",
        "title": "基础输入处理",
        "passed": True,
        "evidence": "已调用 solve 并核对返回值",
    }
]
observations = {"sample_output": {"value": 42}}
print(MARKER + json.dumps({"checks": checks, "observations": observations}, ensure_ascii=False))
```

约束如下：

- 夹具必须真实调用学生函数并核对返回值、状态变化或结构化输出。
- 每个检查项至少包含 `check_id`、`title`、`passed`、`evidence`。
- `observations` 保存 Case 专属数据，适配器再转换为一个或多个 `Dataset`。
- 学生代码加载异常也应尽量转换为结构化失败项；无法结构化时由 `PythonRunResult` 返回。
- 不访问真实网络、业务数据库、AI Key 或 Web 容器文件。
- 不依据函数名、注释或关键词直接判定课程功能通过。
- 输出不得无限增长；运行时间、内存和输出上限由 `PythonRunSpec` 设置。

### 5.4 运行状态处理

适配器至少处理以下 `CodeExecutionStatus`：

| 状态 | 建议行为 |
|---|---|
| `succeeded` | 解析 marker JSON，生成运行检查和课程指标 |
| `compile_error` | 案例功能分为 0，返回编译失败诊断；语法行号由基座静态测评补充 |
| `runtime_error` | 案例功能分为 0 或按已完成检查计分，返回截断后的 `stderr` |
| `timed_out` | 终止执行并返回超时诊断 |
| `unavailable` | 明确说明沙箱不可用，不得用 AST 关键词结果代替功能测评 |
| `internal_error` | 返回运行器内部错误诊断，不暴露服务端敏感信息 |

### 5.5 统一评分

当前代码评测型 Case 使用以下结构：

| 项目 | 负责方 | 分值/处理 |
|---|---|---|
| 课程功能运行测试 | Case | 最高 80 分 |
| PEP8 规范 | 基座 | 最高 10 分 |
| 模块化程度 | 基座 | 最高 10 分 |
| 重复代码检测 | 基座 | 不加分；超过阈值后从总分扣分 |

Case 在直接执行阶段应设置：

```python
functionality_score = runtime_pass_rate / 100 * 80
metrics = {
    "functionality_score": round(functionality_score, 1),
    "overall_score": round(functionality_score, 1),
    "runtime_tests_passed": runtime.tests_passed,
    "runtime_tests_total": runtime.tests_total,
    "runtime_pass_rate": round(runtime.pass_rate, 1),
}
```

随后 `ExecutionService` 自动：

1. 保存 Case 原始分为 `case_score`。
2. 追加 `pep8_score` 和 `modularity_score`。
3. 生成/替换 `quality_scores` 与 `code_issues`。
4. 按 `case_id` 查询其他提交人的历史源码。
5. 追加“重复代码检测”质量项；超过阈值时记录 `original_score`、
   `similarity_penalty` 并更新 `overall_score`。
6. 保存标准结果和本次源码。

同一提交人的历史版本会被排除，不会因个人迭代而扣分。不同 Case 的源码相互隔离，不参与
跨 Case 比较。

### 5.6 基座生成的数据集和指标

启用 `python_static_evaluation` 后，Case 不要自行生成以下数据集：

- `quality_scores`：PEP8、模块化程度、重复代码检测。
- `code_issues`：语法、格式、命名、超长函数和模块化建议。

基座常用指标包括：

- `syntax_valid`
- `case_score`
- `pep8_score`
- `modularity_score`
- `overall_score`
- `similarity_checked_submissions`
- `similarity_score`
- `similarity_threshold`
- `similarity_penalty`
- `original_score`（发生扣分时）

Case 自己只生成 `runtime_*` 和课程专属指标/数据集。

## 六、注册案例

案例包在 `backend/cases/` 中使用独立目录，并由 `backend/cases/__init__.py` 的统一注册函数加载：

```python
# backend/cases/__init__.py
def register_cases(registry):
    registry.register(MyCase())
```

通过环境变量加载一个或多个案例包：

```powershell
$env:AI_TUTOR_CASE_MODULES = "cases"
uvicorn ai_tutor_backend.main:app --reload
```

多个包使用英文逗号分隔：

```powershell
$env:AI_TUTOR_CASE_MODULES = "course_a_cases,course_b_cases"
```

案例 ID 必须全局唯一；重复 ID 会让服务在启动时直接失败，从而避免请求被错误路由。

### 前端入口如何自动生成

展示前端启动时请求 `GET /api/v1/cases`，并为返回的每个 `CaseDescriptor` 创建一张模块卡片，
因此接入新模块不需要修改 HTML、JavaScript 路由或菜单配置。字段映射如下：

| 后端描述字段 | 前端用途 |
|---|---|
| `case_id` | 模块路由标识和执行请求中的案例 ID |
| `name` | 模块卡片及实验台标题 |
| `course` | 课程分类标签 |
| `course_number` | “课程 XX”编号和模块升序位置 |
| `catalog_visible` | 是否在学生首页显示 |
| `description` | 模块简介 |
| `version` | 后端案例契约版本，不要求在学生页面突出显示 |
| `input_schema` | 自动生成文本框、数字框、选择框、复选框或 JSON 编辑框 |
| `output_datasets` | 展示模块预期输出数据集标签 |
| `python_static_evaluation` | 是否由基座追加 Python 通用静态质量与查重结果 |

前端会在打开页面时自动同步。后端运行期间新增模块后，点击页面上的“重新同步模块”即可刷新
目录；如果注册过程发生在应用启动阶段，则需要先重启后端。

## 七、运行仓库中的示例

```powershell
$env:AI_TUTOR_CASE_MODULES = "cases.examples.demo_case_package"
uvicorn ai_tutor_backend.main:app --reload
```

查看已注册案例：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/cases
```

执行并获得 JSON：

```powershell
$body = @{
  case_id = "demo.echo"
  input = @{ text = "你好，AI 助教"; repeat = 2 }
} | ConvertTo-Json

$result = Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/api/v1/executions `
  -ContentType "application/json" `
  -Body $body

$result | ConvertTo-Json -Depth 10
```

将上一步返回的 `request_id` 代入即可再次读取或导出：

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/api/v1/results/$($result.request_id)"
Invoke-WebRequest `
  "http://127.0.0.1:8000/api/v1/results/$($result.request_id)?format=csv" `
  -OutFile result.csv
```

## 八、自动校对

`POST /api/v1/grades` 接收已保存的 `actual_result_id` 和一个标准 `expected` payload。对运行
时间等不稳定字段，可在 `policy.ignored_paths` 中忽略；浮点计算可使用
`numeric_tolerance`。完整请求格式见 [标准化输出接口](interface.md)。

建议标准答案也由同一个适配器版本离线生成并审定。若案例需要语义判分、部分得分或专用
提示规则，可在案例包中先生成规范化结果，再调用底座比较器；不要改变公共输出信封。

## 九、接入验收清单

- 案例 ID 稳定、唯一，并带课程前缀。
- 输入 schema 与服务端实际校验规则一致。
- 每个输出数据集名称唯一，列类型和行数据一致。
- 错误输入抛出 `CaseInputError`，不返回自定义 HTTP 结构。
- JSON 和 CSV 均能导出，中文内容无乱码。
- 同一输入可重复执行，结果中的非确定字段已在校对策略中处理。
- 为正常输入、边界输入、非法输入和标准答案比较编写测试。

代码评测型 Case 还必须满足：

- 输入只接受 `.py` 文件，并限制文件大小；请求必须携带 `metadata.submitter`。
- 描述符启用 `python_static_evaluation=True`，声明 `quality_scores` 和 `code_issues`。
- Case 目录不存在独立的 PEP8、模块化、查重或关键词式功能静态分析器。
- 夹具在隔离环境中真实加载学生代码，检查结果可解释且包含运行证据。
- Case 功能最高 80 分，Case 直接执行时的 `overall_score` 只包含功能分。
- `compile_error`、`runtime_error`、`timed_out`、`unavailable` 都有明确诊断。
- 至少准备一份 `backend/testcase/case_nn_correct.py`，并验证能通过全部核心运行测试。
- 自动化测试同时覆盖“直接调用 Case”与“通过 `ExecutionService` 调用”两条路径。
- 服务层测试确认基座追加 PEP8、模块化和重复代码检测，同一提交人不会互相扣分。
- 生产部署使用 Unix Socket 独立沙箱，禁网、只读根文件系统、非特权 UID 和资源限制生效。

## 十、现有案例对照

| Case | 适配器 | 运行夹具 | 课程专属输出 |
|---|---|---|---|
| Case 3 网络协议分析仪 | `case_03_network_protocol_analyzer/code_grader.py` | `runtime_harness.py` | `runtime_packets`、`runtime_observations` |
| Case 5 算法复杂度分析 | `case_05_alg_complex_analyzer/code_grader.py` | `runtime_harness.py` | `runtime_curve`、`runtime_observations` |
| Case 7 SQL 执行计划 | `case_07_sql_execution_plan/adapter.py` | `runtime_harness.py` | SQL/B+ 树运行检查 |

这三个 Case 都只保留课程专属运行逻辑，共享
`backend/src/ai_tutor_backend/static_evaluation.py`、`code_similarity.py` 和
`code_execution.py`。

