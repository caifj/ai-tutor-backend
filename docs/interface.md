# 标准化输出接口 v1

本接口只规定所有教学案例共同遵守的数据契约，不规定案例内部算法。案例通过
`CaseAdapter` 注册后即可复用执行、持久化、JSON/CSV 导出和自动校对能力。

## JSON 结果信封

```json
{
  "schema_version": "1.0",
  "request_id": "UUID",
  "case_id": "由适配器注册的标识",
  "status": "succeeded",
  "payload": {
    "summary": "面向学生的结果摘要",
    "datasets": [
      {
        "name": "稳定的机器可读名称",
        "title": "前端展示名称",
        "columns": [
          {
            "key": "字段名",
            "title": "字段标题",
            "data_type": "string|integer|number|boolean|datetime|object|array",
            "unit": null,
            "description": null,
            "nullable": false
          }
        ],
        "rows": [{"字段名": "值"}]
      }
    ],
    "metrics": {},
    "diagnostics": [],
    "artifacts": []
  },
  "created_at": "ISO-8601 UTC 时间",
  "duration_ms": 1.23
}
```

`datasets` 能表达二维表、时间线、曲线采样点、树节点/边、日志等。对象或数组可以作为
单元格值；前端依据 `columns.data_type` 选择渲染组件。图片、文件等大对象放在
`artifacts` 中并返回 URI，不直接塞入 JSON。

提交包含 `source_code` 时，底座会按 `case_id` 与不同提交人的历史源码进行相似度审查。
浏览器前端通过 `metadata.submitter` 传递提交人；同一提交人的历史版本不参与互相扣分。
超过阈值后，结果的 `metrics`
会包含相似度、查重范围、原始分数和扣分后分数，`diagnostics` 会包含
`CODE_SIMILARITY_HIGH`。详细规则见 [code-similarity.md](code-similarity.md)。

## CSV 结果格式

CSV 采用稳定长表，而不是让不同案例各自定义表头：

```text
schema_version,request_id,case_id,status,record_type,dataset,row_index,field,value,value_type,unit
```

- `record_type`: `summary`、`metric`、`data`、`diagnostic` 或 `artifact`。
- `dataset` 和 `row_index`: 定位原 JSON 中的数据集与行。
- `field`: 列名或指标名。
- `value_type`: 保证读取方能恢复值类型；对象和数组以紧凑 JSON 写入 `value`。
- 文件使用 UTF-8 BOM，便于 Excel 直接打开中文内容。

## HTTP API

| 方法 | 路径 | 用途 |
|---|---|---|
| `GET` | `/health` | 健康检查 |
| `GET` | `/api/v1/cases` | 查询已注册案例 |
| `GET` | `/api/v1/cases/{case_id}` | 获取案例输入 schema 和输出数据集声明 |
| `POST` | `/api/v1/executions?format=json|csv` | 执行案例 |
| `GET` | `/api/v1/results/{request_id}?format=json|csv` | 读取/导出历史结果 |
| `POST` | `/api/v1/grades?format=json|csv` | 自动校对并生成错误讲解 |

服务启动后可在 `/docs` 查看并调试 OpenAPI 文档。

## 自动校对

`expected` 使用与执行结果相同的 `ResultPayload`。默认执行精确比较，也可设置：

```json
{
  "actual_result_id": "UUID",
  "expected": {"summary": "...", "datasets": [], "metrics": {}},
  "policy": {
    "mode": "numeric_tolerance",
    "absolute_tolerance": 0.001,
    "relative_tolerance": 0.000001,
    "ignore_row_order": true,
    "ignored_paths": ["$.metrics.runtime_ms"],
    "max_issues": 100
  }
}
```

校对结果包含总分、是否通过、差异 JSONPath、期望值、实际值和中文解释，可直接供前端
高亮错误。以后如需大模型生成更自然的讲解，可在 grading 服务上方增加 explanation provider，
无需改变结果协议。

