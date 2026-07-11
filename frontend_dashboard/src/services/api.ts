import {
  addMockKnowledgeItem,
  analyzeMockKnowledge,
  buildMockExpertChat,
  buildMockWeatherBundle,
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
  WeatherBundle,
  WeatherCityOption,
  WeatherPayload,
} from '../types';
import { UserFacingError } from '../utils/format';

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
const useMockWeather = import.meta.env.VITE_USE_MOCK_WEATHER === undefined
  ? useMock
  : import.meta.env.VITE_USE_MOCK_WEATHER !== 'false';
const dashboardStateStorageKey = 'smartagribrain-dashboard-state';

type RequestJsonInit = RequestInit & {
  timeoutMs?: number;
};

function serviceErrorMessage(status: number): string {
  if (status === 401 || status === 403) {
    return '当前操作未获授权，请刷新页面后重试。';
  }
  if (status === 404) {
    return '没有找到相关内容，可能已被删除。';
  }
  if (status === 413) {
    return '图片不能超过 10MB。';
  }
  if (status === 429) {
    return '操作过于频繁，请稍等片刻再试。';
  }
  return status >= 500
    ? '服务暂时不可用，请稍后重试。'
    : '提交的内容无法处理，请检查后重试。';
}

async function throwServiceError(response: Response, operation: string): Promise<never> {
  let detail = '';
  try {
    detail = (await response.text()).slice(0, 800);
  } catch {
    // Keep the user-facing response independent from diagnostic parsing.
  }
  console.warn(`${operation} failed.`, {
    status: response.status,
    statusText: response.statusText,
    detail,
  });
  throw new UserFacingError(serviceErrorMessage(response.status));
}

export interface FarmAnalysisContext {
  weather?: WeatherPayload | null;
  weatherBundle?: WeatherBundle | null;
  history?: HistoryPoint[];
  disease?: DiseaseDetectionResult | null;
  cameraAnalysis?: DiseaseDetectionResult | null;
}

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
  } catch (error) {
    console.warn('Service request unavailable.', { path, error });
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new UserFacingError('等待时间过长，请稍后重试。', error);
    }
    throw new UserFacingError('网络连接不稳定，请检查网络后重试。', error);
  } finally {
    if (timeoutId) {
      window.clearTimeout(timeoutId);
    }
  }
  if (!response.ok) {
    await throwServiceError(response, path);
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

function buildDisconnectedAiAnalysis(latest: TelemetryPayload, detail = '智能分析暂时不可用，请稍后重试。'): AiAnalysisResponse {
  return {
    device_id: latest.device_id,
    crop: 'tomato',
    ai_connected: false,
    risk_level: 'low',
    risk_score: 0,
    risk_status: '智能分析暂不可用',
    risk_factors: [
      {
        key: 'ai_disconnected',
        label: '智能分析暂不可用',
        detail,
        state: 'neutral',
      },
    ],
    summary: '智能分析暂时不可用，本次没有生成风险判断和农事建议。',
    suggestions: ['请稍后重新生成；如持续无法使用，请联系平台管理员。'],
    commands: [],
    basis: ['本次智能分析未完成。'],
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

export async function analyzeFarm(
  latest: TelemetryPayload,
  context: FarmAnalysisContext = {},
): Promise<AiAnalysisResponse> {
  if (useMockAiAdvice) {
    return buildDisconnectedAiAnalysis(latest);
  }
  try {
    return await requestJson<AiAnalysisResponse>('/api/ai/analyze', {
      method: 'POST',
      body: JSON.stringify({
        device_id: latest.device_id,
        crop: 'tomato',
        sensors: latest.sensors,
        status: latest.status,
        weather: context.weather ?? null,
        weather_bundle: context.weatherBundle ?? null,
        history: context.history ?? [],
        disease: context.disease ?? null,
        camera_analysis: context.cameraAnalysis ?? null,
      }),
      timeoutMs: 120000,
    });
  } catch (error) {
    console.warn('AI farm advice API unavailable.', error);
    return buildDisconnectedAiAnalysis(latest);
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

export async function getCurrentWeather(city?: string): Promise<WeatherPayload> {
  if (useMockWeather) {
    return buildMockWeather();
  }
  const query = city ? `?city=${encodeURIComponent(city)}` : '';
  return requestJson<WeatherPayload>(`/api/weather/current${query}`);
}

export async function getWeatherBundle(city?: string): Promise<WeatherBundle> {
  if (useMockWeather) {
    return buildMockWeatherBundle(city);
  }
  const query = city ? `?city=${encodeURIComponent(city)}` : '';
  return requestJson<WeatherBundle>(`/api/weather/bundle${query}`);
}

export async function getWeatherCities(query: string): Promise<WeatherCityOption[]> {
  if (useMockWeather) {
    const value = query.trim() || '无锡';
    const cities: WeatherCityOption[] = [
      { id: '无锡', name: '无锡', path: '无锡,江苏,中国', country: 'CN' },
      { id: '北京', name: '北京', path: '北京,北京,中国', country: 'CN' },
      { id: '上海', name: '上海', path: '上海,上海,中国', country: 'CN' },
      { id: '南京', name: '南京', path: '南京,江苏,中国', country: 'CN' },
      { id: '苏州', name: '苏州', path: '苏州,江苏,中国', country: 'CN' },
      { id: '杭州', name: '杭州', path: '杭州,浙江,中国', country: 'CN' },
      { id: '广州', name: '广州', path: '广州,广东,中国', country: 'CN' },
      { id: '深圳', name: '深圳', path: '深圳,广东,中国', country: 'CN' },
      { id: '成都', name: '成都', path: '成都,四川,中国', country: 'CN' },
      { id: '武汉', name: '武汉', path: '武汉,湖北,中国', country: 'CN' },
      { id: '西安', name: '西安', path: '西安,陕西,中国', country: 'CN' },
      { id: '郑州', name: '郑州', path: '郑州,河南,中国', country: 'CN' },
    ];
    return cities.filter((city) => `${city.name}${city.path}`.includes(value)).slice(0, 8);
  }
  const result = await requestJson<{ items: WeatherCityOption[] }>(`/api/weather/cities?q=${encodeURIComponent(query)}`);
  return result.items;
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
  const formData = new FormData();
  formData.append('image', file);
  const response = await fetch(`${apiBaseUrl}/api/vision/disease`, {
    method: 'POST',
    body: formData,
  });
  if (!response.ok) {
    await throwServiceError(response, 'Disease image analysis');
  }
  return response.json() as Promise<DiseaseDetectionResult>;
}

export async function analyzeGrowthFrame(file: File, imageUrl: string): Promise<DiseaseDetectionResult> {
  // Future growth-specific AI API should replace this wrapper without changing the camera UI.
  return analyzeDiseaseImage(file, imageUrl);
}

export async function uploadDiseasePhoto(file: File): Promise<DiseasePhotoInfo> {
  const formData = new FormData();
  formData.append('image', file);
  const response = await fetch(`${apiBaseUrl}/api/v1/photos/disease/upload`, {
    method: 'POST',
    body: formData,
  });
  if (!response.ok) {
    await throwServiceError(response, 'Disease photo upload');
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
