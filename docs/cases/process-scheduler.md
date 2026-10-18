# 案例 1 进程调度代码评测

案例 ID 为 `os.process-scheduler`，首页显示为课程 01。学生提交单个 UTF-8 `.py`
文件；基座负责语法编译、隔离运行和通用静态测评，案例负责解析运行报文、核对结果、
计算调度指标并返回网页甘特图数据。案例自身不执行 `exec`、`eval` 或 `subprocess`。

## 与原压缩包的关系

原压缩包是 PyQt6 桌面模拟器，运行的是自带算法，不能直接作为网页学生代码评测插件。
本插件复用原 `scheduler/models.py` 与 `scheduler/algorithms.py` 的规则作为服务端参考答案，
其余新增代码完成基座接口和网页接入。原压缩包及桌面源代码不修改。

`backend/testcase/case1_correct.py` 是从原模型与算法合并出的单文件联调样例，
不依赖 PyQt6、psutil、matplotlib。`case1_incorrect.py` 为错误样例。
不要只上传原 `gui_app.py`、`main.py` 或 `algorithms.py`：它们依赖未提交的本地模块。

## 学生提交接口

推荐实现：

```python
def schedule(processes, algorithm, quantum=2):
    # processes 是 PCB 字典列表；algorithm 为 fcfs/sjf/rr/priority。
    # 在这里执行学生自己的算法，返回下面的结构化结果。
    return {"segments": [], "process_metrics": [], "summary": {}}
```

也兼容原案例的类接口：单个文件内提供 `Process`、`FCFSScheduler`、`SJFScheduler`、
`RRScheduler`、`PriorityScheduler`；调用 `.schedule(processes)`，结果可提供 `.to_dict()`。
模块导入时不要启动 GUI 或等待交互输入；演示启动代码放在 `if __name__ == "__main__":` 下。

每个输入进程包含 `pid`、`arrival_time`、`burst_time`、`priority`。测试均使用合法输入，
进程 ID 唯一，时间为整数。`IDLE` 为保留的 CPU 空闲标识。

输出契约沿用原案例说明：

| 字段 | 内容 |
|---|---|
| `segments` | 按时间顺序的 `{pid, start, end}` 数组，可附 `duration` |
| `process_metrics` | 每进程的 `pid, arrival_time, burst_time, priority, first_start_time, completion_time, waiting_time, turnaround_time, response_time` |
| `summary` | `average_waiting_time, average_turnaround_time, average_response_time, cpu_utilization_percent, total_time` |

等待时间 = 完成时间 − 到达时间 − 服务时间；周转时间 = 完成时间 − 到达时间；
响应时间 = 首次开始时间 − 到达时间。CPU 利用率从时刻 0 起统计，含初始空闲。
平均指标允许四位小数，比较绝对容差为 0.0001。

调度约定与原实现一致：FCFS 按 `(arrival_time, pid)`；SJF 非抢占，按
`(burst_time, arrival_time, pid)`；优先级非抢占，数字越小越高，平局按
`(arrival_time, pid)`；RR 时间片末端新到达进程先入队，再将未完成进程放回队尾。
RR 必须保留每个时间片，即使相邻两段为同一进程。空闲段也必须显式输出。

## 评分与展示

四种算法各运行六个场景：同时到达、CPU 空闲、平局与乱序、时间片边界到达、单进程、
固定种子的混合输入。RR 覆盖时间片 1、2、3、4。每次运行分别检查时间线、逐进程指标、
平均性能指标，共 72 项，等权折算为功能分 80 分。基座另加 PEP8 10 分、模块化 10 分，
并按基座既有规则处理代码相似度。

沙箱只采集学生返回值，不持有标准答案，也不决定评分。服务端固定检查项数，验证报文结构、
测试 ID、数值及各进程指标。缺失、重复、截断的报文均不通过；语法错误、运行异常、超时、
沙箱不可用均显示诊断。沙箱不可用时功能分为 0，静态分仍由基座单独给出，不能解释成评测通过。

网页展示已通过时间线核对的学生调度结果，并从这些时间线计算展示用指标。
若学生自己返回的指标错误，相关检查会扣分，页面仍可展示其正确时间线及重新计算的指标。
未通过时间线核对的场景不绘制图，错误证据在“查看全部调度检查”内；不会用教师答案代替
学生结果。CSV、结果保存、历史记录复用基座接口。

当前是调度功能评分，不表示完整桌面项目验收通过。原文档的 PyQt6 界面、psutil 系统监控、
matplotlib 桌面绘图、真实进程到 PCB 的联动，仍需桌面环境单独验收。网页使用 SVG 甘特图。
固定公开测试用于课程反馈，不能证明任意输入均正确，也不等同于防作弊的隐藏测试系统。

## 本地验证

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e "backend[dev]"
$env:PYTHONPATH = "$PWD/backend/src"
.venv\Scripts\python.exe -m pytest backend/tests -ra
$env:AI_TUTOR_CODE_RUNNER = "local"
.venv\Scripts\python.exe -m uvicorn ai_tutor_backend.main:app --host 127.0.0.1 --port 8000
```

仅在开发测试中使用 `local`。公网部署保持 `unix` 模式和既有独立沙箱。
网页选择“课程 01”，填写提交人，上传正确/错误样例，即可核对得分与图表。
API 请求为 `POST /api/v1/executions`，包含 `case_id`、`input.filename`、
`input.source_code` 和 `metadata.submitter`。

## 合并范围

新增独立的 `backend/cases/case_01_process_scheduler/`、正反样例、专项测试及本说明。
公共改动只有案例注册、前端调度数据集展示、两个目录枚举测试的预期案例列表。
提交前先 `git fetch origin`，检查与远端差异，再合并最新主分支并运行回归；不要覆盖他人代码。
