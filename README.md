# 知行课程助手

本仓库按前后端职责分离存放：

```text
backend/   Python API、案例插件、SQLite 数据、测试与测试代码
frontend/  独立的 HTML、CSS、JavaScript 展示前端
docs/      接口、案例接入、AI 助手与代码查重说明
```

后端内部采用包级解耦：`course_assistant_ai` 负责 AI 能力，`assignment_grading` 负责作业
批改，`ai_tutor_backend` 仅在应用组合层装配二者。AI 包不依赖批改模型、案例或数据库。

## 快速启动

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e "backend[dev]"
$env:SPARK_API_KEY = "你的 API Key"
uvicorn ai_tutor_backend.main:app --reload
```

默认访问 `http://127.0.0.1:8000/`。后端会以兼容模式托管 `frontend/dist/`，也可以设置
`AI_TUTOR_SERVE_FRONTEND=0` 后分别部署前端与后端。完整说明见 [docs/README.md](docs/README.md)。
