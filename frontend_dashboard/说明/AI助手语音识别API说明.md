# AI 助手语音输入说明

AI 助手语音输入现在由浏览器原生 Web Speech API 完成，识别结果会实时写入右侧 AI 助手的输入框。

## 使用方式

1. 使用 Chrome 或 Edge 打开本地前端页面。
2. 点击 AI 助手输入框左侧的麦克风按钮。
3. 允许浏览器使用麦克风后，说话内容会实时同步到输入框。
4. 再次点击麦克风按钮即可停止语音输入。

## 后端说明

后端不再提供语音识别接口，也不再调用 OpenAI/Whisper 兼容的 `/audio/transcriptions` API。

以下旧配置已不再需要：

```text
SPEECH_TRANSCRIBE_BASE_URL
SPEECH_TRANSCRIBE_API_KEY
SPEECH_TRANSCRIBE_MODEL
SPEECH_TRANSCRIBE_TIMEOUT_SECONDS
OPENAI_API_KEY
```

如果当前浏览器不支持 Web Speech API，AI 助手会提示改用 Chrome/Edge 或手动输入。
