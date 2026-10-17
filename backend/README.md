# AI Tutor Backend

该目录是独立 Python 后端工程，包含：

- `src/ai_tutor_backend/`：HTTP API、案例执行、数据契约、存储与组合根；
- `src/course_assistant_ai/`：独立 AI 问答、行为规范、模型客户端和路由；
- `src/assignment_grading/`：独立结果批改与代码相似度检查；
- `cases/`：正式案例和接入示例；
- `tests/`：后端自动化测试；
- `testcase/`：供案例评测使用的学生代码样例；
- `var/`：运行时 SQLite 数据，不进入 Git。

从仓库根目录安装和测试：

```powershell
python -m pip install -e "backend[dev]"
python -m pytest backend/tests
python -m ruff check backend
```

后端默认兼容托管仓库中的 `frontend/dist/`。设置 `AI_TUTOR_SERVE_FRONTEND=0` 可关闭；
独立前端来源通过 `AI_TUTOR_CORS_ORIGINS` 配置。

三个 Python 包按单向依赖组合：API 组合层可以装配 AI 和批改包；AI 包不导入后端、
案例、存储或批改模型，批改包也不导入 AI 包。`tests/test_architecture.py` 会持续检查边界。
