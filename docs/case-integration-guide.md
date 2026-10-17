# 案例接入指南

本文说明如何把一个新教学案例接入基础后端。示例使用 `demo.echo` 文本重复插件，它仅用于
演示扩展机制，不属于需求中列出的 8 个业务案例，也不包含那些案例的算法逻辑。

## 一、接入关系

一个案例包只需要完成三件事：

1. 用 Pydantic 或等价方式校验自己的输入。
2. 实现 `CaseAdapter`，把算法输出转换为统一的 `ResultPayload`。
3. 暴露 `register_cases(registry)`，由底座在启动时加载。

底座负责 HTTP 接口、请求编号、耗时统计、SQLite 保存、JSON/CSV 导出、自动校对和统一
错误响应。案例包不应重复实现这些功能。

## 二、建议目录

```text
backend/cases/case_nn_my_case/
  __init__.py       # register_cases 注册入口
  adapter.py        # CaseAdapter 实现
  algorithm.py      # 案例自身算法，可继续拆分
  tests/
```

仓库内的完整可运行示例位于：

```text
backend/cases/examples/demo_case_package/
  __init__.py
  echo_case.py
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

## 五、注册案例

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
| `description` | 模块简介 |
| `version` | 卡片版本标识 |
| `input_schema` | 自动生成文本框、数字框、选择框、复选框或 JSON 编辑框 |
| `output_datasets` | 展示模块预期输出数据集标签 |

前端会在打开页面时自动同步。后端运行期间新增模块后，点击页面上的“重新同步模块”即可刷新
目录；如果注册过程发生在应用启动阶段，则需要先重启后端。

## 六、运行仓库中的示例

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

## 七、自动校对

`POST /api/v1/grades` 接收已保存的 `actual_result_id` 和一个标准 `expected` payload。对运行
时间等不稳定字段，可在 `policy.ignored_paths` 中忽略；浮点计算可使用
`numeric_tolerance`。完整请求格式见 [标准化输出接口](interface.md)。

建议标准答案也由同一个适配器版本离线生成并审定。若案例需要语义判分、部分得分或专用
提示规则，可在案例包中先生成规范化结果，再调用底座比较器；不要改变公共输出信封。

## 八、接入验收清单

- 案例 ID 稳定、唯一，并带课程前缀。
- 输入 schema 与服务端实际校验规则一致。
- 每个输出数据集名称唯一，列类型和行数据一致。
- 错误输入抛出 `CaseInputError`，不返回自定义 HTTP 结构。
- JSON 和 CSV 均能导出，中文内容无乱码。
- 同一输入可重复执行，结果中的非确定字段已在校对策略中处理。
- 为正常输入、边界输入、非法输入和标准答案比较编写测试。

