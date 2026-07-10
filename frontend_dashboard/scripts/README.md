# 脚本说明

脚本都整理在 `scripts` 目录下，按功能分组。

## web

用于启动本地 Web 前端页面。

- `scripts/web/start-web.bat`
- `scripts/web/start-web.ps1`

平时双击 `scripts/web/start-web.bat` 即可启动网页。

## backend

用于启动本地 FastAPI 后端，提供 AI 农事建议和 AI 助手文字对话接口。

- `scripts/backend/start-backend.bat`
- `scripts/backend/start-backend.ps1`

首次启动会自动创建 `backend_api/.venv` 并安装依赖。后端会读取 `backend_api/.env` 中的 DeepSeek 配置；`.env` 是本地密钥文件，不要提交。别人拿到代码后可以复制 `backend_api/.env.example` 并填入自己的 Key：

```text
DEEPSEEK_API_KEY=your-deepseek-api-key
```

知识库使用后端数据库保存。默认配置为本地 SQLite，首次启动会自动创建 `backend_api/smartagribrain.db` 并写入初始知识库：

```text
DATABASE_URL=sqlite:///./smartagribrain.db
```

以后部署多人线上版时，可以在 `backend_api/.env` 中把 `DATABASE_URL` 改为 PostgreSQL 地址。

AI 助手语音输入现在由浏览器 Web Speech API 实时写入输入框，不需要后端语音识别 API Key。

## git

用于把当前 `pro` 工程导入并推送到 GitHub 仓库的 `frontend_dashboard/` 目录。

- `scripts/git/push-frontend.bat`
- `scripts/git/push-frontend.ps1`

网络稳定、GitHub 登录正常时，双击 `scripts/git/push-frontend.bat`，输入本次修改备注即可推送。
