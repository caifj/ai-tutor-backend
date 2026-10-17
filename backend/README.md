# AI Tutor Backend

该目录是独立 Python 后端工程，包含：

- `src/ai_tutor_backend/`：统一 API、AI 助手、查重、执行与结果存储；
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
