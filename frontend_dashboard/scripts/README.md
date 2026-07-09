# 脚本说明

脚本都整理在 `scripts` 目录下，按功能分组。

## web

用于启动本地 Web 前端页面。

- `scripts/web/start-web.bat`
- `scripts/web/start-web.ps1`

平时双击 `scripts/web/start-web.bat` 即可启动网页。

## api

用于启动本地 FastAPI 后端，提供 AI 助手文字对话和语音识别接口。

- `scripts/api/start-api.bat`
- `scripts/api/start-api.ps1`

首次启动会自动创建 `backend_api/.venv` 并安装依赖。真实语音识别需要在 `backend_api/.env` 中填写：

```text
SPEECH_TRANSCRIBE_API_KEY=你的语音识别 API Key
```

或者：

```text
OPENAI_API_KEY=你的 API Key
```

## git

用于把当前 `pro` 工程导入并推送到 GitHub 仓库的 `frontend_dashboard/` 目录。

- `scripts/git/push-frontend.bat`
- `scripts/git/push-frontend.ps1`

网络稳定、GitHub 登录正常时，双击 `scripts/git/push-frontend.bat`，输入本次修改备注即可推送。
