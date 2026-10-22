# AI 知识文档配置

此目录专门存放课程助手使用的知识文档。

- 默认文档：`default.md`
- 自定义文档：建议在本目录新增 Markdown 或 UTF-8 文本文件，不要直接覆盖默认文档。
- 配置变量：`AI_TUTOR_KNOWLEDGE_DOCUMENT`
- 最大读取字符数：`AI_TUTOR_KNOWLEDGE_MAX_CHARS`，默认 `20000`，可配置范围为 `1000` 至 `100000`。

相对路径以 `backend` 目录为基准。例如：

```env
AI_TUTOR_KNOWLEDGE_DOCUMENT=knowledge/computer_networks.md
```

当变量未配置、文件不存在、文件无法按 UTF-8 读取或内容为空时，系统会自动使用 `knowledge/default.md`。修改配置后需要重启后端服务。

知识文档只用于提供课程事实和学习背景，不能覆盖系统的学习范围、隐私保护和安全行为规范。
