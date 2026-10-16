# AI Tutor Frontend

该目录是无构建步骤的独立 Web 前端，入口为 `dist/index.html`。

后端兼容模式会直接托管 `dist/`。如需前后端分别启动，可先编辑 `dist/config.js`：

```javascript
window.AI_TUTOR_API_BASE_URL = "http://127.0.0.1:8000";
```

随后使用任意静态服务器托管 `dist/`，例如：

```powershell
python -m http.server 5500 --directory frontend/dist
```

后端环境变量 `AI_TUTOR_CORS_ORIGINS` 应包含该前端地址。
