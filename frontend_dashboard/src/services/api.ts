import {
  addMockKnowledgeItem,
  analyzeMockKnowledge,
  buildMockAiAnalysis,
  buildMockDiseaseDetection,
  buildMockExpertChat,
  buildMockWeather,
  buildMockHistory,
  buildMockLatest,
  createMockKnowledgeBase,
  deleteMockKnowledgeBase,
  deleteMockKnowledgeItem,
  executeMockCommand,
  mockAlarms,
  mockKnowledgeBases,
  mockKnowledgeItems,
  updateMockKnowledgeBase,
  updateMockKnowledgeItem,
} from '../mock/data';
import type {
  AiAnalysisResponse,
  AlarmRecord,
  CommandResult,
  DeviceCommand,
  DiseaseDetectionResult,
  ExpertChatRequest,
  ExpertChatResponse,
  HistoryPoint,
  KnowledgeAnalyzeResult,
  KnowledgeBaseInfo,
  KnowledgeItemInfo,
  KnowledgeTextAddResult,
  TelemetryPayload,
  VoiceTranscriptionResponse,
  VoiceTranscriptionStatus,
  WeatherPayload,
} from '../types';

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
const useMock = import.meta.env.VITE_USE_MOCK !== 'false';
const useMockAssistant = import.meta.env.VITE_USE_MOCK_ASSISTANT === undefined
  ? useMock
  : import.meta.env.VITE_USE_MOCK_ASSISTANT !== 'false';

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
    ...init,
  });
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return response.json() as Promise<T>;
}

export async function getLatestTelemetry(): Promise<TelemetryPayload> {
  if (useMock) {
    return buildMockLatest();
  }
  return requestJson<TelemetryPayload>('/api/device/latest');
}

export async function getDeviceHistory(): Promise<HistoryPoint[]> {
  if (useMock) {
    return buildMockHistory();
  }
  return requestJson<HistoryPoint[]>('/api/device/history');
}

export async function getDeviceStatus(): Promise<TelemetryPayload['status']> {
  if (useMock) {
    return buildMockLatest().status;
  }
  return requestJson<TelemetryPayload['status']>('/api/device/status');
}

export async function analyzeFarm(latest: TelemetryPayload): Promise<AiAnalysisResponse> {
  if (useMock) {
    return buildMockAiAnalysis(latest);
  }
  return requestJson<AiAnalysisResponse>('/api/ai/analyze', {
    method: 'POST',
    body: JSON.stringify({
      device_id: latest.device_id,
      crop: 'tomato',
      sensors: latest.sensors,
      status: latest.status,
    }),
  });
}

export async function sendDeviceCommand(command: DeviceCommand): Promise<CommandResult> {
  if (useMock) {
    return executeMockCommand(command);
  }
  return requestJson<CommandResult>('/api/device/command', {
    method: 'POST',
    body: JSON.stringify(command),
  });
}

export async function getAlarmRecords(): Promise<AlarmRecord[]> {
  if (useMock) {
    return mockAlarms;
  }
  return requestJson<AlarmRecord[]>('/api/device/alarms');
}

export async function getCurrentWeather(): Promise<WeatherPayload> {
  if (useMock) {
    return buildMockWeather();
  }
  return requestJson<WeatherPayload>('/api/weather/current');
}

export async function analyzeDiseaseImage(file: File, imageUrl: string): Promise<DiseaseDetectionResult> {
  if (useMock) {
    return buildMockDiseaseDetection(imageUrl);
  }
  const formData = new FormData();
  formData.append('image', file);
  const response = await fetch(`${apiBaseUrl}/api/vision/disease`, {
    method: 'POST',
    body: formData,
  });
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return response.json() as Promise<DiseaseDetectionResult>;
}

export async function sendExpertChatMessage(payload: ExpertChatRequest): Promise<ExpertChatResponse> {
  if (useMockAssistant) {
    return buildMockExpertChat(payload);
  }
  const response = await requestJson<ExpertChatResponse>('/api/v1/assistant/chat', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
  const actions = response.actions ?? response.message.suggested_actions ?? [];
  return {
    ...response,
    message: {
      ...response.message,
      references: response.message.references ?? response.references ?? [],
      suggested_actions: actions.map((action) => ({ ...action, status: action.status ?? 'pending' })),
    },
    actions,
  };
}

export async function transcribeVoiceChunk(payload: {
  audio: Blob;
  sessionId: string;
  sequence: number;
  isFinal: boolean;
  mimeType: string;
  language?: string;
}): Promise<VoiceTranscriptionResponse> {
  if (useMockAssistant) {
    return {
      ok: false,
      text: '',
      partial: !payload.isFinal,
      final: payload.isFinal,
      message: '语音识别需要关闭助手 Mock，并连接后端服务。',
    };
  }
  const formData = new FormData();
  formData.append('audio', payload.audio, `voice-${payload.sequence}.webm`);
  formData.append('session_id', payload.sessionId);
  formData.append('sequence', String(payload.sequence));
  formData.append('is_final', String(payload.isFinal));
  formData.append('language', payload.language ?? 'zh-CN');
  formData.append('mime_type', payload.mimeType);
  const response = await fetch(`${apiBaseUrl}/api/v1/assistant/voice/transcribe`, {
    method: 'POST',
    body: formData,
  });
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return response.json() as Promise<VoiceTranscriptionResponse>;
}

export async function getVoiceTranscriptionStatus(): Promise<VoiceTranscriptionStatus> {
  if (useMockAssistant) {
    return {
      ok: true,
      configured: false,
      provider: 'browser',
      model: 'Web Speech API',
      message: '助手 Mock 模式下使用浏览器语音识别。',
    };
  }

  try {
    const response = await fetch(`${apiBaseUrl}/api/v1/assistant/voice/status`);
    if (!response.ok) {
      throw new Error(`${response.status} ${response.statusText}`);
    }
    return response.json() as Promise<VoiceTranscriptionStatus>;
  } catch (error) {
    const message = error instanceof Error ? error.message : 'unknown error';
    return {
      ok: false,
      configured: true,
      provider: 'backend',
      model: '',
      message: `语音状态接口不可用，将继续尝试后端识别：${message}`,
    };
  }
}

export async function getKnowledgeBases(): Promise<KnowledgeBaseInfo[]> {
  if (useMock) {
    return mockKnowledgeBases;
  }
  const result = await requestJson<{ items: KnowledgeBaseInfo[] }>('/api/v1/kb/list');
  return result.items;
}

export async function getKnowledgeItems(kbId: number): Promise<KnowledgeItemInfo[]> {
  if (useMock) {
    return mockKnowledgeItems.filter((item) => item.kbId === kbId);
  }
  const result = await requestJson<{ items: KnowledgeItemInfo[] }>(`/api/v1/kb/items?kbId=${encodeURIComponent(kbId)}`);
  return result.items;
}

export async function createKnowledgeBase(name: string, description: string): Promise<KnowledgeBaseInfo> {
  if (useMock) {
    return createMockKnowledgeBase(name, description);
  }
  return requestJson<KnowledgeBaseInfo>('/api/v1/kb/create', {
    method: 'POST',
    body: JSON.stringify({ name, description }),
  });
}

export async function updateKnowledgeBase(kbId: number, name: string, description: string): Promise<KnowledgeBaseInfo> {
  if (useMock) {
    return updateMockKnowledgeBase(kbId, name, description);
  }
  return requestJson<KnowledgeBaseInfo>('/api/v1/kb/update', {
    method: 'POST',
    body: JSON.stringify({ kbId, name, description }),
  });
}

export async function deleteKnowledgeBase(kbId: number): Promise<void> {
  if (useMock) {
    deleteMockKnowledgeBase(kbId);
    return;
  }
  await requestJson<{ success: boolean }>('/api/v1/kb/delete', {
    method: 'POST',
    body: JSON.stringify({ kbId }),
  });
}

export async function addKnowledgeItem(kbId: number, title: string, content: string): Promise<KnowledgeTextAddResult> {
  if (useMock) {
    return addMockKnowledgeItem(kbId, title, content);
  }
  return requestJson<KnowledgeTextAddResult>('/api/v1/kb/add_text', {
    method: 'POST',
    body: JSON.stringify({ kbId, title, content }),
  });
}

export async function updateKnowledgeItem(kbId: number, itemId: number, title: string, content: string): Promise<KnowledgeTextAddResult> {
  if (useMock) {
    return updateMockKnowledgeItem(kbId, itemId, title, content);
  }
  return requestJson<KnowledgeTextAddResult>('/api/v1/kb/item/update', {
    method: 'POST',
    body: JSON.stringify({ kbId, itemId, title, content }),
  });
}

export async function deleteKnowledgeItem(kbId: number, itemId: number): Promise<void> {
  if (useMock) {
    deleteMockKnowledgeItem(kbId, itemId);
    return;
  }
  await requestJson<{ success: boolean }>('/api/v1/kb/item/delete', {
    method: 'POST',
    body: JSON.stringify({ kbId, itemId }),
  });
}

export async function analyzeKnowledge(kbId: number, fieldId: string, question: string): Promise<KnowledgeAnalyzeResult> {
  if (useMock) {
    return analyzeMockKnowledge(kbId, question);
  }
  return requestJson<KnowledgeAnalyzeResult>('/api/v1/kb/analyze', {
    method: 'POST',
    body: JSON.stringify({ kbId, fieldId, question }),
  });
}
