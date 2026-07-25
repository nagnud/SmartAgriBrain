import type {
  AiAnalysisResponse,
  AgriSourceInfo,
  AlarmRecord,
  AlarmSettingsResponse,
  CurrentCropPositionsResult,
  DeviceHealth,
  DiseasePhotoInfo,
  DiseaseDetectionResult,
  CameraPositionConfig,
  BackendCameraConfig,
  ExpertChatRequest,
  ExpertChatResponse,
  HistoryPoint,
  KnowledgeAnalyzeResult,
  KnowledgeBaseInfo,
  KnowledgeItemInfo,
  KnowledgeTextAddResult,
  MetricTargetRange,
  PersistedDashboardState,
  TelemetryPayload,
  WeatherBundle,
  WeatherCityOption,
  WeatherPayload,
  HistoryMetricKey,
  RetrievalMode,
  SharedAssistantAction,
  SharedAssistantConversation,
  SharedAssistantMessage,
  SiteState,
  PositionLocateResult,
  AssistantTurnAccepted,
  AssistantTurnEvent,
  AssistantTurnRequest,
  AssistantPreferenceItem,
  WaterGunState,
  WaterGunTargetInput,
} from '../types';
import { UserFacingError } from '../utils/format';
import chinaWeatherRegions from '../../shared_data/china_weather_regions.json';

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export function resolveApiAssetUrl(path: string | undefined): string {
  if (!path) return '';
  if (/^(?:https?:|blob:|data:)/i.test(path)) return path;
  return `${apiBaseUrl.replace(/\/$/, '')}/${path.replace(/^\//, '')}`;
}
const dashboardStateStorageKey = 'smartagribrain-dashboard-state';
export const defaultSiteId = import.meta.env.VITE_SITE_ID || 'greenhouse_001';

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
  let userDetail = '';
  try {
    detail = (await response.text()).slice(0, 800);
    const parsed = JSON.parse(detail) as { detail?: unknown };
    if (typeof parsed.detail === 'string' && parsed.detail.trim().length > 0) {
      userDetail = parsed.detail.trim().slice(0, 300);
    }
  } catch {
    // Keep the user-facing response independent from diagnostic parsing.
  }
  console.warn(`${operation} failed.`, {
    status: response.status,
    statusText: response.statusText,
    detail,
  });
  throw new UserFacingError(userDetail || serviceErrorMessage(response.status));
}

export interface FarmAnalysisContext {
  weather?: WeatherPayload | null;
  weatherBundle?: WeatherBundle | null;
  history?: HistoryPoint[];
  disease?: DiseaseDetectionResult | null;
  cameraAnalysis?: DiseaseDetectionResult | null;
  retrievalMode?: RetrievalMode;
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

export function backendCameraStreamUrl(): string {
  return `${apiBaseUrl}/api/v1/camera/stream.mjpg`;
}

export async function getBackendCameraStatus(): Promise<{ ready: boolean; error?: string; captured_at?: number }> {
  return requestJson<{ ready: boolean; error?: string; captured_at?: number }>('/api/v1/camera/status', {
    timeoutMs: 5000,
  });
}

export async function getBackendCameraConfig(): Promise<BackendCameraConfig> {
  const status = await requestJson<{ config: BackendCameraConfig }>('/api/v1/camera/status', { timeoutMs: 5000 });
  return status.config;
}

export async function saveBackendCameraConfig(config: BackendCameraConfig): Promise<BackendCameraConfig> {
  const result = await requestJson<{ success: boolean; config: BackendCameraConfig }>('/api/v1/camera/config', {
    method: 'PUT',
    body: JSON.stringify(config),
  });
  return result.config;
}

export async function captureBackendCameraFrame(): Promise<File> {
  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl}/api/v1/camera/frame.jpg?ts=${Date.now()}`, { cache: 'no-store' });
  } catch (error) {
    throw new UserFacingError('无法连接电脑后端摄像头。', error);
  }
  if (!response.ok) await throwServiceError(response, 'Camera snapshot');
  const blob = await response.blob();
  return new File([blob], `camera-frame-${Date.now()}.jpg`, { type: 'image/jpeg' });
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

export async function getLatestTelemetry(): Promise<TelemetryPayload> {
  return siteStateToTelemetry(await getSiteState());
}

export async function getSiteState(siteId = defaultSiteId): Promise<SiteState> {
  return requestJson<SiteState>(`/api/v1/sites/${encodeURIComponent(siteId)}/state`);
}

export function siteStateToTelemetry(state: SiteState): TelemetryPayload {
  const sensor = (key: string): number => {
    const value = state.sensors[key];
    return typeof value === 'number' && Number.isFinite(value) ? value : Number.NaN;
  };
  const devices = Object.values(state.devices);
  const edgeOnline = devices.some((device) => device.online);
  return {
    device_id: Object.values(state.devices).find((device) => device.role === 'sensor_actuator')?.device_id
      ?? 'greenhouse_001_s3',
    timestamp: state.updated_at,
    sensors: {
      temperature: sensor('temperature_c'),
      humidity: sensor('humidity_pct'),
      pressure: sensor('pressure_kpa'),
      gas_resistance: sensor('gas_resistance_ohm'),
      light: sensor('illuminance_lux'),
      co2: sensor('co2_ppm'),
      soil_moisture: sensor('soil_moisture_pct'),
      soil_ec: sensor('soil_ec_ms_cm'),
    },
    status: {
      wifi: edgeOnline ? 'connected' : 'disconnected',
      mqtt: edgeOnline ? 'connected' : 'disconnected',
    },
  };
}

export function subscribeSiteEvents(
  onEvent: (eventType: string, data: unknown) => void,
  onDisconnected: () => void,
  onConnected: () => void,
  siteId = defaultSiteId,
): () => void {
  const source = new EventSource(`${apiBaseUrl}/api/v1/sites/${encodeURIComponent(siteId)}/events`);
  const eventNames = [
    'telemetry',
    'device_status',
    'capabilities',
    'command_update',
    'assistant_message',
    'assistant_action',
    'smart_control',
    'water_gun',
  ];
  for (const eventName of eventNames) {
    source.addEventListener(eventName, (event) => {
      try {
        onEvent(eventName, JSON.parse((event as MessageEvent<string>).data));
      } catch (error) {
        console.warn('Invalid site event payload.', { eventName, error });
      }
    });
  }
  source.onopen = onConnected;
  source.onerror = onDisconnected;
  return () => source.close();
}

export async function getSharedAssistantConversation(
  sessionId?: string,
  siteId = defaultSiteId,
): Promise<SharedAssistantConversation> {
  const query = sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : '';
  return requestJson<SharedAssistantConversation>(
    `/api/v1/sites/${encodeURIComponent(siteId)}/assistant/conversation${query}`,
  );
}

export async function sendSharedAssistantMessage(
  text: string,
  sessionId?: string,
  siteId = defaultSiteId,
): Promise<SharedAssistantMessage> {
  return requestJson<SharedAssistantMessage>(`/api/v1/sites/${encodeURIComponent(siteId)}/assistant/messages`, {
    method: 'POST',
    body: JSON.stringify({ text, session_id: sessionId || null, channel: 'web' }),
    timeoutMs: 120000,
  });
}

export async function decideSharedAssistantAction(
  actionId: string,
  decision: 'confirm' | 'cancel',
  siteId = defaultSiteId,
): Promise<SharedAssistantAction> {
  return requestJson<SharedAssistantAction>(
    `/api/v1/sites/${encodeURIComponent(siteId)}/assistant/actions/${encodeURIComponent(actionId)}/decision`,
    { method: 'POST', body: JSON.stringify({ decision }) },
  );
}

export async function createAssistantTurn(payload: AssistantTurnRequest): Promise<AssistantTurnAccepted> {
  return requestJson<AssistantTurnAccepted>('/api/v1/assistant/turns', {
    method: 'POST',
    body: JSON.stringify(payload),
    timeoutMs: 10000,
  });
}

export async function streamAssistantTurn(
  turnId: string,
  onProgress?: (text: string) => void,
): Promise<ExpertChatResponse> {
  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl}/api/v1/assistant/turns/${encodeURIComponent(turnId)}/events`, {
      headers: { Accept: 'text/event-stream' },
    });
  } catch (error) {
    throw new UserFacingError('无法连接智能助手，请检查后端服务。', error);
  }
  if (!response.ok || !response.body) {
    await throwServiceError(response, 'Assistant event stream');
  }

  const streamBody = response.body;
  if (!streamBody) throw new UserFacingError('智能助手事件流没有可读取内容。');
  const reader = streamBody.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let finalResponse: ExpertChatResponse | null = null;
  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done });
    const blocks = buffer.split(/\r?\n\r?\n/);
    buffer = blocks.pop() ?? '';
    for (const block of blocks) {
      if (!block || block.startsWith(':')) continue;
      let eventName = 'message';
      const dataLines: string[] = [];
      for (const line of block.split(/\r?\n/)) {
        if (line.startsWith('event:')) eventName = line.slice(6).trim();
        if (line.startsWith('data:')) dataLines.push(line.slice(5).trimStart());
      }
      if (!dataLines.length) continue;
      const data = JSON.parse(dataLines.join('\n')) as Record<string, unknown>;
      const event = { event: eventName, data } as AssistantTurnEvent;
      if (event.event === 'progress') onProgress?.(event.data.text);
      if (event.event === 'completed') finalResponse = event.data.response;
      if (event.event === 'failed') throw new UserFacingError(event.data.message || '智能助手暂时不可用。');
    }
    if (done) break;
  }
  if (!finalResponse) throw new UserFacingError('智能助手没有返回完整结果，请重试。');
  const actions = finalResponse.actions ?? finalResponse.message.suggested_actions ?? [];
  return {
    ...finalResponse,
    message: {
      ...finalResponse.message,
      content: sanitizeAssistantContent(finalResponse.message.content),
      suggested_actions: actions.map((action) => ({ ...action, status: action.status ?? 'pending' })),
    },
    actions,
  };
}

export async function getAssistantPreferences(siteId = defaultSiteId): Promise<AssistantPreferenceItem[]> {
  const result = await requestJson<{ site_id: string; items: AssistantPreferenceItem[] }>(
    `/api/v1/assistant/preferences?site_id=${encodeURIComponent(siteId)}`,
  );
  return result.items;
}

export async function deleteAssistantPreference(key: string, siteId = defaultSiteId): Promise<AssistantPreferenceItem[]> {
  const result = await requestJson<{ site_id: string; items: AssistantPreferenceItem[] }>(
    `/api/v1/assistant/preferences/${encodeURIComponent(key)}?site_id=${encodeURIComponent(siteId)}`,
    { method: 'DELETE' },
  );
  return result.items;
}

export async function getSiteHistory(hours = 6, siteId = defaultSiteId): Promise<HistoryPoint[]> {
  return requestJson<HistoryPoint[]>(
    `/api/v1/sites/${encodeURIComponent(siteId)}/history?hours=${Math.min(Math.max(Math.round(hours), 1), 24)}`,
  );
}

export async function analyzeFarm(
  latest: TelemetryPayload,
  context: FarmAnalysisContext = {},
): Promise<AiAnalysisResponse> {
  return requestJson<AiAnalysisResponse>('/api/ai/analyze', {
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
      retrieval_mode: context.retrievalMode ?? 'auto',
    }),
    timeoutMs: 120000,
  });
}

export async function getAlarmRecords(): Promise<AlarmRecord[]> {
  return requestJson<AlarmRecord[]>('/api/device/alarms');
}

export async function acknowledgeAlarm(alarmId: string): Promise<AlarmRecord> {
  return requestJson<AlarmRecord>(`/api/device/alarms/${encodeURIComponent(alarmId)}/ack`, {
    method: 'POST',
  });
}

export async function getDeviceHealth(siteId = defaultSiteId): Promise<DeviceHealth> {
  const state = await getSiteState(siteId);
  const device = Object.values(state.devices).find((item) => item.role === 'sensor_actuator');

  return {
    device_id: device?.device_id ?? 'greenhouse_001_s3',
    device_name: '一号大棚设备',
    online: device?.online ?? false,
    transport: 'mqtt',
    last_seen_at: device?.last_seen_at ?? 0,
    last_telemetry_at: state.updated_at,
    offline_after_seconds: 30,
  };
}

export async function getAlarmSettings(
  deviceId: string,
  fallbackRanges: Record<HistoryMetricKey, MetricTargetRange>,
): Promise<AlarmSettingsResponse> {
  return requestJson<AlarmSettingsResponse>(`/api/device/alarm-settings?device_id=${encodeURIComponent(deviceId)}`);
}

export async function saveAlarmSettings(
  deviceId: string,
  ranges: Record<HistoryMetricKey, MetricTargetRange>,
): Promise<AlarmSettingsResponse> {
  return requestJson<AlarmSettingsResponse>(`/api/device/alarm-settings?device_id=${encodeURIComponent(deviceId)}`, {
    method: 'PUT',
    body: JSON.stringify({ ranges }),
  });
}

export async function getCurrentWeather(city?: string): Promise<WeatherPayload> {
  const query = city ? `?city=${encodeURIComponent(city)}` : '';
  return requestJson<WeatherPayload>(`/api/weather/current${query}`);
}

export async function getWeatherBundle(city?: string): Promise<WeatherBundle> {
  const query = city ? `?city=${encodeURIComponent(city)}` : '';
  return requestJson<WeatherBundle>(`/api/weather/bundle${query}`);
}

type WeatherRegionSource = {
  name: string;
  direct: boolean;
  cities: string[];
};

const weatherRegionSources = chinaWeatherRegions as WeatherRegionSource[];

function weatherProvinceOption(region: WeatherRegionSource): WeatherCityOption {
  return {
    id: `province:${region.name}`,
    name: region.name,
    path: `${region.name},中国`,
    country: 'CN',
    level: 'province',
    province: region.name,
    direct: region.direct,
    cities: region.cities.map((city) => ({
      id: `city:${region.name}:${city}`,
      name: city,
      path: `${city},${region.name},中国`,
      country: 'CN',
      level: 'city',
      province: region.name,
      direct: false,
    })),
  };
}

const weatherRegionOptions = weatherRegionSources.map(weatherProvinceOption);

export function getWeatherRegions(): WeatherCityOption[] {
  return weatherRegionOptions;
}

export function getWeatherCitiesForProvince(province: string): WeatherCityOption[] {
  return weatherRegionOptions.find((item) => item.name === province)?.cities ?? [];
}

export async function getWeatherCities(query: string): Promise<WeatherCityOption[]> {
  const value = query.trim();
  if (!value) {
    return [];
  }
  const provinces = weatherRegionOptions.filter((item) => item.name?.includes(value));
  if (provinces.length > 0) {
    return provinces;
  }
  return weatherRegionOptions
    .flatMap((item) => item.cities ?? [])
    .filter((item) => item.name?.includes(value))
    .slice(0, 20);
}

export async function getPersistedDashboardState(): Promise<PersistedDashboardState | null> {
  const localState = readLocalDashboardState();
  try {
    const result = await requestJson<{ key: string; value: PersistedDashboardState }>('/api/v1/state/dashboard', {
      timeoutMs: 1500,
    });
    const backendState = result.value && typeof result.value === 'object' ? result.value : null;
    if (backendState && Object.keys(backendState).length > 0) {
      writeLocalDashboardState(backendState);
      return backendState;
    }
    return localState;
  } catch (error) {
    console.warn('Backend dashboard state unavailable; using the local fallback.', error);
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

export async function analyzeDiseaseImage(
  file: File,
  imageUrl: string,
  retrievalMode: RetrievalMode = 'force',
): Promise<DiseaseDetectionResult> {
  const formData = new FormData();
  formData.append('image', file);
  formData.append('retrieval_mode', retrievalMode);
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
  return analyzeDiseaseImage(file, imageUrl, 'auto');
}

export async function getCameraPositionConfig(): Promise<CameraPositionConfig | null> {
  try {
    const result = await requestJson<{ value: CameraPositionConfig }>('/api/v1/state/camera-position', { timeoutMs: 1200 });
    return result.value && typeof result.value === 'object' ? result.value : null;
  } catch (error) {
    console.warn('Camera position configuration unavailable.', error);
    return null;
  }
}

export async function saveCameraPositionConfig(value: CameraPositionConfig): Promise<void> {
  await requestJson('/api/v1/state/camera-position', {
    method: 'POST',
    body: JSON.stringify({ value }),
  });
}

export async function locateCameraObject(
  file: File,
  question: string,
  calibration: CameraPositionConfig,
): Promise<PositionLocateResult> {
  const formData = new FormData();
  formData.append('image', file);
  formData.append('question', question);
  formData.append('calibration', JSON.stringify(calibration));
  const response = await fetch(`${apiBaseUrl}/api/vision/locate`, { method: 'POST', body: formData });
  if (!response.ok) {
    await throwServiceError(response, 'Camera object location');
  }
  return response.json() as Promise<PositionLocateResult>;
}

export async function analyzeCurrentCropPositions(
  file: File,
  calibration: CameraPositionConfig,
): Promise<CurrentCropPositionsResult> {
  const formData = new FormData();
  formData.append('image', file);
  formData.append('calibration', JSON.stringify(calibration));
  const response = await fetch(`${apiBaseUrl}/api/vision/crops/current`, { method: 'POST', body: formData });
  if (!response.ok) {
    await throwServiceError(response, 'Current crop position analysis');
  }
  return response.json() as Promise<CurrentCropPositionsResult>;
}

export async function getCurrentCropPositions(): Promise<CurrentCropPositionsResult> {
  return requestJson<CurrentCropPositionsResult>('/api/vision/crops/current', { timeoutMs: 2000 });
}

export async function sendCameraPosition(resultId: string, deviceId: string): Promise<{ success: boolean; command_id: number; message: string }> {
  return requestJson<{ success: boolean; command_id: number; message: string }>('/api/vision/position/send', {
    method: 'POST',
    body: JSON.stringify({ result_id: resultId, device_id: deviceId }),
  });
}

export async function getWaterGunState(siteId = defaultSiteId): Promise<WaterGunState> {
  return requestJson<WaterGunState>(`/api/v1/sites/${encodeURIComponent(siteId)}/water-gun`);
}

export async function setWaterGunStaticTarget(
  target: WaterGunTargetInput,
  siteId = defaultSiteId,
): Promise<WaterGunState> {
  return requestJson<WaterGunState>(`/api/v1/sites/${encodeURIComponent(siteId)}/water-gun/static`, {
    method: 'POST',
    body: JSON.stringify(target),
  });
}

export async function previewWaterGunTarget(
  target: WaterGunTargetInput,
  siteId = defaultSiteId,
): Promise<WaterGunState> {
  return requestJson<WaterGunState>(`/api/v1/sites/${encodeURIComponent(siteId)}/water-gun/preview`, {
    method: 'POST',
    body: JSON.stringify(target),
  });
}

export async function startWaterGunDynamic(
  target: WaterGunTargetInput,
  siteId = defaultSiteId,
): Promise<WaterGunState> {
  return requestJson<WaterGunState>(`/api/v1/sites/${encodeURIComponent(siteId)}/water-gun/dynamic/start`, {
    method: 'POST',
    body: JSON.stringify(target),
  });
}

export async function updateWaterGunDynamicTarget(
  sessionId: string,
  target: Pick<WaterGunTargetInput, 'ground_range_mm' | 'bearing_deg'>,
  siteId = defaultSiteId,
): Promise<WaterGunState> {
  return requestJson<WaterGunState>(`/api/v1/sites/${encodeURIComponent(siteId)}/water-gun/dynamic/target`, {
    method: 'PUT',
    // MQTT sequence numbers are allocated by the backend so this request
    // cannot race the one-second heartbeat for the same sequence value.
    body: JSON.stringify({ session_id: sessionId, ...target }),
  });
}

export async function heartbeatWaterGunDynamic(sessionId: string, siteId = defaultSiteId): Promise<WaterGunState> {
  return requestJson<WaterGunState>(`/api/v1/sites/${encodeURIComponent(siteId)}/water-gun/dynamic/heartbeat`, {
    method: 'POST',
    body: JSON.stringify({ session_id: sessionId }),
  });
}

export async function setWaterGunDynamicSpray(
  sessionId: string,
  sprayEnabled: boolean,
  siteId = defaultSiteId,
): Promise<WaterGunState> {
  return requestJson<WaterGunState>(`/api/v1/sites/${encodeURIComponent(siteId)}/water-gun/dynamic/spray`, {
    method: 'POST',
    body: JSON.stringify({ session_id: sessionId, spray_enabled: sprayEnabled }),
  });
}

export async function stopWaterGunDynamic(
  sessionId: string,
  keepSpraying: boolean,
  siteId = defaultSiteId,
): Promise<WaterGunState> {
  return requestJson<WaterGunState>(`/api/v1/sites/${encodeURIComponent(siteId)}/water-gun/dynamic/stop`, {
    method: 'POST',
    body: JSON.stringify({ session_id: sessionId, keep_spraying: keepSpraying }),
  });
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
  const response = await requestJson<ExpertChatResponse>('/api/v1/assistant/chat', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
  const actions = response.actions ?? response.message.suggested_actions ?? [];
  return {
    ...response,
    message: {
      ...response.message,
      content: sanitizeAssistantContent(response.message.content),
      references: response.message.references ?? response.references ?? [],
      retrievalStatus: response.retrievalStatus ?? 'not_used',
      suggested_actions: actions.map((action) => ({ ...action, status: action.status ?? 'pending' })),
    },
    actions,
  };
}

function sanitizeAssistantContent(content: string): string {
  const text = String(content ?? '').trim();
  if (!text) return '我已收到问题，但暂时没有生成可靠回答。';

  const jsonCandidates: string[] = [text];
  for (const match of text.matchAll(/```(?:json)?\s*([\s\S]*?)```/gi)) {
    if (match[1]) jsonCandidates.push(match[1].trim());
  }
  const firstBrace = text.indexOf('{');
  const lastBrace = text.lastIndexOf('}');
  if (firstBrace >= 0 && lastBrace > firstBrace) {
    jsonCandidates.push(text.slice(firstBrace, lastBrace + 1));
  }
  for (const candidate of jsonCandidates) {
    try {
      const parsed = JSON.parse(candidate) as { answer?: unknown };
      if (parsed && typeof parsed === 'object' && typeof parsed.answer === 'string' && parsed.answer.trim()) {
        return parsed.answer.trim().slice(0, 1600);
      }
    } catch {
      // Continue with the user-visible prose cleanup below.
    }
  }

  let cleaned = text.replace(/```(?:json)?\s*[\s\S]*?```/gi, '').trim();
  const internalJsonStart = cleaned.search(/\n\s*\{\s*["']?(?:answer|actions|referenceIds)["']?\s*:/i);
  if (internalJsonStart >= 0) cleaned = cleaned.slice(0, internalJsonStart).trim();
  if (!cleaned || /^[\[{]/.test(cleaned)) {
    return '我已收到问题，但暂时没有生成可靠回答，请换一种说法后重试。';
  }
  return cleaned.slice(0, 1600);
}

export async function getAgriSources(): Promise<AgriSourceInfo[]> {
  const result = await requestJson<{ items: AgriSourceInfo[] }>('/api/v1/agri/sources', { timeoutMs: 8000 });
  return result.items;
}

export async function updateAgriSource(sourceId: AgriSourceInfo['sourceId'], enabled: boolean): Promise<AgriSourceInfo> {
  return requestJson<AgriSourceInfo>(`/api/v1/agri/sources/${encodeURIComponent(sourceId)}`, {
    method: 'PATCH',
    body: JSON.stringify({ enabled }),
  });
}

export async function testAgriSource(sourceId: AgriSourceInfo['sourceId']): Promise<{ source: AgriSourceInfo; sampleCount: number }> {
  return requestJson<{ source: AgriSourceInfo; sampleCount: number }>(`/api/v1/agri/sources/${encodeURIComponent(sourceId)}/test`, {
    method: 'POST',
    timeoutMs: 15000,
  });
}

export async function getKnowledgeBases(): Promise<KnowledgeBaseInfo[]> {
  const result = await requestJson<{ items: KnowledgeBaseInfo[] }>('/api/v1/kb/list', { timeoutMs: 2500 });
  return result.items;
}

export async function getKnowledgeItems(kbId: number): Promise<KnowledgeItemInfo[]> {
  const result = await requestJson<{ items: KnowledgeItemInfo[] }>(`/api/v1/kb/items?kbId=${encodeURIComponent(kbId)}`, { timeoutMs: 2500 });
  return result.items;
}

export async function createKnowledgeBase(name: string, description: string): Promise<KnowledgeBaseInfo> {
  return requestJson<KnowledgeBaseInfo>('/api/v1/kb/create', {
    method: 'POST',
    body: JSON.stringify({ name, description }),
  });
}

export async function updateKnowledgeBase(kbId: number, name: string, description: string): Promise<KnowledgeBaseInfo> {
  return requestJson<KnowledgeBaseInfo>('/api/v1/kb/update', {
    method: 'POST',
    body: JSON.stringify({ kbId, name, description }),
  });
}

export async function deleteKnowledgeBase(kbId: number): Promise<void> {
  await requestJson<{ success: boolean }>('/api/v1/kb/delete', {
    method: 'POST',
    body: JSON.stringify({ kbId }),
  });
}

export async function addKnowledgeItem(kbId: number, title: string, content: string): Promise<KnowledgeTextAddResult> {
  return requestJson<KnowledgeTextAddResult>('/api/v1/kb/add_text', {
    method: 'POST',
    body: JSON.stringify({ kbId, title, content }),
  });
}

export async function updateKnowledgeItem(kbId: number, itemId: number, title: string, content: string): Promise<KnowledgeTextAddResult> {
  return requestJson<KnowledgeTextAddResult>('/api/v1/kb/item/update', {
    method: 'POST',
    body: JSON.stringify({ kbId, itemId, title, content }),
  });
}

export async function deleteKnowledgeItem(kbId: number, itemId: number): Promise<void> {
  await requestJson<{ success: boolean }>('/api/v1/kb/item/delete', {
    method: 'POST',
    body: JSON.stringify({ kbId, itemId }),
  });
}

export async function analyzeKnowledge(kbId: number, fieldId: string, question: string): Promise<KnowledgeAnalyzeResult> {
  return requestJson<KnowledgeAnalyzeResult>('/api/v1/kb/analyze', {
    method: 'POST',
    body: JSON.stringify({ kbId, fieldId, question }),
  });
}
