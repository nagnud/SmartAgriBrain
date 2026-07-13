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

设备默认继续使用 HTTP 通信。只有在 `backend_api/.env` 中同时设置 `MQTT_ENABLED=true`、MQTT 服务器地址和 `DEVICE_COMMAND_TRANSPORT=mqtt` 时，后端才会启用 MQTT；未配置时不会发起连接，也不会影响现有功能。

AI 助手语音输入现在由浏览器 Web Speech API 实时写入输入框，不需要后端语音识别 API Key。

## git

用于把当前 `pro` 工程导入并推送到 GitHub 仓库的 `frontend_dashboard/` 目录。

- `scripts/git/push-frontend.bat`
- `scripts/git/push-frontend.ps1`

双击 `scripts/git/push-frontend.bat`，输入本次修改备注即可推送。脚本固定通过
GitHub SSH 的 443 端口连接，不会修改电脑的全局 Git 配置。

第一次运行会创建一对仅用于本项目推送的 SSH 密钥，并打开 GitHub 的 SSH Key
设置页面。按窗口说明把公钥添加到受邀的 GitHub 账号后，以后无需 token。
旧的 `push输入.md` 明文 token 方案已经停用；不要重新创建该文件，并应在 GitHub
设置中撤销曾经保存在其中的旧 token。

如果网络不可用，提交会安全保存在 `.push-cache`，并明确显示“尚未上传”。网络
恢复后再次双击同一个脚本即可继续推送，不需要修改或重新生成脚本。

可以使用下面的命令做只读检查；它不会创建提交或连接远端：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/git/push-frontend.ps1 -ValidateOnly
```
