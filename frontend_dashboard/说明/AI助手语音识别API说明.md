# AI 助手语音识别 API 说明

## 启动方式

双击：

```text
scripts\backend\start-backend.bat
```

后端默认启动在：

```text
http://localhost:8000
```

前端 `.env` 已指向：

```text
VITE_API_BASE_URL=http://localhost:8000
VITE_USE_MOCK_ASSISTANT=false
```

## 需要配置的 Key

复制 `backend_api\.env.example` 为 `backend_api\.env` 后填写：

```text
SPEECH_TRANSCRIBE_BASE_URL=https://api.openai.com/v1
SPEECH_TRANSCRIBE_API_KEY=你的语音识别 API Key
SPEECH_TRANSCRIBE_MODEL=whisper-1
SPEECH_TRANSCRIBE_TIMEOUT_SECONDS=45
```

也可以不写 `SPEECH_TRANSCRIBE_API_KEY`，改用：

```text
OPENAI_API_KEY=你的 API Key
```

## 前端调用接口

AI 助手录音后会调用：

```http
POST /api/v1/assistant/voice/transcribe
Content-Type: multipart/form-data
```

字段：

```text
audio       录音文件，前端 MediaRecorder 产生的 webm/ogg/mp4 分片
session_id 语音会话 ID
sequence   分片序号，从 0 开始
is_final   是否为最后一个分片
language   默认 zh-CN
mime_type  前端录音 MIME 类型
```

返回：

```json
{
  "ok": true,
  "text": "识别出的文字",
  "partial": false,
  "final": true,
  "message": "语音已识别"
}
```

如果没有配置 key，后端不会崩溃，会返回：

```json
{
  "ok": false,
  "text": "",
  "partial": true,
  "final": false,
  "message": "后端还没有配置语音识别 API Key，请设置 SPEECH_TRANSCRIBE_API_KEY 或 OPENAI_API_KEY。"
}
```
