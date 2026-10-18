# 案例 2：虚拟内存分页模拟器代码评测

## 目标与边界

本案例接收学生提交的单个 `.py` 文件，判断代码是否覆盖虚拟内存分页模拟器的要求：

1. 建立页表并管理物理页框。
2. 实现逻辑地址到物理地址的转换（页号 + 页内偏移）。
3. 实现缺页中断处理流程。
4. 实现 FIFO（先进先出）页面置换。
5. 实现 LRU（最近最久未使用）页面置换。
6. 实现 OPT（最佳置换）页面置换。
7. 统计缺页次数并计算缺页率。
8. 扫描多档内存页框数，输出缺页率曲线数据。

按需求约定，本案例**只检测代码、不运行代码**：功能检查全部由 Python `ast` 静态分析完成，
学生提交的文件不会被执行，也不需要基座沙箱。案例同时用基座自带的参考分页模拟器产出一组
标准答案数据，供学生对照自查自己的缺页率曲线是否正确。

PEP8 规范与模块化程度**不在本案例内实现**：描述符声明 `python_static_evaluation = True` 后，
基座 `ai_tutor_backend.service` 会自动完成语法检查与质量评分，注入 `quality_scores`、
`code_issues` 两个数据集，并把案例功能分与质量分相加得到 100 分制总分。本案例只负责
分页模拟器特有的功能检查、分页专用问题以及缺页率基准数据。

核心文件：

```text
backend/cases/case_02_virtual_memory_paging/
  code_grader.py       案例描述、输入校验、功能评分与标准化输出
  evaluator.py         AST 功能检查（8 项）与分页专用问题定位
  paging_reference.py  参考分页模拟器（FIFO / LRU / OPT），产出缺页率标准答案
```

## 参考分页模拟器

`paging_reference.py` 是基座内置的**标准答案数据源**，与学生代码无关：

- 参考序列共 96 次访问，覆盖 9 个逻辑页，分两段构造：先做工作集由 2 页爬升到 8 页的
  斜坡段（每档重复访问形成时间局部性），再追加两次教材中经典的 Belady 异常引用串
  `0 1 2 3 0 1 4 0 1 2 3 4`。序列完全确定，任何一次评测都得到逐位一致的结果。
- 物理内存页框数取 1 ~ 9 共 9 档，分别用 FIFO、LRU、OPT 模拟，输出缺页次数、命中次数与
  缺页率，合计 27 个采样点。
- 三条曲线随页框数单调下降，OPT 全区间平均缺页率最低；同时在 3 页框处复现 Belady 异常
  （FIFO 缺页率反而低于 LRU），可用来验证学生是否真的区分了两种置换策略。
- 另有页框占用时间线（LRU、4 页框），以“起始/结束访问序号 + 逻辑页号”记录页面换入换出。

参考模拟器输出的缺页率可作为标准答案，对学生代码使用 `POST /api/v1/grades` 自动校对；
静态检查得到的分数与曲线数据互不影响，曲线数据始终由参考实现产出。

## Web 使用方式

1. 启动后端并打开 `http://127.0.0.1:8000/`。
2. 进入“虚拟内存分页模拟器代码评测”。
3. 填写提交人，并选择或拖入一个不超过 500 KB 的 `.py` 文件。
4. 点击“提交并评测”，查看功能检查明细、缺页率对应表、缺页率变化曲线和页框占用过程。
5. 再次提交后，可在“本机提交时间线”选择历史版本并查看逐行差异。

页面不会提供源码文本框；文件扩展名和大小会在浏览器与后端两端校验。可直接使用仓库中的
`backend/testcase/case2_correct.py`（应 8/8 通过、100 分）与
`backend/testcase/case2_incorrect.py`（演示未通过状态）验证完整流程。

## HTTP 请求

浏览器读取文件文本后仍通过统一 JSON 接口提交：

```json
{
  "case_id": "os.virtual-memory-paging",
  "input": {
    "filename": "student_paging.py",
    "source_code": "class PageTable:\n    ..."
  },
  "metadata": {"submitter": "20260001"}
}
```

`source_code` 最大 500,000 字符；`filename` 必须以 `.py` 结尾。接口保持 JSON/CSV 标准输出，
源码会按本案例单独保存在后端并参与后续学生提交的相似度审查；超过默认 85% 阈值时会扣减总分。
完整规则见 [../code-similarity.md](../code-similarity.md)。

## 评分组成

案例自身只产出**功能覆盖 80 分**，8 项检查的权重依次为 12 / 15 / 10 / 9 / 12 / 8 / 7。
适配器把功能分写入 `metrics["overall_score"]`，随后基座叠加：

- PEP8 规范 10 分：超长行、Tab 缩进、行尾空白、通配符导入、函数命名；
- 模块化程度 10 分：函数与类的拆分、文档字符串覆盖率、超长函数；
- 查重结论（重复代码）同样由基座写入。

基座叠加后 `metrics["case_score"]` 保留案例功能分，`metrics["overall_score"]` 为 100 分制总分。

输出数据集：

| 数据集 | 来源 | 含义 |
| --- | --- | --- |
| `functional_tests` | 本案例 | 8 项功能要求的通过状态、权重、判定证据和改进建议 |
| `paging_issues` | 本案例 | 分页专用问题：级别、行号、规则编号和修复建议 |
| `frame_fault_rate_table` | 本案例 | 物理内存页框数与缺页率的对应关系（27 行，含缺页与命中次数） |
| `fault_rate_curve` | 本案例 | 缺页率变化曲线数据（横轴内存页框数、纵轴缺页率、按算法分组） |
| `frame_occupancy_timeline` | 本案例 | 页框占用过程（LRU、4 页框），起止访问序号与逻辑页号 |
| `quality_scores` | 基座注入 | PEP8、模块化与查重评分 |
| `code_issues` | 基座注入 | 通用 Python 代码问题与建议 |

`fault_rate_curve` 数据集名以 `curve` 结尾，基座前端会自动绘制缺页率随内存页框数变化的折线图，
区块标题取自数据集标题，图例颜色与对应表中的算法色块一致；其余本案例数据集以表格呈现。

主要指标：`case_score`、`functionality_score`、`test_pass_rate`、`pep8_score`、
`modularity_score`、`reference_sequence_length`、`reference_page_span`、`frame_count_min/max`、
`curve_sample_count`、`best_algorithm`、`best_algorithm_average_fault_rate`、
`fifo/lru/opt_average_fault_rate`、`belady_anomaly_frame_count`。

## 检出规则

基座的通用规则（`code_issues`）见 `src/ai_tutor_backend/static_evaluation.py`。
下表是本案例在 `paging_issues` 中额外给出的分页专用规则：

| 规则 | 级别 | 触发条件 |
| --- | --- | --- |
| `NO_REPLACEMENT_ALGORITHM` | 错误 | FIFO / LRU / OPT 三项全部缺失 |
| `MISSING_FAULT_HANDLING` | 错误 | 没有缺页判断或换入处理 |
| `FLOAT_DIVISION_FOR_PAGE` | 错误 | 全文只有浮点除法 `/`，没有 `//`、`%` 或 `divmod` |
| `UNSAFE_DYNAMIC_EXECUTION` | 错误 | 使用 `eval`、`exec`、`compile` 等高风险调用 |
| `FIXED_FRAME_COUNT` | 注意 | 硬编码页框数且未扫描多档页框数 |
| `NO_FRAME_SWEEP` | 注意 | 未生成页框数与缺页率的对应关系 |
| `MISSING_FAULT_RATE` | 注意 | 没有缺页率统计逻辑 |
| `NO_EXCEPTION_HANDLING` | 注意 | 存在除法但既无 `try-except` 也无 `raise` |
| `GLOBAL_VARS` | 注意 | `global` 声明超过 3 处 |
| `UNBOUNDED_LOOP` | 注意 | 存在 `while True` |
| `MISSING_MAIN_GUARD` | 规范 | 缺少 `if __name__ == "__main__":` |
| `MISSING_TYPE_ANNOTATION` | 质量 | 函数超过 2 个且完全没有类型注解 |

## 评测限制

- 本案例不执行学生代码，只能判断代码结构与可识别的实现迹象；把算法写在文档字符串里不会得分，
  但通过间接调用、反射或动态生成的方式实现可能漏报。
- 静态检查判定的是“是否写了要求的结构”，不验证数值结果是否正确；缺页率数值是否正确应由学生
  用本页给出的参考曲线自行对照。
- 曲线与对应表由基座参考实现产出，反映的是标准答案，与被测代码是否真的能算出同样数据无关。
- 页面显示的结论应作为自动初筛，并允许教师展开证据后人工复核。