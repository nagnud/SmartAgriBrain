import {
  addMockKnowledgeItem,
  analyzeMockKnowledge,
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
  DiseasePhotoInfo,
  DiseaseDetectionResult,
  ExpertChatRequest,
  ExpertChatResponse,
  HistoryPoint,
  KnowledgeAnalyzeResult,
  KnowledgeBaseInfo,
  KnowledgeItemInfo,
  KnowledgeTextAddResult,
  PersistedDashboardState,
  TelemetryPayload,
  WeatherPayload,
} from '../types';

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
const useMock = import.meta.env.VITE_USE_MOCK !== 'false';
const useMockAssistant = import.meta.env.VITE_USE_MOCK_ASSISTANT === undefined
  ? useMock
  : import.meta.env.VITE_USE_MOCK_ASSISTANT !== 'false';
const useMockAiAdvice = import.meta.env.VITE_USE_MOCK_AI_ADVICE === undefined
  ? useMock
  : import.meta.env.VITE_USE_MOCK_AI_ADVICE !== 'false';
const useMockKnowledge = import.meta.env.VITE_USE_MOCK_KNOWLEDGE === undefined
  ? useMock
  : import.meta.env.VITE_USE_MOCK_KNOWLEDGE !== 'false';
const dashboardStateStorageKey = 'smartagribrain-dashboard-state';

type RequestJsonInit = RequestInit & {
  timeoutMs?: number;
};

async function requestJson<T>(path: string, init?: RequestJsonInit): Promise<T> {
  const { timeoutMs, ...requestInit } = init ?? {};
  const controller = timeoutMs ? new AbortController() : null;
  const timeoutId = timeoutMs && controller
    ? window.setTimeout(() => controller.abort(), timeoutMs)
    : undefined;
  let response!: Response;
  try {
    response = await fetch(`${apiBaseUrl}${path}`, {
      headers: {
        'Content-Type': 'application/json',
        ...(requestInit.headers ?? {}),
      },
      ...requestInit,
      signal: controller?.signal ?? requestInit.signal,
    });
  } finally {
    if (timeoutId) {
      window.clearTimeout(timeoutId);
    }
  }
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return response.json() as Promise<T>;
}

function resolveApiUrl(url: string): string {
  if (!url || /^(https?:|blob:|data:)/i.test(url)) {
    return url;
  }
  return `${apiBaseUrl}${url.startsWith('/') ? url : `/${url}`}`;
}

function normalizeDiseasePhoto(item: DiseasePhotoInfo): DiseasePhotoInfo {
  return {
    ...item,
    url: resolveApiUrl(item.url),
  };
}

function readLocalDashboardState(): PersistedDashboardState | null {
  if (typeof window === 'undefined') {
    return null;
  }
  try {
    const raw = window.localStorage.getItem(dashboardStateStorageKey);
    if (!raw) {
      return null;
    }
    const parsed = JSON.parse(raw) as PersistedDashboardState;
    return parsed && typeof parsed === 'object' ? parsed : null;
  } catch (error) {
    console.warn('Local dashboard state read failed.', error);
    return null;
  }
}

function writeLocalDashboardState(value: PersistedDashboardState): void {
  if (typeof window === 'undefined') {
    return;
  }
  try {
    window.localStorage.setItem(dashboardStateStorageKey, JSON.stringify(value));
  } catch (error) {
    console.warn('Local dashboard state save failed.', error);
  }
}

function buildDisconnectedAiAnalysis(latest: TelemetryPayload, detail = 'AI 服务暂时不可用。'): AiAnalysisResponse {
  return {
    device_id: latest.device_id,
    crop: 'tomato',
    ai_connected: false,
    risk_level: 'low',
    risk_score: 0,
    risk_status: 'AI 未连接',
    risk_factors: [
      {
        key: 'ai_disconnected',
        label: 'AI 未连接',
        detail,
        state: 'neutral',
      },
    ],
    summary: 'AI 未连接，暂时无法生成风险指数和农事建议。',
    suggestions: ['请检查 DeepSeek API Key、后端服务和网络连接后重新生成 AI 分析。'],
    commands: [],
    basis: ['未连接 AI 服务，本次未生成 AI 分析结果。'],
    updated_at: Date.now(),
  };
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
  if (useMockAiAdvice) {
    return buildDisconnectedAiAnalysis(latest, '当前前端配置为不请求 AI 农事建议接口。');
  }
  try {
    return await requestJson<AiAnalysisResponse>('/api/ai/analyze', {
      method: 'POST',
      body: JSON.stringify({
        device_id: latest.device_id,
        crop: 'tomato',
        sensors: latest.sensors,
        status: latest.status,
      }),
      timeoutMs: 2500,
    });
  } catch (error) {
    console.warn('AI farm advice API unavailable.', error);
    return buildDisconnectedAiAnalysis(latest, 'AI 农事建议接口不可用，请检查后端服务。');
  }
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

export async function getPersistedDashboardState(): Promise<PersistedDashboardState | null> {
  const localState = readLocalDashboardState();
  if (localState) {
    return localState;
  }
  try {
    const result = await requestJson<{ key: string; value: PersistedDashboardState }>('/api/v1/state/dashboard', {
      timeoutMs: 600,
    });
    const backendState = result.value && typeof result.value === 'object' ? result.value : null;
    if (backendState && Object.keys(backendState).length > 0) {
      writeLocalDashboardState(backendState);
      return backendState;
    }
    return null;
  } catch (error) {
    console.warn('Persisted dashboard state unavailable.', error);
    return localState;
  }
}

export async function savePersistedDashboardState(value: PersistedDashboardState): Promise<void> {
  writeLocalDashboardState(value);
  try {
    await requestJson<{ key: string; value: PersistedDashboardState; updatedAt: string }>('/api/v1/state/dashboard', {
      method: 'POST',
      body: JSON.stringify({ value }),
      timeoutMs: 1200,
    });
  } catch (error) {
    console.warn('Persisted dashboard state save failed.', error);
  }
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

export async function uploadDiseasePhoto(file: File): Promise<DiseasePhotoInfo> {
  const formData = new FormData();
  formData.append('image', file);
  const response = await fetch(`${apiBaseUrl}/api/v1/photos/disease/upload`, {
    method: 'POST',
    body: formData,
  });
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return normalizeDiseasePhoto(await response.json() as DiseasePhotoInfo);
}

export async function getDiseasePhotos(): Promise<DiseasePhotoInfo[]> {
  const result = await requestJson<{ items: DiseasePhotoInfo[] }>('/api/v1/photos/disease/list', { timeoutMs: 2500 });
  return result.items.map(normalizeDiseasePhoto);
}

export async function getDiseasePhoto(photoId: number): Promise<DiseasePhotoInfo> {
  const result = await requestJson<DiseasePhotoInfo>(`/api/v1/photos/disease/${encodeURIComponent(photoId)}`, {
    timeoutMs: 2500,
  });
  return normalizeDiseasePhoto(result);
}

export async function saveDiseasePhotoAnalysis(
  photoId: number,
  analysisResult: DiseaseDetectionResult,
): Promise<DiseasePhotoInfo> {
  const result = await requestJson<DiseasePhotoInfo>(`/api/v1/photos/disease/${encodeURIComponent(photoId)}/analysis`, {
    method: 'POST',
    body: JSON.stringify({ analysisResult }),
  });
  return normalizeDiseasePhoto(result);
}

export async function deleteDiseasePhoto(photoId: number): Promise<void> {
  await requestJson<{ success: boolean }>(`/api/v1/photos/disease/${encodeURIComponent(photoId)}`, {
    method: 'DELETE',
  });
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

export async function getKnowledgeBases(): Promise<KnowledgeBaseInfo[]> {
  if (useMockKnowledge) {
    return mockKnowledgeBases;
  }
  const result = await requestJson<{ items: KnowledgeBaseInfo[] }>('/api/v1/kb/list', { timeoutMs: 2500 });
  return result.items;
}

export async function getKnowledgeItems(kbId: number): Promise<KnowledgeItemInfo[]> {
  if (useMockKnowledge) {
    return mockKnowledgeItems.filter((item) => item.kbId === kbId);
  }
  const result = await requestJson<{ items: KnowledgeItemInfo[] }>(`/api/v1/kb/items?kbId=${encodeURIComponent(kbId)}`, { timeoutMs: 2500 });
  return result.items;
}

export async function createKnowledgeBase(name: string, description: string): Promise<KnowledgeBaseInfo> {
  if (useMockKnowledge) {
    return createMockKnowledgeBase(name, description);
  }
  return requestJson<KnowledgeBaseInfo>('/api/v1/kb/create', {
    method: 'POST',
    body: JSON.stringify({ name, description }),
  });
}

export async function updateKnowledgeBase(kbId: number, name: string, description: string): Promise<KnowledgeBaseInfo> {
  if (useMockKnowledge) {
    return updateMockKnowledgeBase(kbId, name, description);
  }
  return requestJson<KnowledgeBaseInfo>('/api/v1/kb/update', {
    method: 'POST',
    body: JSON.stringify({ kbId, name, description }),
  });
}

export async function deleteKnowledgeBase(kbId: number): Promise<void> {
  if (useMockKnowledge) {
    deleteMockKnowledgeBase(kbId);
    return;
  }
  await requestJson<{ success: boolean }>('/api/v1/kb/delete', {
    method: 'POST',
    body: JSON.stringify({ kbId }),
  });
}

export async function addKnowledgeItem(kbId: number, title: string, content: string): Promise<KnowledgeTextAddResult> {
  if (useMockKnowledge) {
    return addMockKnowledgeItem(kbId, title, content);
  }
  return requestJson<KnowledgeTextAddResult>('/api/v1/kb/add_text', {
    method: 'POST',
    body: JSON.stringify({ kbId, title, content }),
  });
}

export async function updateKnowledgeItem(kbId: number, itemId: number, title: string, content: string): Promise<KnowledgeTextAddResult> {
  if (useMockKnowledge) {
    return updateMockKnowledgeItem(kbId, itemId, title, content);
  }
  return requestJson<KnowledgeTextAddResult>('/api/v1/kb/item/update', {
    method: 'POST',
    body: JSON.stringify({ kbId, itemId, title, content }),
  });
}

export async function deleteKnowledgeItem(kbId: number, itemId: number): Promise<void> {
  if (useMockKnowledge) {
    deleteMockKnowledgeItem(kbId, itemId);
    return;
  }
  await requestJson<{ success: boolean }>('/api/v1/kb/item/delete', {
    method: 'POST',
    body: JSON.stringify({ kbId, itemId }),
  });
}

export async function analyzeKnowledge(kbId: number, fieldId: string, question: string): Promise<KnowledgeAnalyzeResult> {
  if (useMockKnowledge) {
    return analyzeMockKnowledge(kbId, question);
  }
  return requestJson<KnowledgeAnalyzeResult>('/api/v1/kb/analyze', {
    method: 'POST',
    body: JSON.stringify({ kbId, fieldId, question }),
  });
}
