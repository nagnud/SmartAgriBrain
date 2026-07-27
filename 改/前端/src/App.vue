<script setup lang="ts">
import type { Component } from 'vue';
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import type { EChartsOption } from 'echarts';
import {
  Activity,
  AlertTriangle,
  ArrowDown,
  BarChart3,
  Bell,
  Bot,
  ClipboardPaste,
  CloudSun,
  Cpu,
  Database,
  Droplets,
  Fan,
  Gauge,
  History,
  Home,
  Image,
  ImageOff,
  Leaf,
  Lightbulb,
  Mic,
  Pencil,
  Plus,
  Pin,
  RefreshCw,
  Save,
  Send,
  ShieldCheck,
  SlidersHorizontal,
  Sun,
  Thermometer,
  ToggleLeft,
  Trash2,
  Upload,
  Wind,
  X,
} from '@lucide/vue';
import CameraGrowthPanel from './components/CameraGrowthPanel.vue';
import EChartPanel from './components/EChartPanel.vue';
import MarkdownContent from './components/MarkdownContent.vue';
import StatusPill from './components/StatusPill.vue';
import {
  addKnowledgeItem,
  acknowledgeAlarm,
  analyzeDiseaseImage,
  analyzeFarm,
  analyzeKnowledge,
  createKnowledgeBase,
  createAssistantTurn,
  defaultSiteId,
  decideSharedAssistantAction,
  deleteAssistantPreference,
  deleteDiseasePhoto,
  deleteKnowledgeBase,
  deleteKnowledgeItem,
  getAlarmRecords,
  getAlarmSettings,
  getAssistantPreferences,
  getAgriSources,
  getDiseasePhotos,
  getDeviceHealth,
  getCameraPositionConfig,
  getBackendCameraConfig,
  getCurrentWeather,
  getCurrentCropPositions,
  getWeatherBundle,
  getWeatherCities,
  getWeatherCitiesForProvince,
  getWeatherRegions,
  getWaterGunState,
  heartbeatWaterGunDynamic,
  getKnowledgeBases,
  getKnowledgeItems,
  getLatestTelemetry,
  getPersistedDashboardState,
  getSharedAssistantConversation,
  getSiteHistory,
  getSiteState,
  savePersistedDashboardState,
  saveAlarmSettings,
  saveCameraPositionConfig,
  saveBackendCameraConfig,
  saveDiseasePhotoAnalysis,
  sendExpertChatMessage,
  sendSharedAssistantMessage,
  setWaterGunDynamicSpray,
  setWaterGunStaticTarget,
  siteStateToTelemetry,
  subscribeSiteEvents,
  streamAssistantTurn,
  startWaterGunDynamic,
  stopWaterGunDynamic,
  testAgriSource,
  locateCameraObject,
  resolveApiAssetUrl,
  updateAgriSource,
  updateKnowledgeBase,
  updateKnowledgeItem,
  updateWaterGunDynamicTarget,
  uploadDiseasePhoto,
} from './services/api';
import type {
  AiAnalysisResponse,
  AgriSourceInfo,
  AlarmRecord,
  CropPositionInfo,
  CurrentCropPositionsResult,
  DeviceHealth,
  AssistantAction,
  AssistantThread,
  AssistantPreferenceItem,
  ChatMessage,
  CameraPositionConfig,
  BackendCameraConfig,
  DiseaseDetectionResult,
  DiseasePhotoInfo,
  PositionLocateResult,
  HistoryPoint,
  HistoryMetricKey,
  KnowledgeAnalyzeResult,
  KnowledgeBaseInfo,
  KnowledgeItemInfo,
  KnowledgeReference,
  MetricTargetRange,
  PersistedDashboardState,
  SharedAssistantAction,
  SharedAssistantConversation,
  SiteState,
  StatusLevel,
  RetrievalMode,
  RetrievalStatus,
  TelemetryPayload,
  WeatherPayload,
  WeatherBundle,
  WeatherCityOption,
  WeatherDailyItem,
  WeatherAlarmItem,
  WaterGunState,
  WaterGunSpraySchedule,
  WaterGunTargetSource,
} from './types';
import {
  confidenceText,
  formatDateTime,
  formatTime,
  numberText,
  UserFacingError,
  userErrorText,
} from './utils/format';

type ViewKey = 'overview' | 'realtime' | 'history' | 'disease' | 'ai' | 'control' | 'knowledge' | 'alarms';

interface NavItem {
  key: ViewKey;
  label: string;
  icon: Component;
}

interface DiseasePhotoGroup {
  dateKey: string;
  dateLabel: string;
  photos: DiseasePhotoInfo[];
}

interface MetricCardVm {
  key: HistoryMetricKey;
  title: string;
  value: string;
  unit: string;
  hint: string;
  state: 'good' | 'watch' | 'danger' | 'low';
  icon: Component;
  color: string;
  currentValue: number;
  statusLabel: string;
  targetText: string;
  trendText: string;
  aiInsight: string;
}

interface SpeechRecognitionEventLike {
  results: {
    length: number;
    [index: number]: {
      isFinal: boolean;
      [index: number]: {
        transcript: string;
      };
    };
  };
}

interface SpeechRecognitionLike {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  maxAlternatives: number;
  start: () => void;
  stop: () => void;
  abort: () => void;
  onstart: (() => void) | null;
  onspeechstart: (() => void) | null;
  onspeechend: (() => void) | null;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onerror: (() => void) | null;
  onend: (() => void) | null;
}

type SpeechRecognitionConstructor = new () => SpeechRecognitionLike;

interface HistoryMetricDefinition {
  key: HistoryMetricKey;
  name: string;
  unit: string;
  color: string;
  value: (point: HistoryPoint) => number | null;
}

interface AiRiskFactor {
  key: string;
  label: string;
  detail: string;
  state: StatusLevel;
}

interface MetricEditorRect {
  left: number;
  top: number;
  width: number;
  height: number;
}

interface MetricEditorSourceRect extends MetricEditorRect {
  documentLeft: number;
  documentTop: number;
}

interface PositionCaptureLoadState {
  attempts: number;
  retryToken: number;
  verifying: boolean;
  expired: boolean;
}

const historyMetricDefinitions: HistoryMetricDefinition[] = [
  { key: 'temperature', name: '温度', unit: '摄氏度', color: '#D68C1F', value: (point) => point.temperature },
  { key: 'light', name: '光照', unit: 'lux', color: '#E6B325', value: (point) => point.light },
  { key: 'co2', name: '二氧化碳', unit: 'ppm', color: '#7A5CFA', value: (point) => point.co2 },
  { key: 'soil_moisture', name: '土壤湿度', unit: '%', color: '#2F8F4E', value: (point) => point.soil_moisture },
];

const historySampleIntervalMs = 10_000;
const historyWindowMinDurationMs = 5 * 60 * 1000;
const historyWindowMaxDurationMs = 12 * 60 * 60 * 1000;
const historyWindowDefaultDurationMs = 6 * 60 * 60 * 1000;
const historyChartPointCount = 30;

const navItems: NavItem[] = [
  { key: 'overview', label: '首页总览', icon: Home },
  { key: 'control', label: '设备控制', icon: ToggleLeft },
  { key: 'realtime', label: '实时监测', icon: Activity },
  { key: 'history', label: '历史曲线', icon: BarChart3 },
  { key: 'disease', label: '病害识别', icon: Image },
  { key: 'ai', label: 'AI 农事建议', icon: Bot },
  { key: 'knowledge', label: '知识库管理', icon: Database },
  { key: 'alarms', label: '报警记录', icon: Bell },
];

function isViewKey(value: unknown): value is ViewKey {
  return typeof value === 'string' && navItems.some((item) => item.key === value);
}

const activeView = ref<ViewKey>('overview');
const latest = ref<TelemetryPayload | null>(null);
const currentWeather = ref<WeatherPayload | null>(null);
const weatherBundle = ref<WeatherBundle | null>(null);
const weatherCity = ref('无锡');
const weatherCityDraft = ref('无锡');
const weatherCityOptions = ref<WeatherCityOption[]>([]);
const weatherCityDropdownOpen = ref(false);
const weatherPickerMode = ref<'provinces' | 'cities' | 'search'>('search');
const weatherSelectedProvince = ref('');
const weatherPanelOpen = ref(false);
const weatherLoading = ref(false);
const weatherError = ref('');
const historyPoints = ref<HistoryPoint[]>([]);
const historyWindowEnd = ref(Math.floor(Date.now() / historySampleIntervalMs) * historySampleIntervalMs);
const historyWindowDurationMs = ref(historyWindowDefaultDurationMs);
const historyWindowSliderValue = ref(historySliderValueForDuration(historyWindowDefaultDurationMs));
const aiAnalysis = ref<AiAnalysisResponse | null>(null);
const aiAnalysisLoading = ref(false);
const aiAnalysisCompletedAt = ref<number | null>(null);
const pageVisible = ref(typeof document === 'undefined' || document.visibilityState === 'visible');
const alarms = ref<AlarmRecord[]>([]);
const deviceHealth = ref<DeviceHealth | null>(null);
const alarmActionMessage = ref('');
const acknowledgingAlarmId = ref('');
const alarmSettingsSyncPending = ref(false);
const siteState = ref<SiteState | null>(null);
const siteEventsConnected = ref(false);
const sharedAssistantConversation = ref<SharedAssistantConversation>({ session_id: '', messages: [] });
const sharedAssistantInput = ref('');
const sharedAssistantBusy = ref(false);
const sharedAssistantActionBusy = ref('');
const diseaseResult = ref<DiseaseDetectionResult | null>(null);
const diseaseImageUrl = ref('');
const diseaseImageLoadError = ref(false);
const diseaseLoading = ref(false);
const diseaseUploadError = ref('');
const diseaseDragActive = ref(false);
const diseasePhotoLibraryOpen = ref(false);
const diseasePhotos = ref<DiseasePhotoInfo[]>([]);
const selectedDiseasePhoto = ref<DiseasePhotoInfo | null>(null);
const selectedDiseasePhotoImageError = ref(false);
const currentDiseasePhotoId = ref<number | null>(null);
const cameraGrowthPanelRef = ref<{
  captureAndAnalyze: () => Promise<void>;
  captureCurrentFrame: () => Promise<File | null>;
} | null>(null);
const cameraAnalysisResult = ref<DiseaseDetectionResult | null>(null);
const currentCropPositions = ref<CurrentCropPositionsResult | null>(null);
const defaultCameraPositionConfig: CameraPositionConfig = {
  image_width: 1280,
  image_height: 720,
  fx: 1315.5,
  fy: 1478.1,
  cx: 605.7,
  cy: 332.9,
  distortion: [0, 0, 0, 0, 0],
  camera_height_mm: 150,
  pitch_down_deg: 15,
  yaw_deg: -2.02,
  roll_deg: 0.74,
};
const cameraPositionConfig = ref<CameraPositionConfig>({ ...defaultCameraPositionConfig });
const backendCameraConfig = ref<BackendCameraConfig>({ device_index: 0, width: 1280, height: 720, fps: 15 });
const cameraDistortionText = ref('');
const cameraPositionConfigSaving = ref(false);
const cameraPositionConfigMessage = ref('请先填写棋盘格标定得到的 fx、fy、cx、cy。');
let savedCameraPositionConfigSnapshot: CameraPositionConfig = {
  ...defaultCameraPositionConfig,
  distortion: [...defaultCameraPositionConfig.distortion],
};
let savedBackendCameraConfigSnapshot: BackendCameraConfig = { ...backendCameraConfig.value };
const positionSelectionSession = ref<PositionLocateResult | null>(null);
const positionImageModal = ref<{ result: PositionLocateResult; title: string; capturedAt: number } | null>(null);
const positionCaptureStates = ref<Record<string, PositionCaptureLoadState>>({});
const waterGunFieldRef = ref<SVGSVGElement | null>(null);
const waterGunState = ref<WaterGunState | null>(null);
const waterGunRangeMm = ref(600);
const waterGunBearingDeg = ref(0);
const waterGunTargetSource = ref<WaterGunTargetSource>('manual');
const waterGunTargetLabel = ref('');
const waterGunBusy = ref(false);
const waterGunMessage = ref('等待设置水枪目标。');
const waterGunStaticConfirmOpen = ref(false);
const waterGunDynamicConfirmOpen = ref(false);
const waterGunPointerActive = ref(false);
const waterGunPendingDynamicTarget = ref<{ range: number; bearing: number } | null>(null);
const waterGunSpraySchedule = ref<WaterGunSpraySchedule | null>('continuous');
const waterGunDurationHours = ref(0);
const waterGunDurationMinutes = ref(0);
const waterGunDurationSeconds = ref(0);
const waterGunCountdownNow = ref(Date.now());
let waterGunDynamicSendTimer: number | undefined;
let waterGunHeartbeatTimer: number | undefined;
let waterGunCountdownTimer: number | undefined;
let waterGunDynamicTargetSending = false;
const diseasePhotoLoading = ref(false);
const diseasePhotoDeletingId = ref<number | null>(null);
const diseasePhotoError = ref('');
const chatMessages = ref<ChatMessage[]>([]);
const assistantThreads = ref<AssistantThread[]>([]);
const activeAssistantThreadId = ref('');
const assistantHistoryOpen = ref(false);
const assistantPreferencesOpen = ref(false);
const assistantPreferences = ref<AssistantPreferenceItem[]>([]);
const assistantPreferencesLoading = ref(false);
const renamingAssistantThreadId = ref('');
const assistantThreadNameDraft = ref('');
const chatInput = ref('番茄叶片有黄斑，结合当前环境应该怎么处理？');
const chatInputRef = ref<HTMLTextAreaElement | null>(null);
const chatImageUrl = ref('');
const chatImageFileName = ref('');
const chatImageFile = ref<File | null>(null);
const chatImageError = ref('');
const chatDragActive = ref(false);
const chatSendingStage = ref<'idle' | 'vision' | 'chat'>('idle');
const chatSending = ref(false);
const assistantOpen = ref(false);
const defaultAssistantWidth = 460;
const minAssistantWidth = 360;
const minWorkspaceWidth = 640;
const maxAssistantViewportRatio = 0.55;
const assistantWidth = ref(defaultAssistantWidth);
const assistantResizing = ref(false);
const assistantMessagesRef = ref<HTMLElement | null>(null);
const assistantAtBottom = ref(true);
const assistantShowScrollButton = ref(false);
const assistantExecutingActionId = ref<string | null>(null);
const voiceMessage = ref('语音输入可用时会自动转成文字');
const listening = ref(false);
const knowledgeBases = ref<KnowledgeBaseInfo[]>([]);
const knowledgeItems = ref<KnowledgeItemInfo[]>([]);
const selectedKbId = ref(0);
const kbNameDraft = ref('番茄结果期管理');
const kbDescriptionDraft = ref('结果期水肥、光照、病害管理经验');
const itemTitleDraft = ref('番茄高湿病害风险');
const itemContentDraft = ref('番茄在高湿、通风不足时容易出现叶斑病和霜霉病，应先通风降湿并减少叶面结露。');
const editingKbId = ref(0);
const editingItemId = ref(0);
const knowledgeBaseDialogOpen = ref(false);
const knowledgeItemDialogOpen = ref(false);
const knowledgeQuestion = ref('结合当前农情，给出水泵、补光灯、风机和卷帘的管理建议。');
const knowledgeAnswer = ref<KnowledgeAnalyzeResult | null>(null);
const knowledgeLoading = ref(false);
const knowledgeError = ref('');
const agriSources = ref<AgriSourceInfo[]>([]);
const agriSourcesLoading = ref(false);
const agriSourceBusyId = ref<AgriSourceInfo['sourceId'] | null>(null);
const agriSourceError = ref('');
const selectedHistoryMetricKeys = ref<HistoryMetricKey[]>(historyMetricDefinitions.map((item) => item.key));
const metricTargetRanges = ref<Record<HistoryMetricKey, MetricTargetRange>>({
  temperature: { min: 24, max: 30 },
  humidity: { min: 55, max: 72 },
  light: { min: 14000, max: 24000 },
  co2: { min: 520, max: 900 },
  soil_moisture: { min: 48, max: 66 },
  soil_ec: { min: 1.2, max: 2.6 },
  gas_resistance: { min: 12000, max: 22000 },
});
const selectedMetricKey = ref<HistoryMetricKey | null>(null);
const metricEditorTransition = ref<'opening' | 'closing' | 'switch-next' | 'switch-prev' | ''>('');
const metricEditorChartActive = ref(false);
const targetMinDraft = ref('');
const targetMaxDraft = ref('');
const targetRangeError = ref('');
const targetRangeSavedMessage = ref('');
const targetRangeSaving = ref(false);
let targetRangeSavedTimer: number | undefined;
const metricEditorStageRef = ref<HTMLElement | null>(null);
const metricEditorStyle = ref<Record<string, string>>({
  '--metric-editor-left': '0px',
  '--metric-editor-top': '0px',
  '--metric-editor-width': '100vw',
  '--metric-editor-height': '100vh',
  '--metric-editor-motion-x': '0px',
  '--metric-editor-motion-y': '0px',
  '--metric-editor-scale-x': '1',
  '--metric-editor-scale-y': '1',
});
const loading = ref(true);
const refreshing = ref(false);
let refreshTimer: number | undefined;
let historyCalibrationTimer: number | undefined;
let closeSiteEvents: (() => void) | undefined;
let aiAnalysisTimer: number | undefined;
let aiAnalysisRequest: Promise<void> | null = null;
let metricEditorTimer: number | undefined;
let metricEditorChartTimer: number | undefined;
let activeBrowserSpeechRecognition: SpeechRecognitionLike | null = null;
let assistantThinkingTimer: number | undefined;
let assistantTypeRunId = 0;
let assistantResizeFrame = 0;
let pendingAssistantResizeClientX = 0;
let voiceInputPrefix = '';
let voiceInputSuffix = '';
let voiceCurrentTranscript = '';
let voiceRecognitionHadError = false;
let applyingVoiceTranscriptFocus = false;
let voiceSilenceStopTimer: number | undefined;
let voiceSpeechActive = false;
let metricEditorLastSourceRect: MetricEditorSourceRect | null = null;
const metricEditorSourceRects = new Map<HistoryMetricKey, MetricEditorSourceRect>();
let persistentStateReady = false;
let applyingPersistentState = false;
let persistentStateSaveTimer: number | undefined;
let weatherCitySearchTimer: number | undefined;
const aiAnalysisIntervalMs = 120000;
const maxUploadImageBytes = 10 * 1024 * 1024;
const voiceSilenceStopDelayMs = 3_000;
const allowedUploadImageTypes = new Set(['image/jpeg', 'image/png', 'image/webp']);
const sentChatImageUrls = new Set<string>();
let diseaseDragDepth = 0;
let chatDragDepth = 0;

const metricTargetInputSteps: Record<HistoryMetricKey, number> = {
  temperature: 0.01,
  humidity: 0.1,
  light: 10,
  co2: 1,
  soil_moisture: 0.1,
  soil_ec: 0.01,
  gas_resistance: 10,
};

const selectedKnowledgeBase = computed(() => knowledgeBases.value.find((item) => item.kbId === selectedKbId.value) ?? null);
const activeAlarms = computed(() => alarms.value.filter((item) => item.state === 'open').length);
const diseasePhotoGroups = computed<DiseasePhotoGroup[]>(() => {
  const groupMap = new Map<string, DiseasePhotoGroup>();
  for (const photo of diseasePhotos.value) {
    const dateKey = diseasePhotoDateKey(photo.createdAt);
    const existing = groupMap.get(dateKey);
    if (existing) {
      existing.photos.push(photo);
      continue;
    }
    groupMap.set(dateKey, {
      dateKey,
      dateLabel: diseasePhotoDateLabel(dateKey),
      photos: [photo],
    });
  }
  return [...groupMap.values()];
});
const diseaseDetectionBoxes = computed(() => (
  diseaseResult.value?.detections.filter((item) => item.bbox.width > 0 && item.bbox.height > 0) ?? []
));
const selectedDiseasePhotoAnalysis = computed(() => diseasePhotoAnalysis(selectedDiseasePhoto.value));
const weatherCurrentDetail = computed(() => (
  weatherBundle.value?.current.available ? weatherBundle.value.current.data ?? null : null
));
const weatherDailyItems = computed<WeatherDailyItem[]>(() => (
  weatherBundle.value?.daily.available && Array.isArray(weatherBundle.value.daily.data)
    ? weatherBundle.value.daily.data
    : []
));
const weatherTodayDetail = computed(() => {
  const today = weatherDailyItems.value[0];
  const current = weatherCurrentDetail.value ?? currentWeather.value;
  const condition = today ? weatherConditionText(today) : current?.condition || '天气暂无';
  const temperature = today
    ? `${weatherValueText(today.low, '°')} - ${weatherValueText(today.high, '°')}`
    : `当前 ${weatherValueText(current?.temperature, ' 摄氏度')}`;
  const rainfall = today ? weatherRainText(today) : '降雨暂无';
  const humidityValue = today?.humidity ?? current?.humidity;
  const humidity = typeof humidityValue === 'number'
    ? `湿度 ${weatherValueText(humidityValue, '%')}${today?.humidity == null ? '（实时）' : ''}`
    : '湿度暂无';
  const windDirection = today?.wind_direction || current?.wind_direction || '风向暂无';
  const windLevel = today?.wind_scale != null
    ? `${today.wind_scale}级`
    : current?.wind_level || '风力暂无';
  return { condition, temperature, rainfall, humidity, wind: `${windDirection} ${windLevel}` };
});
const weatherAlarmItems = computed<WeatherAlarmItem[]>(() => (
  weatherBundle.value?.alarms.available && Array.isArray(weatherBundle.value.alarms.data)
    ? weatherBundle.value.alarms.data
    : []
));
const weatherSearchOptions = computed<WeatherCityOption[]>(() => {
  if (weatherPickerMode.value === 'provinces') {
    return getWeatherRegions();
  }
  if (weatherPickerMode.value === 'cities') {
    return getWeatherCitiesForProvince(weatherSelectedProvince.value);
  }
  return weatherCityOptions.value;
});
const weatherDisplayLocation = computed(() => weatherLocationLabel(currentWeather.value?.location || weatherCity.value));
const weatherPanelTitle = computed(() => `${weatherDisplayLocation.value} 天气`);
const weatherImpactTips = computed(() => buildWeatherImpactTips());
const deviceDisplayName = computed(() => deviceHealth.value?.device_name || '一号大棚设备');
const deviceOnlineLabel = computed(() => deviceHealth.value?.online === false ? '设备离线' : '设备在线');
const deviceOnlineState = computed<StatusLevel>(() => deviceHealth.value?.online === false ? 'danger' : 'good');

const waterGunDynamicActive = computed(() => waterGunState.value?.mode === 'dynamic');
const waterGunSpraying = computed(() => Boolean(waterGunState.value?.spray_enabled));
const waterGunStaticDraftDirty = computed(() => {
  const state = waterGunState.value;
  if (!state || state.mode !== 'static') return false;
  return Math.abs(waterGunRangeMm.value - state.ground_range_mm) >= 0.05
    || Math.abs(waterGunBearingDeg.value - state.bearing_deg) >= 0.05
    || waterGunTargetSource.value !== state.source
    || waterGunTargetLabel.value !== state.target_label;
});
const waterGunManualForwardMaxMm = 1200;
const waterGunManualHalfWidthMm = 1200;
const waterGunMinRangeMm = 300;
const waterGunMaxRangeMm = 1200;
const waterGunFullScaleRangeMm = 1700;
const waterGunMappedPumpPercent = computed(() => (
  Math.min(100, Math.max(0, (waterGunState.value?.ground_range_mm ?? waterGunRangeMm.value) / waterGunFullScaleRangeMm * 100))
));
const waterGunPumpPercent = computed(() => (
  waterGunSpraying.value ? waterGunMappedPumpPercent.value : 0
));
const waterGunTargetCartesian = computed(() => {
  const radians = waterGunBearingDeg.value * Math.PI / 180;
  return {
    right: waterGunRangeMm.value * Math.sin(radians),
    forward: waterGunRangeMm.value * Math.cos(radians),
  };
});
const waterGunTargetOutside = computed(() => {
  const { right, forward } = waterGunTargetCartesian.value;
  return waterGunRangeMm.value < waterGunMinRangeMm
    || waterGunRangeMm.value > waterGunMaxRangeMm
    || forward < 0
    || forward > waterGunManualForwardMaxMm
    || Math.abs(right) > waterGunManualHalfWidthMm;
});
const waterGunMarker = computed(() => {
  const { right, forward } = waterGunTargetCartesian.value;
  let displayRight = right;
  let displayForward = forward;
  if (waterGunTargetOutside.value) {
    const scales = [1];
    if (Math.abs(right) > waterGunManualHalfWidthMm) scales.push(waterGunManualHalfWidthMm / Math.abs(right));
    if (forward > waterGunManualForwardMaxMm) scales.push(waterGunManualForwardMaxMm / forward);
    if (forward < 0) scales.push(0);
    const scale = Math.min(...scales);
    displayRight *= scale;
    displayForward = Math.max(0, displayForward * scale);
  }
  return {
    x: 400 + (displayRight / waterGunManualHalfWidthMm) * 370,
    y: 385 - (displayForward / waterGunManualForwardMaxMm) * 370,
  };
});
function waterGunSvgPointForTarget(groundRangeMm: number | null | undefined, bearingDeg: number | null | undefined): { x: number; y: number } | null {
  if (typeof groundRangeMm !== 'number' || typeof bearingDeg !== 'number' || !Number.isFinite(groundRangeMm) || !Number.isFinite(bearingDeg)) {
    return null;
  }
  const radians = bearingDeg * Math.PI / 180;
  const right = groundRangeMm * Math.sin(radians);
  const forward = groundRangeMm * Math.cos(radians);
  if (forward < 0 || forward > waterGunManualForwardMaxMm || Math.abs(right) > waterGunManualHalfWidthMm) {
    return null;
  }
  return {
    x: 400 + (right / waterGunManualHalfWidthMm) * 370,
    y: 385 - (forward / waterGunManualForwardMaxMm) * 370,
  };
}
const waterGunCropMarkers = computed(() => (
  currentCropPositions.value?.crops
    .filter((crop) => crop.coordinate_status === 'located')
    .map((crop) => ({ crop, point: waterGunSvgPointForTarget(crop.ground_range_mm, crop.bearing_deg) }))
    .filter((item): item is { crop: CropPositionInfo; point: { x: number; y: number } } => item.point !== null)
    ?? []
));
const waterGunBearingText = computed(() => {
  const bearing = waterGunBearingDeg.value;
  if (Math.abs(bearing) < 0.05) return '正前方 0.0°';
  return `${bearing < 0 ? '左' : '右'} ${Math.abs(bearing).toFixed(1)}°`;
});
const waterGunActualBearingDeg = computed(() => (
  waterGunStaticDraftDirty.value ? (waterGunState.value?.bearing_deg ?? waterGunBearingDeg.value) : waterGunBearingDeg.value
));
const waterGunTimedDurationError = computed(() => {
  if (waterGunSpraySchedule.value !== 'timed') return '';
  const values = [waterGunDurationHours.value, waterGunDurationMinutes.value, waterGunDurationSeconds.value];
  if (values.some((value) => !Number.isInteger(value))) return '时间必须为整数。';
  if (waterGunDurationHours.value < 0 || waterGunDurationHours.value > 23) return '小时必须在 0–23 之间。';
  if (waterGunDurationMinutes.value < 0 || waterGunDurationMinutes.value > 59) return '分钟必须在 0–59 之间。';
  if (waterGunDurationSeconds.value < 0 || waterGunDurationSeconds.value > 59) return '秒必须在 0–59 之间。';
  if (waterGunDurationHours.value + waterGunDurationMinutes.value + waterGunDurationSeconds.value === 0) {
    return '请设置至少 1 秒的喷射时间。';
  }
  return '';
});
const waterGunDurationTotalSeconds = computed(() => (
  waterGunDurationHours.value * 3600 + waterGunDurationMinutes.value * 60 + waterGunDurationSeconds.value
));
const waterGunRemainingSeconds = computed(() => {
  const endsAt = waterGunState.value?.spray_ends_at;
  if (!waterGunSpraying.value || !endsAt) return 0;
  return Math.max(0, Math.ceil((endsAt - waterGunCountdownNow.value) / 1000));
});
const waterGunCountdownLabel = computed(() => {
  if (waterGunSpraying.value && waterGunState.value?.spray_schedule === 'timed') {
    return `剩余 ${formatWaterGunDuration(waterGunRemainingSeconds.value)}`;
  }
  if (waterGunState.value?.stop_reason === 'timed_complete') return '已停止喷水';
  return waterGunSpraying.value ? '正在持续喷水' : '待机';
});
const waterGunSprayActionDisabled = computed(() => (
  waterGunBusy.value
  || (!waterGunDynamicActive.value && !waterGunSpraying.value && (
    waterGunSpraySchedule.value === null
    || Boolean(waterGunTimedDurationError.value)
  ))
));

function formatWaterGunDuration(totalSeconds: number): string {
  const safeSeconds = Math.max(0, Math.floor(totalSeconds));
  const hours = Math.floor(safeSeconds / 3600);
  const minutes = Math.floor((safeSeconds % 3600) / 60);
  const seconds = safeSeconds % 60;
  return [hours, minutes, seconds].map((value) => String(value).padStart(2, '0')).join(':');
}

function selectWaterGunSpraySchedule(schedule: WaterGunSpraySchedule): void {
  waterGunSpraySchedule.value = schedule;
  if (schedule === 'timed' && waterGunDurationTotalSeconds.value === 0) waterGunDurationMinutes.value = 1;
}

function setWaterGunDurationFields(totalSeconds: number | null): void {
  const safeSeconds = Math.max(0, Math.min(86_399, Math.floor(totalSeconds ?? 0)));
  waterGunDurationHours.value = Math.floor(safeSeconds / 3600);
  waterGunDurationMinutes.value = Math.floor((safeSeconds % 3600) / 60);
  waterGunDurationSeconds.value = safeSeconds % 60;
}

function waterGunTargetPayload() {
  return {
    ground_range_mm: Math.round(waterGunRangeMm.value * 10) / 10,
    bearing_deg: Math.round(waterGunBearingDeg.value * 10) / 10,
    device_id: 'greenhouse_001_s3',
    source: waterGunTargetSource.value,
    target_label: waterGunTargetLabel.value,
  };
}

function waterGunConfirmedTargetPayload() {
  const state = waterGunState.value;
  if (!state) return waterGunTargetPayload();
  return {
    ground_range_mm: state.ground_range_mm,
    bearing_deg: state.bearing_deg,
    device_id: state.device_id,
    source: state.source,
    target_label: state.target_label,
  };
}

function hasLocalDynamicTarget(): boolean {
  return waterGunPointerActive.value
    || waterGunPendingDynamicTarget.value !== null
    || waterGunDynamicTargetSending;
}

function syncWaterGunState(state: WaterGunState, forceTarget = false, preserveTarget = false): void {
  const previousState = waterGunState.value;
  const hadStaticDraft = waterGunStaticDraftDirty.value;
  waterGunState.value = state;
  // Heartbeat and SSE responses describe the last backend target. While the
  // user is selecting or sending a newer dynamic target, keep the local draft
  // so an older response cannot move the marker back and resend a stale point.
  if (!preserveTarget && (forceTarget || !hadStaticDraft || state.mode === 'dynamic')) {
    waterGunRangeMm.value = state.ground_range_mm;
    waterGunBearingDeg.value = state.bearing_deg;
    waterGunTargetSource.value = state.source;
    waterGunTargetLabel.value = state.target_label;
  }
  if (!previousState || previousState.spray_enabled !== state.spray_enabled || state.spray_enabled) {
    waterGunSpraySchedule.value = state.spray_schedule;
    if (state.spray_schedule === 'timed') setWaterGunDurationFields(state.spray_duration_seconds);
  }
  if (state.timed_out) {
    waterGunMessage.value = '动态会话已超时，水枪已停止，最后目标位置已保留。';
  } else if (state.stop_reason === 'timed_complete') {
    waterGunMessage.value = '已停止喷水。';
  }
}

async function loadWaterGunControlState(): Promise<void> {
  try {
    const state = await getWaterGunState();
    syncWaterGunState(state, true);
    if (state.mode === 'dynamic') startWaterGunHeartbeat();
  } catch (error) {
    waterGunMessage.value = userErrorText(error, '水枪控制状态暂时无法读取。');
  }
}

function setWaterGunTargetFromPointer(event: PointerEvent): void {
  const element = waterGunFieldRef.value;
  if (!element) return;
  const rect = element.getBoundingClientRect();
  const viewX = (event.clientX - rect.left) / rect.width * 800;
  const viewY = (event.clientY - rect.top) / rect.height * 400;
  const clampedX = Math.max(30, Math.min(770, viewX));
  const clampedY = Math.max(15, Math.min(385, viewY));
  const right = (clampedX - 400) / 370 * waterGunManualHalfWidthMm;
  const forward = (385 - clampedY) / 370 * waterGunManualForwardMaxMm;
  // ESP32 only accepts a radial distance of 300..1200 mm. Clamp the Web
  // selection before sending so the displayed point is always executable.
  const rawRangeMm = Math.hypot(right, forward);
  waterGunRangeMm.value = Math.round(Math.max(waterGunMinRangeMm, Math.min(waterGunMaxRangeMm, rawRangeMm)));
  waterGunBearingDeg.value = Math.round(Math.atan2(right, forward) * 180 / Math.PI * 10) / 10;
  waterGunTargetSource.value = 'manual';
  waterGunTargetLabel.value = '';
  waterGunMessage.value = waterGunDynamicActive.value ? '动态目标正在实时更新。' : '目标已调整，尚未发送。';
  if (waterGunDynamicActive.value) scheduleWaterGunDynamicSend();
}

async function setWaterGunSprayEnabled(enabled: boolean): Promise<void> {
  if (waterGunBusy.value || waterGunSpraying.value === enabled) return;
  if (enabled && (waterGunSpraySchedule.value === null || waterGunTimedDurationError.value)) {
    waterGunMessage.value = waterGunTimedDurationError.value || '请先选择喷射时间。';
    return;
  }
  waterGunBusy.value = true;
  if (waterGunDynamicActive.value) {
    try {
      const sessionId = waterGunState.value?.session_id;
      if (!sessionId) throw new Error('动态会话不存在。');
      const state = await setWaterGunDynamicSpray(sessionId, enabled);
      syncWaterGunState(state);
      waterGunMessage.value = enabled ? '动态追踪喷水已开启。' : '已停止喷水，动态追踪仍在运行。';
    } catch (error) {
      waterGunMessage.value = userErrorText(error, '动态喷水状态更新失败。');
    } finally {
      waterGunBusy.value = false;
    }
    return;
  }
  try {
    const schedule = enabled
      ? waterGunSpraySchedule.value!
      : (waterGunState.value?.spray_schedule ?? waterGunSpraySchedule.value ?? 'continuous');
    const durationSeconds = schedule === 'timed'
      ? (enabled ? waterGunDurationTotalSeconds.value : (waterGunState.value?.spray_duration_seconds ?? waterGunDurationTotalSeconds.value))
      : null;
    const state = await setWaterGunStaticTarget({
      ...waterGunConfirmedTargetPayload(),
      spray_enabled: enabled,
      spray_schedule: schedule,
      spray_duration_seconds: durationSeconds,
    });
    syncWaterGunState(state);
    waterGunMessage.value = enabled
      ? (schedule === 'timed' ? `已开启定时喷水 ${formatWaterGunDuration(durationSeconds ?? 0)}。` : '已开启持续喷水。')
      : '已停止喷水。';
  } catch (error) {
    waterGunMessage.value = userErrorText(error, '水枪状态更新失败。');
  } finally {
    waterGunBusy.value = false;
  }
}

function selectWaterGunMode(mode: 'static' | 'dynamic'): void {
  if (mode === 'dynamic') {
    if (!waterGunDynamicActive.value) waterGunDynamicConfirmOpen.value = true;
    return;
  }
  if (waterGunDynamicActive.value) void finishWaterGunDynamic(false);
}

function returnWaterGunToActualTarget(): void {
  const state = waterGunState.value;
  if (!state) return;
  waterGunRangeMm.value = state.ground_range_mm;
  waterGunBearingDeg.value = state.bearing_deg;
  waterGunTargetSource.value = state.source;
  waterGunTargetLabel.value = state.target_label;
  waterGunMessage.value = '已回到水枪当前实际目标位置。';
}

function startWaterGunPointer(event: PointerEvent): void {
  event.preventDefault();
  waterGunPointerActive.value = true;
  waterGunFieldRef.value?.setPointerCapture(event.pointerId);
  setWaterGunTargetFromPointer(event);
}

function moveWaterGunPointer(event: PointerEvent): void {
  if (waterGunPointerActive.value) setWaterGunTargetFromPointer(event);
}

function endWaterGunPointer(event: PointerEvent): void {
  if (!waterGunPointerActive.value) return;
  waterGunPointerActive.value = false;
  waterGunFieldRef.value?.releasePointerCapture(event.pointerId);
  if (waterGunDynamicActive.value) scheduleWaterGunDynamicSend(true);
}

function scheduleWaterGunDynamicSend(immediate = false): void {
  if (!waterGunDynamicActive.value || !waterGunState.value?.session_id) return;
  waterGunPendingDynamicTarget.value = { range: waterGunRangeMm.value, bearing: waterGunBearingDeg.value };
  if (waterGunDynamicSendTimer !== undefined) {
    if (!immediate) return;
    window.clearTimeout(waterGunDynamicSendTimer);
    waterGunDynamicSendTimer = undefined;
  }
  waterGunDynamicSendTimer = window.setTimeout(() => {
    waterGunDynamicSendTimer = undefined;
    void flushWaterGunDynamicTarget();
  }, immediate ? 0 : 100);
}

async function flushWaterGunDynamicTarget(): Promise<void> {
  // Serialize HTTP target updates. Without this guard, responses can arrive
  // out of order and an older pointer position can overwrite the final point.
  if (waterGunDynamicTargetSending) return;
  const target = waterGunPendingDynamicTarget.value;
  const sessionId = waterGunState.value?.session_id;
  if (!target || !sessionId || !waterGunDynamicActive.value) return;
  waterGunPendingDynamicTarget.value = null;
  waterGunDynamicTargetSending = true;
  try {
    const state = await updateWaterGunDynamicTarget(sessionId, {
      ground_range_mm: target.range,
      bearing_deg: target.bearing,
    });
    if (waterGunState.value?.session_id === state.session_id) {
      syncWaterGunState(state, true, waterGunPendingDynamicTarget.value !== null || waterGunPointerActive.value);
    }
  } catch (error) {
    waterGunMessage.value = userErrorText(error, '动态目标发送失败，请重新指定目标。');
  } finally {
    waterGunDynamicTargetSending = false;
    // Pointer events that happened during the request are collapsed into one
    // latest target and sent only after the current request has completed.
    if (waterGunPendingDynamicTarget.value !== null && waterGunDynamicActive.value) {
      scheduleWaterGunDynamicSend(true);
    }
  }
}

function startWaterGunHeartbeat(): void {
  stopWaterGunHeartbeat();
  waterGunHeartbeatTimer = window.setInterval(() => {
    const sessionId = waterGunState.value?.session_id;
    if (!sessionId || !waterGunDynamicActive.value) return;
    void heartbeatWaterGunDynamic(sessionId)
      .then((state) => {
        // The backend owns the dynamic sequence because every heartbeat also
        // becomes an ESP32-visible MQTT keepalive. Never overwrite a newer
        // local target response with an older heartbeat response.
        if (waterGunState.value?.session_id !== state.session_id) return;
        const currentSequence = waterGunState.value?.sequence ?? 0;
        if (state.sequence >= currentSequence) {
          syncWaterGunState(state, true, hasLocalDynamicTarget());
        }
      })
      .catch(async (error) => {
        waterGunMessage.value = userErrorText(error, '动态会话已断开，水泵将自动停止。');
        stopWaterGunHeartbeat();
        await loadWaterGunControlState();
      });
  }, 1000);
}

function stopWaterGunHeartbeat(): void {
  if (waterGunHeartbeatTimer !== undefined) window.clearInterval(waterGunHeartbeatTimer);
  waterGunHeartbeatTimer = undefined;
  if (waterGunDynamicSendTimer !== undefined) window.clearTimeout(waterGunDynamicSendTimer);
  waterGunDynamicSendTimer = undefined;
  waterGunPendingDynamicTarget.value = null;
}

async function confirmWaterGunStaticTarget(): Promise<void> {
  const targetChanged = waterGunStaticDraftDirty.value;
  const wasSpraying = waterGunSpraying.value;
  waterGunBusy.value = true;
  try {
    const state = await setWaterGunStaticTarget({
      ...waterGunTargetPayload(),
      spray_enabled: targetChanged ? false : wasSpraying,
      spray_schedule: targetChanged ? 'continuous' : (waterGunState.value?.spray_schedule ?? 'continuous'),
      spray_duration_seconds: targetChanged ? null : waterGunState.value?.spray_duration_seconds,
    });
    syncWaterGunState(state, true);
    waterGunStaticConfirmOpen.value = false;
    if (targetChanged && wasSpraying) {
      waterGunSpraySchedule.value = null;
      setWaterGunDurationFields(0);
      waterGunMessage.value = '目标已更改，喷水已关闭。请重新选择喷射时间后开启。';
    } else {
      waterGunMessage.value = '目标已确认。';
    }
  } catch (error) {
    waterGunMessage.value = userErrorText(error, '静态目标发送失败。');
  } finally {
    waterGunBusy.value = false;
  }
}

async function confirmWaterGunDynamicStart(): Promise<void> {
  waterGunBusy.value = true;
  try {
    const state = await startWaterGunDynamic({ ...waterGunTargetPayload(), spray_enabled: false });
    syncWaterGunState(state, true);
    waterGunDynamicConfirmOpen.value = false;
    waterGunMessage.value = '已进入动态模式，默认关闭喷水。';
    startWaterGunHeartbeat();
  } catch (error) {
    waterGunMessage.value = userErrorText(error, '无法进入动态模式。');
  } finally {
    waterGunBusy.value = false;
  }
}

async function finishWaterGunDynamic(_keepSpraying = false): Promise<boolean> {
  const sessionId = waterGunState.value?.session_id;
  if (!sessionId) return true;
  waterGunBusy.value = true;
  stopWaterGunHeartbeat();
  try {
    const state = await stopWaterGunDynamic(sessionId, false);
    syncWaterGunState(state, true);
    waterGunMessage.value = '已转为静态模式，水枪已关闭，最后目标位置已保留。';
    return true;
  } catch (error) {
    waterGunMessage.value = userErrorText(error, '动态模式退出失败，请立即检查设备状态。');
    if (waterGunDynamicActive.value) startWaterGunHeartbeat();
    return false;
  } finally {
    waterGunBusy.value = false;
  }
}

function requestViewChange(view: ViewKey): void {
  if (activeView.value === 'control' && view !== 'control' && waterGunDynamicActive.value && waterGunSpraying.value) {
    void finishWaterGunDynamic(false).then((stopped) => {
      if (stopped) activeView.value = view;
    });
    return;
  }
  activeView.value = view;
}

function lastDataUpdateText(timestamp?: number): string {
  if (!timestamp) {
    return '正在等待设备数据';
  }
  const elapsed = Math.max(0, Date.now() - timestamp);
  if (elapsed < 60_000) {
    return '数据刚刚更新';
  }
  const minutes = Math.floor(elapsed / 60_000);
  if (minutes < 60) {
    return `数据更新于 ${minutes} 分钟前`;
  }
  return `最近更新 ${formatDateTime(timestamp)}`;
}

function alarmStateLabel(alarm: AlarmRecord): string {
  if (alarm.state === 'resolved') {
    return '已恢复';
  }
  if (alarm.state === 'acknowledged') {
    return '已确认';
  }
  return '待处理';
}

function alarmStateLevel(alarm: AlarmRecord): StatusLevel {
  if (alarm.state === 'resolved') {
    return 'good';
  }
  return alarm.level === 'danger' ? 'danger' : 'watch';
}

const statusSummary = computed<Array<{ label: string; state: StatusLevel }>>(() => {
  const status = latest.value?.status;
  if (!status) {
    return [];
  }
  return [
    { label: `设备网络${status.wifi === 'connected' ? '正常' : '异常'}`, state: status.wifi === 'connected' ? 'good' : 'danger' },
    { label: `云端连接${status.mqtt === 'connected' ? '正常' : '中断'}`, state: status.mqtt === 'connected' ? 'good' : 'danger' },
  ];
});

const metricCards = computed<MetricCardVm[]>(() => {
  if (!latest.value) {
    return [];
  }
  return historyMetricDefinitions.map((definition) => {
    const currentValue = currentMetricValue(definition.key);
    const range = metricTargetRanges.value[definition.key];
    const status = metricTargetStatus(currentValue, range);
    return {
      key: definition.key,
      title: metricDisplayTitle(definition.key),
      value: metricValueText(definition.key, currentValue),
      unit: definition.unit,
      hint: Number.isFinite(currentValue) ? metricHint(status.kind, definition.key) : '传感器未接入或当前数据异常',
      state: status.state,
      icon: metricIcon(definition.key),
      color: definition.color,
      currentValue,
      statusLabel: status.label,
      targetText: `目标 ${range.min}-${range.max} ${definition.unit}`,
      trendText: metricTrendText(definition),
      aiInsight: Number.isFinite(currentValue) ? metricAiInsight(status.kind, definition.key) : '当前没有可靠数据，不参与智能判断。',
    };
  });
});

const selectedMetricCard = computed(() => metricCards.value.find((metric) => metric.key === selectedMetricKey.value) ?? null);

const sortedAssistantThreads = computed(() => [...assistantThreads.value].sort((left, right) => {
  if (left.pinned !== right.pinned) {
    return left.pinned ? -1 : 1;
  }
  return right.updated_at - left.updated_at;
}));

const activeAssistantThread = computed(() => (
  assistantThreads.value.find((thread) => thread.id === activeAssistantThreadId.value) ?? null
));

const overviewMetricCards = computed(() => metricCards.value.map((metric) => ({
  ...metric,
  hint: `${metric.statusLabel} · ${metric.hint}`,
})));

const realtimeMetricCards = computed(() => metricCards.value);

const aiAnalysisViewActive = computed(() => (
  pageVisible.value && (activeView.value === 'overview' || activeView.value === 'ai')
));

const cameraPanelActive = computed(() => true);

const aiAnalysisUpdateText = computed(() => {
  if (aiAnalysisLoading.value) {
    return '正在生成最新分析';
  }
  if (aiAnalysisCompletedAt.value) {
    return `更新 ${formatDateTime(aiAnalysisCompletedAt.value)}`;
  }
  return '尚未生成';
});

function clampRiskScore(value: unknown): number {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    return 0;
  }
  return Math.max(0, Math.min(100, Math.round(value)));
}

function riskScoreState(score: number): StatusLevel {
  if (score >= 70) {
    return 'danger';
  }
  if (score >= 35) {
    return 'watch';
  }
  return 'good';
}

function analysisStatusLabel(analysis: AiAnalysisResponse | null): string {
  if (!analysis) {
    return '等待 AI';
  }
  if (analysis.ai_connected === false) {
    return '智能分析暂不可用';
  }
  return analysis.risk_status || riskLabel(analysis.risk_level);
}

function analysisStatusState(analysis: AiAnalysisResponse | null): StatusLevel {
  if (!analysis || analysis.ai_connected === false) {
    return 'neutral';
  }
  if (typeof analysis.risk_score === 'number') {
    return riskScoreState(analysis.risk_score);
  }
  return analysis.risk_level === 'low' ? 'good' : analysis.risk_level === 'medium' ? 'watch' : 'danger';
}

function retrievalStatusLabel(status?: RetrievalStatus): string {
  if (status === 'success') return '已联网检索';
  if (status === 'partial') return '部分来源可用';
  if (status === 'unavailable') return '在线资料暂不可用';
  return '未使用联网资料';
}

function retrievalStatusState(status?: RetrievalStatus): StatusLevel {
  if (status === 'success') return 'good';
  if (status === 'partial') return 'watch';
  return 'neutral';
}

function sourceStatusLabel(source: AgriSourceInfo): string {
  if (!source.configured) return '待配置';
  if (!source.enabled) return '已停用';
  if (source.status === 'available') return '连接正常';
  if (source.status === 'unavailable') return '连接异常';
  return '等待检查';
}

function sourceStatusState(source: AgriSourceInfo): StatusLevel {
  if (source.status === 'available') return 'good';
  if (source.status === 'unavailable') return 'danger';
  if (!source.configured) return 'watch';
  return 'neutral';
}

function referenceKey(reference: KnowledgeReference): string {
  return reference.referenceId || `${reference.sourceType || 'local'}-${reference.itemId || 0}-${reference.chunkId || 0}-${reference.title}`;
}

const aiRiskScore = computed(() => {
  if (!latest.value || realtimeMetricCards.value.length === 0) {
    return 0;
  }
  if (typeof aiAnalysis.value?.risk_score === 'number') {
    return clampRiskScore(aiAnalysis.value.risk_score);
  }

  const metricScore = realtimeMetricCards.value.reduce((total, metric) => {
    if (metric.state === 'good') {
      return total + 2;
    }
    const range = metricTargetRanges.value[metric.key];
    const span = Math.max(range.max - range.min, 1);
    const distance = metric.currentValue < range.min
      ? range.min - metric.currentValue
      : Math.max(metric.currentValue - range.max, 0);
    const severity = Math.min(distance / span, 1);
    return total + (metric.state === 'danger' ? 18 : 14) + severity * 22;
  }, 0);

  const analysisFloor = aiAnalysis.value?.risk_level === 'high'
    ? 82
    : aiAnalysis.value?.risk_level === 'medium'
      ? 54
      : aiAnalysis.value?.risk_level === 'low'
        ? 18
        : 0;

  return Math.min(100, Math.round(Math.max(metricScore, analysisFloor)));
});

const aiRiskStatus = computed<{ label: string; state: StatusLevel }>(() => {
  if (!latest.value) {
    return { label: '等待数据', state: 'neutral' };
  }
  if (aiAnalysis.value?.ai_connected === false) {
    return { label: '智能分析暂不可用', state: 'neutral' };
  }
  if (aiAnalysis.value?.risk_status && typeof aiAnalysis.value.risk_score === 'number') {
    return {
      label: aiAnalysis.value.risk_status,
      state: riskScoreState(aiRiskScore.value),
    };
  }
  if (aiRiskScore.value >= 70) {
    return { label: '高风险', state: 'danger' };
  }
  if (aiRiskScore.value >= 35) {
    return { label: '需关注', state: 'watch' };
  }
  return { label: '较稳定', state: 'good' };
});

const aiRiskSummary = computed(() => {
  if (!latest.value) {
    return '等待实时采样数据。';
  }
  if (aiAnalysis.value?.summary && typeof aiAnalysis.value.risk_score === 'number') {
    return aiAnalysis.value.summary;
  }
  if (aiRiskScore.value >= 70) {
    return '多项指标偏离明显，请优先处理高风险项。';
  }
  if (aiRiskScore.value >= 35) {
    return '部分指标偏离目标，建议小幅调整并复查。';
  }
  return '当前环境整体平稳，保持现有策略并继续观察。';
});

const aiRiskFactors = computed<AiRiskFactor[]>(() => {
  const apiFactors = aiAnalysis.value?.risk_factors;
  if (apiFactors && apiFactors.length > 0) {
    return apiFactors.slice(0, 3).map((factor, index) => ({
      key: factor.key || `api-factor-${index}`,
      label: factor.label,
      detail: factor.detail,
      state: factor.state,
    }));
  }

  const factors = realtimeMetricCards.value
    .filter((metric) => metric.state !== 'good')
    .map((metric) => ({
      key: metric.key,
      label: metric.title,
      detail: `${metric.statusLabel}，${metric.hint}`,
      state: metric.state === 'danger' ? 'danger' as const : 'watch' as const,
    }))
    .sort((left, right) => {
      const weight = { danger: 2, watch: 1, good: 0, neutral: 0 };
      return weight[right.state] - weight[left.state];
    })
    .slice(0, 3);

  if (factors.length > 0) {
    return factors;
  }

  return [{
    key: 'stable',
    label: '环境稳定',
    detail: '关键指标在目标范围内',
    state: 'good',
  }];
});

const selectedMetricDefinition = computed(() => historyMetricDefinitions.find((metric) => metric.key === selectedMetricKey.value) ?? null);
const selectedMetricInputStep = computed(() => selectedMetricKey.value ? metricTargetInputSteps[selectedMetricKey.value] : 0.01);

const contentLayoutClass = computed(() => ({
  'content-layout--assistant-open': assistantOpen.value,
}));

const contentLayoutStyle = computed<Record<string, string>>(() => ({
  '--assistant-width': `${assistantWidth.value}px`,
}));

const selectedMetricChartOption = computed<EChartsOption>(() => metricChartOptionFor(selectedMetricDefinition.value));

function metricChartOptionFor(metric: HistoryMetricDefinition | null): EChartsOption {
  if (!metric) {
    return {};
  }
  const values = historyPoints.value.map(metric.value);
  const range = historyAxisRange(values);
  return {
    tooltip: { trigger: 'axis' },
    grid: { left: 58, right: 24, top: 34, bottom: 30 },
    xAxis: {
      type: 'time',
      axisLabel: { formatter: (value: number) => formatTime(value) },
    },
    yAxis: {
      type: 'value',
      name: `${metric.name}(${metric.unit})`,
      min: range.min,
      max: range.max,
      axisLine: { show: true, lineStyle: { color: metric.color } },
      axisTick: { lineStyle: { color: metric.color } },
      axisLabel: { color: metric.color },
      nameTextStyle: { color: metric.color, fontWeight: 700 },
      splitLine: { lineStyle: { color: '#e7eee8' } },
    },
    series: [{
      name: metric.name,
      type: 'line',
      smooth: true,
      showSymbol: true,
      symbol: 'circle',
      symbolSize: 7,
      data: historyPoints.value.map((point) => [point.timestamp, metric.value(point)]),
      connectNulls: false,
      color: metric.color,
      lineStyle: { width: 3, color: metric.color },
      itemStyle: { color: '#ffffff', borderColor: metric.color, borderWidth: 2 },
      emphasis: { focus: 'series', scale: 1.2 },
    }],
  };
}

const overviewChartOption = computed<EChartsOption>(() => buildMultiMetricChartOption(false));
const historyChartOption = computed<EChartsOption>(() => buildMultiMetricChartOption(true));
const historyWindowStart = computed(() => historyWindowEnd.value - historyWindowDurationMs.value);
const historyChartPoints = computed<HistoryPoint[]>(() => (
  buildHistoryChartPoints(historyPoints.value, historyWindowStart.value, historyWindowEnd.value)
));
const historyWindowDurationLabel = computed(() => historyWindowDurationText(historyWindowDurationMs.value));
const multiMetricChartMinWidth = computed(() => {
  const selectedCount = selectedHistoryMetricKeys.value.length;
  const layout = multiMetricAxisLayout(selectedCount);
  const plotWidth = selectedCount >= 7 ? 540 : selectedCount >= 5 ? 500 : selectedCount >= 3 ? 440 : 360;
  return Math.max(720, layout.left + layout.right + plotWidth);
});

function multiMetricAxisLayout(selectedCount: number): { left: number; right: number; top: number; spacing: number } {
  const leftAxisCount = Math.ceil(selectedCount / 2);
  const rightAxisCount = selectedCount - leftAxisCount;
  const spacing = selectedCount >= 7 ? 76 : selectedCount >= 5 ? 68 : 60;
  return {
    left: Math.max(86, 86 + Math.max(0, leftAxisCount - 1) * spacing),
    right: Math.max(86, 86 + Math.max(0, rightAxisCount - 1) * spacing),
    top: selectedCount >= 5 ? 82 : 66,
    spacing,
  };
}

function buildMultiMetricChartOption(showSymbols: boolean): EChartsOption {
  const selectedDefinitions = historyMetricDefinitions.filter((item) => selectedHistoryMetricKeys.value.includes(item.key));
  const selectedCount = selectedDefinitions.length;
  const axisLayout = multiMetricAxisLayout(selectedCount);
  return {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'line', snap: true },
      triggerOn: 'mousemove',
    },
    legend: { show: false },
    grid: {
      left: axisLayout.left,
      right: axisLayout.right,
      top: axisLayout.top,
      bottom: 34,
    },
    xAxis: {
      type: 'time',
      min: historyWindowStart.value,
      max: historyWindowEnd.value,
      axisLabel: { formatter: (value: number) => formatTime(value) },
      splitLine: { show: false },
    },
    yAxis: selectedDefinitions.map((definition, index) => {
      const values = historyChartPoints.value.map(definition.value);
      const range = historyAxisRange(values);
      return {
        type: 'value',
        name: `${definition.name}\n(${definition.unit})`,
        min: range.min,
        max: range.max,
        position: index % 2 === 0 ? 'left' : 'right',
        offset: Math.floor(index / 2) * axisLayout.spacing,
        axisLine: { show: true, lineStyle: { color: definition.color } },
        axisTick: { lineStyle: { color: definition.color } },
        axisLabel: { color: definition.color, margin: 8, hideOverlap: true },
        nameGap: 22,
        nameTextStyle: {
          color: definition.color,
          fontWeight: 700,
          lineHeight: 16,
          align: index % 2 === 0 ? 'left' : 'right',
          verticalAlign: 'bottom',
        },
        splitLine: { show: index === 0, lineStyle: { color: '#e7eee8' } },
      };
    }),
    series: selectedDefinitions.map((definition, index) => ({
      name: definition.name,
      type: 'line',
      smooth: true,
      showSymbol: true,
      symbol: 'circle',
      symbolSize: showSymbols ? 6 : 8,
      yAxisIndex: index,
      data: historyChartPoints.value.map((point) => [point.timestamp, definition.value(point)]),
      connectNulls: false,
      color: definition.color,
      lineStyle: { width: 3, color: definition.color },
      itemStyle: { color: '#ffffff', borderColor: definition.color, borderWidth: 2, opacity: showSymbols ? 1 : 0 },
      emphasis: {
        focus: 'series',
        scale: 1.18,
        itemStyle: { color: '#ffffff', borderColor: definition.color, borderWidth: 2, opacity: 1 },
      },
    })),
  };
}

function historyMinute(timestamp: number): number {
  return Math.floor(timestamp / historySampleIntervalMs) * historySampleIntervalMs;
}

function clampHistorySliderValue(value: number): number {
  return Math.min(100, Math.max(0, value));
}

function normalizeHistoryWindowDuration(value: number): number {
  const rounded = Math.round(value / historySampleIntervalMs) * historySampleIntervalMs;
  return Math.min(historyWindowMaxDurationMs, Math.max(historyWindowMinDurationMs, rounded));
}

function historyWindowDurationForSlider(sliderValue: number): number {
  const fraction = clampHistorySliderValue(sliderValue) / 100;
  const rawDuration = historyWindowMinDurationMs * Math.pow(
    historyWindowMaxDurationMs / historyWindowMinDurationMs,
    fraction,
  );
  return normalizeHistoryWindowDuration(rawDuration);
}

function historySliderValueForDuration(durationMs: number): number {
  const normalizedDuration = normalizeHistoryWindowDuration(durationMs);
  const fraction = Math.log(normalizedDuration / historyWindowMinDurationMs)
    / Math.log(historyWindowMaxDurationMs / historyWindowMinDurationMs);
  return Math.round(clampHistorySliderValue(fraction * 100));
}

function historyWindowDurationText(durationMs: number): string {
  const minutes = Math.round(durationMs / 60_000);
  if (minutes < 60) {
    return `${minutes} 分钟`;
  }
  const hours = Math.floor(minutes / 60);
  const remainder = minutes % 60;
  return remainder === 0 ? `${hours} 小时` : `${hours} 小时 ${remainder} 分钟`;
}

function updateHistoryWindowSlider(event: Event): void {
  const target = event.target;
  if (!(target instanceof HTMLInputElement)) {
    return;
  }
  historyWindowSliderValue.value = clampHistorySliderValue(Number(target.value));
  historyWindowDurationMs.value = historyWindowDurationForSlider(historyWindowSliderValue.value);
  schedulePersistentDashboardStateSave();
}

function buildHistoryChartPoints(
  rawPoints: HistoryPoint[],
  windowStart: number,
  windowEnd: number,
): HistoryPoint[] {
  const pointIntervalMs = (windowEnd - windowStart) / historyChartPointCount;
  const latestPointBySlot = new Map<number, HistoryPoint>();
  rawPoints.forEach((point) => {
    if (
      !Number.isFinite(point.timestamp)
      || point.timestamp < windowStart
      || point.timestamp >= windowEnd + historySampleIntervalMs
    ) {
      return;
    }
    const slot = Math.min(
      historyChartPointCount - 1,
      Math.floor((point.timestamp - windowStart) / pointIntervalMs),
    );
    const existing = latestPointBySlot.get(slot);
    if (!existing || point.timestamp >= existing.timestamp) {
      latestPointBySlot.set(slot, point);
    }
  });

  const points: HistoryPoint[] = [];
  for (let slot = 0; slot < historyChartPointCount; slot += 1) {
    const slotTimestamp = windowStart + slot * pointIntervalMs;
    const point = latestPointBySlot.get(slot);
    points.push({
      timestamp: point ? Math.min(point.timestamp, windowEnd) : slotTimestamp,
      temperature: point?.temperature ?? null,
      light: point?.light ?? null,
      co2: point?.co2 ?? null,
      soil_moisture: point?.soil_moisture ?? null,
      humidity: point?.humidity ?? null,
      gas_resistance: point?.gas_resistance ?? null,
      soil_ec: point?.soil_ec ?? null,
    });
  }
  return points;
}

function historyAxisRange(values: Array<number | null>): { min: number; max: number } {
  const finiteValues = values.filter((value): value is number => (
    typeof value === 'number' && Number.isFinite(value)
  ));
  if (finiteValues.length === 0) {
    return { min: 0, max: 1 };
  }
  const minValue = Math.min(...finiteValues);
  const maxValue = Math.max(...finiteValues);
  const rawRange = maxValue - minValue;
  const padding = rawRange > 0 ? rawRange * 0.16 : Math.max(Math.abs(maxValue) * 0.08, 1);
  const min = minValue - padding;
  const max = maxValue + padding;
  return {
    min: Number(min.toFixed(2)),
    max: Number(max.toFixed(2)),
  };
}

function isPlainRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isMetricTargetRangeValue(value: unknown): value is MetricTargetRange {
  return isPlainRecord(value)
    && typeof value.min === 'number'
    && Number.isFinite(value.min)
    && typeof value.max === 'number'
    && Number.isFinite(value.max);
}

function persistedMetricTargetRanges(value: unknown): Record<HistoryMetricKey, MetricTargetRange> {
  const ranges = { ...metricTargetRanges.value };
  if (!isPlainRecord(value)) {
    return ranges;
  }
  historyMetricDefinitions.forEach((definition) => {
    const range = value[definition.key];
    if (isMetricTargetRangeValue(range)) {
      ranges[definition.key] = { min: range.min, max: range.max };
    }
  });
  return ranges;
}

function createAssistantWelcomeMessage(): ChatMessage {
  return {
    id: `assistant-welcome-${Date.now()}`,
    role: 'assistant',
    content: '我是智慧农业专家助手。你可以输入文字、上传叶片图片，或用语音提问。',
    created_at: Date.now(),
  };
}

function createAssistantThread(messages: ChatMessage[] = [createAssistantWelcomeMessage()]): AssistantThread {
  const now = Date.now();
  return {
    id: `assistant-thread-${now}-${Math.random().toString(36).slice(2, 8)}`,
    title: assistantThreadTitleFromMessages(messages),
    pinned: false,
    created_at: now,
    updated_at: now,
    messages,
  };
}

function ensureAssistantThreadState(): void {
  if (assistantThreads.value.length === 0) {
    const thread = createAssistantThread();
    assistantThreads.value = [thread];
    activeAssistantThreadId.value = thread.id;
    chatMessages.value = thread.messages;
    return;
  }
  const activeThread = assistantThreads.value.find((thread) => thread.id === activeAssistantThreadId.value)
    ?? sortedAssistantThreads.value[0];
  activeAssistantThreadId.value = activeThread.id;
  chatMessages.value = activeThread.messages.length > 0 ? activeThread.messages : [createAssistantWelcomeMessage()];
}

function assistantThreadTitleFromMessages(messages: ChatMessage[]): string {
  const firstUserMessage = messages.find((message) => message.role === 'user' && message.content.trim().length > 0);
  if (!firstUserMessage) {
    return '新对话';
  }
  const title = firstUserMessage.content.replace(/\s+/g, ' ').trim();
  return title.length > 18 ? `${title.slice(0, 18)}...` : title;
}

function assistantThreadHasConversationContent(messages: ChatMessage[]): boolean {
  return messages.some((message) => (
    message.role === 'user'
    && (message.content.trim().length > 0 || Boolean(message.image_url))
  ));
}

function assistantThreadPreview(thread: AssistantThread): string {
  const latestMessage = [...thread.messages].reverse().find((message) => message.content.trim().length > 0);
  if (!latestMessage) {
    return '暂无消息';
  }
  const text = latestMessage.content.replace(/\s+/g, ' ').trim();
  return text.length > 34 ? `${text.slice(0, 34)}...` : text;
}

function persistedAssistantThreads(value: unknown): AssistantThread[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .filter((item): item is AssistantThread => (
      isPlainRecord(item)
      && typeof item.id === 'string'
      && typeof item.title === 'string'
      && typeof item.created_at === 'number'
      && typeof item.updated_at === 'number'
    ))
    .map((item) => {
      const messages = persistedChatMessages(item.messages);
      return {
        id: item.id,
        title: item.title.trim() || assistantThreadTitleFromMessages(messages),
        pinned: item.pinned === true,
        created_at: item.created_at,
        updated_at: item.updated_at,
        messages: messages.length > 0 ? messages : [createAssistantWelcomeMessage()],
      };
    })
    .slice(-24);
}

function persistedChatMessages(value: unknown): ChatMessage[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter((item): item is ChatMessage => (
    isPlainRecord(item)
    && (item.role === 'user' || item.role === 'assistant')
    && typeof item.id === 'string'
    && typeof item.content === 'string'
    && typeof item.created_at === 'number'
  )).map((item) => ({
    ...item,
    typing: false,
    references: item.referencesVerified === true ? item.references : [],
    image_url: item.image_url?.startsWith('blob:') ? undefined : item.image_url,
  })).slice(-30);
}

function serializableChatMessages(): ChatMessage[] {
  return chatMessages.value
    .filter((message) => !message.typing)
    .map((message) => ({
      ...message,
      image_url: message.image_url?.startsWith('blob:') ? undefined : message.image_url,
    }))
    .slice(-30);
}

function syncActiveAssistantThreadMessages(updateTitle = false): void {
  if (!activeAssistantThreadId.value) {
    return;
  }
  const messages = serializableChatMessages();
  const hasRealMessage = messages.some((message) => message.role === 'user');
  assistantThreads.value = assistantThreads.value.map((thread) => {
    if (thread.id !== activeAssistantThreadId.value) {
      return thread;
    }
    const shouldRefreshTitle = updateTitle || thread.title === '新对话';
    return {
      ...thread,
      title: shouldRefreshTitle ? assistantThreadTitleFromMessages(messages) : thread.title,
      updated_at: updateTitle && hasRealMessage ? Date.now() : thread.updated_at,
      messages: messages.length > 0 ? messages : [createAssistantWelcomeMessage()],
    };
  });
}

function serializableAssistantThreads(): AssistantThread[] {
  syncActiveAssistantThreadMessages();
  return assistantThreads.value
    .map((thread) => ({
      ...thread,
      title: thread.title.trim() || assistantThreadTitleFromMessages(thread.messages),
      messages: thread.messages
        .filter((message) => !message.typing)
        .map((message) => ({
          ...message,
          image_url: message.image_url?.startsWith('blob:') ? undefined : message.image_url,
        }))
        .slice(-30),
    }))
    .slice(-24);
}

function serializeDashboardState(): PersistedDashboardState {
  return {
    version: 1,
    activeView: activeView.value,
    selectedHistoryMetricKeys: [...selectedHistoryMetricKeys.value],
    historyWindowDurationMs: historyWindowDurationMs.value,
    metricTargetRanges: metricTargetRanges.value,
    selectedKbId: selectedKbId.value,
    knowledgeQuestion: knowledgeQuestion.value,
    knowledgeAnswer: knowledgeAnswer.value,
    assistantOpen: assistantOpen.value,
    assistantWidth: assistantWidth.value,
    chatInput: chatInput.value,
    chatMessages: serializableChatMessages(),
    assistantThreads: serializableAssistantThreads(),
    activeAssistantThreadId: activeAssistantThreadId.value,
    weatherCity: weatherCity.value,
    weatherPanelOpen: weatherPanelOpen.value,
  };
}

async function savePersistentDashboardStateNow(): Promise<void> {
  if (!persistentStateReady || applyingPersistentState) {
    return;
  }
  if (persistentStateSaveTimer) {
    window.clearTimeout(persistentStateSaveTimer);
    persistentStateSaveTimer = undefined;
  }
  await savePersistedDashboardState(serializeDashboardState());
}

function schedulePersistentDashboardStateSave(delay = 300): void {
  if (!persistentStateReady || applyingPersistentState || typeof window === 'undefined') {
    return;
  }
  if (persistentStateSaveTimer) {
    window.clearTimeout(persistentStateSaveTimer);
  }
  persistentStateSaveTimer = window.setTimeout(() => {
    persistentStateSaveTimer = undefined;
    void savePersistentDashboardStateNow();
  }, delay);
}

async function loadPersistentDashboardState(): Promise<void> {
  const state = await getPersistedDashboardState();
  if (!state) {
    return;
  }
  applyingPersistentState = true;
  try {
    if (state.activeView && isViewKey(state.activeView)) {
      activeView.value = state.activeView;
    }
    if (typeof state.weatherCity === 'string' && state.weatherCity.trim().length > 0) {
      weatherCity.value = state.weatherCity.trim() === 'wuxi' ? '无锡' : state.weatherCity.trim();
      weatherCityDraft.value = weatherCity.value;
    }
    if (typeof state.weatherPanelOpen === 'boolean') {
      weatherPanelOpen.value = state.weatherPanelOpen;
    }
    if (Array.isArray(state.selectedHistoryMetricKeys)) {
      const historyKeys = state.selectedHistoryMetricKeys.filter((key): key is HistoryMetricKey => (
        typeof key === 'string' && historyMetricDefinitions.some((definition) => definition.key === key)
      ));
      if (historyKeys.length > 0) {
        selectedHistoryMetricKeys.value = historyKeys;
      }
    }
    if (typeof state.historyWindowDurationMs === 'number' && Number.isFinite(state.historyWindowDurationMs)) {
      historyWindowDurationMs.value = normalizeHistoryWindowDuration(state.historyWindowDurationMs);
      historyWindowSliderValue.value = historySliderValueForDuration(historyWindowDurationMs.value);
    }
    metricTargetRanges.value = persistedMetricTargetRanges(state.metricTargetRanges);
    if (typeof state.selectedKbId === 'number' && Number.isFinite(state.selectedKbId)) {
      selectedKbId.value = state.selectedKbId;
    }
    if (typeof state.knowledgeQuestion === 'string') {
      knowledgeQuestion.value = state.knowledgeQuestion;
    }
    if (state.knowledgeAnswer && isPlainRecord(state.knowledgeAnswer)) {
      knowledgeAnswer.value = state.knowledgeAnswer as unknown as KnowledgeAnalyzeResult;
    }
    if (typeof state.assistantOpen === 'boolean') {
      assistantOpen.value = state.assistantOpen;
    }
    if (typeof state.assistantWidth === 'number' && Number.isFinite(state.assistantWidth)) {
      assistantWidth.value = clampAssistantWidth(state.assistantWidth);
    }
    if (typeof state.chatInput === 'string') {
      chatInput.value = state.chatInput;
    }
    const savedThreads = persistedAssistantThreads(state.assistantThreads);
    if (savedThreads.length > 0) {
      assistantThreads.value = savedThreads;
      const activeThread = savedThreads.find((thread) => thread.id === state.activeAssistantThreadId)
        ?? [...savedThreads].sort((left, right) => {
          if (left.pinned !== right.pinned) {
            return left.pinned ? -1 : 1;
          }
          return right.updated_at - left.updated_at;
        })[0];
      activeAssistantThreadId.value = activeThread.id;
      chatMessages.value = activeThread.messages;
    } else {
      const savedMessages = persistedChatMessages(state.chatMessages);
      if (savedMessages.length > 0) {
        const migratedThread = createAssistantThread(savedMessages);
        assistantThreads.value = [migratedThread];
        activeAssistantThreadId.value = migratedThread.id;
        chatMessages.value = savedMessages;
      }
    }
    ensureAssistantThreadState();
  } finally {
    applyingPersistentState = false;
  }
}

function isHistoryMetricSelected(key: HistoryMetricKey): boolean {
  return selectedHistoryMetricKeys.value.includes(key);
}

function toggleHistoryMetric(key: HistoryMetricKey): void {
  if (isHistoryMetricSelected(key)) {
    if (selectedHistoryMetricKeys.value.length === 1) {
      return;
    }
    selectedHistoryMetricKeys.value = selectedHistoryMetricKeys.value.filter((item) => item !== key);
    void savePersistentDashboardStateNow();
    return;
  }
  selectedHistoryMetricKeys.value = [...selectedHistoryMetricKeys.value, key];
  void savePersistentDashboardStateNow();
}

function currentMetricValue(key: HistoryMetricKey): number {
  const sensors = latest.value?.sensors;
  if (!sensors) {
    return Number.NaN;
  }
  if (key === 'temperature') {
    return sensors.temperature;
  }
  if (key === 'humidity') {
    return sensors.humidity;
  }
  if (key === 'light') {
    return sensors.light;
  }
  if (key === 'co2') {
    return sensors.co2;
  }
  if (key === 'soil_moisture') {
    return sensors.soil_moisture;
  }
  if (key === 'soil_ec') {
    return sensors.soil_ec;
  }
  return sensors.gas_resistance;
}

function metricDisplayTitle(key: HistoryMetricKey): string {
  if (key === 'temperature') {
    return '棚内温度';
  }
  if (key === 'humidity') {
    return '环境湿度';
  }
  if (key === 'light') {
    return '光照强度';
  }
  if (key === 'co2') {
    return '二氧化碳浓度';
  }
  if (key === 'soil_moisture') {
    return '空气湿度';
  }
  if (key === 'soil_ec') {
    return '土壤肥力';
  }
  return '空气质量';
}

function metricIcon(key: HistoryMetricKey): Component {
  if (key === 'temperature') {
    return Thermometer;
  }
  if (key === 'humidity') {
    return Droplets;
  }
  if (key === 'light') {
    return Sun;
  }
  if (key === 'co2') {
    return Wind;
  }
  if (key === 'soil_moisture') {
    return Droplets;
  }
  if (key === 'soil_ec') {
    return Gauge;
  }
  return Leaf;
}

function metricValueText(key: HistoryMetricKey, value: number): string {
  if (!Number.isFinite(value)) {
    return '--';
  }
  if (key === 'soil_ec') {
    return numberText(value, 2);
  }
  if (key === 'temperature' || key === 'humidity' || key === 'soil_moisture') {
    return numberText(value);
  }
  return String(Math.round(value));
}

function metricTargetStatus(value: number, range: MetricTargetRange): { kind: 'high' | 'low' | 'normal'; label: string; state: 'danger' | 'low' | 'good' } {
  if (!Number.isFinite(value)) {
    return { kind: 'normal', label: '不可用', state: 'low' };
  }
  if (value > range.max) {
    return { kind: 'high', label: '过高', state: 'danger' };
  }
  if (value < range.min) {
    return { kind: 'low', label: '过低', state: 'low' };
  }
  return { kind: 'normal', label: '适中', state: 'good' };
}

function metricHint(kind: 'high' | 'low' | 'normal', key: HistoryMetricKey): string {
  if (kind === 'normal') {
    return '当前值处于目标区间';
  }
  if (kind === 'high') {
    if (key === 'light') {
      return '当前值过高，可考虑关闭卷帘或降低补光';
    }
    if (key === 'soil_moisture') {
      return '当前值过高，建议暂停水泵并通风观察';
    }
    return '当前值过高，建议及时调整控制策略';
  }
  if (key === 'light') {
    return '当前值过低，可打开卷帘或开启补光';
  }
  if (key === 'co2') {
    return '当前值过低，可结合通风状态补充气肥';
  }
  return '当前值过低，建议关注补充或调节';
}

function metricTrendText(definition: HistoryMetricDefinition): string {
  const values = historyPoints.value
    .map(definition.value)
    .filter((value): value is number => typeof value === 'number' && Number.isFinite(value));
  if (values.length < 2) {
    return '等待更多采样';
  }
  const current = values[values.length - 1];
  const previous = values[values.length - 2];
  const diff = current - previous;
  if (Math.abs(diff) < 0.01) {
    return '最近趋势平稳';
  }
  const text = definition.key === 'soil_ec' ? numberText(Math.abs(diff), 2) : numberText(Math.abs(diff));
  return `${diff > 0 ? '较上次上升' : '较上次下降'} ${text} ${definition.unit}`;
}

function metricAiInsight(kind: 'high' | 'low' | 'normal', key: HistoryMetricKey): string {
  if (kind === 'normal') {
    return '智能判断：维持当前控制策略，继续观察曲线变化。';
  }
  if (key === 'temperature') {
    return kind === 'high' ? '智能判断：优先检查通风和遮阳状态。' : '智能判断：关注夜间保温和补光联动。';
  }
  if (key === 'humidity' || key === 'soil_moisture') {
    return kind === 'high' ? '智能判断：病害风险上升，建议降低湿度。' : '智能判断：关注补水节奏，避免作物胁迫。';
  }
  if (key === 'light') {
    return kind === 'high' ? '智能判断：强光时段注意遮阴。' : '智能判断：可优先打开卷帘并评估补光。';
  }
  if (key === 'co2') {
    return kind === 'high' ? '智能判断：注意通风换气，避免浓度堆积。' : '智能判断：通风后可结合气肥补充。';
  }
  return kind === 'high' ? '智能判断：当前指标偏高，需要复核设备状态。' : '智能判断：当前指标偏低，建议结合其他指标判断。';
}

function scheduleMetricEditorTransitionClear(): void {
  if (metricEditorTimer) {
    window.clearTimeout(metricEditorTimer);
  }
  metricEditorTimer = window.setTimeout(() => {
    metricEditorTransition.value = '';
  }, 380);
}

function clearMetricEditorChartTimer(): void {
  if (metricEditorChartTimer) {
    window.clearTimeout(metricEditorChartTimer);
    metricEditorChartTimer = undefined;
  }
}

function scheduleMetricEditorChartActivation(delay = 420): void {
  clearMetricEditorChartTimer();
  metricEditorChartActive.value = false;
  metricEditorChartTimer = window.setTimeout(() => {
    metricEditorChartActive.value = Boolean(selectedMetricKey.value);
    metricEditorChartTimer = undefined;
  }, delay);
}

function elementRect(element: Element): MetricEditorRect {
  const rect = element.getBoundingClientRect();
  return {
    left: rect.left,
    top: rect.top,
    width: Math.max(rect.width, 1),
    height: Math.max(rect.height, 1),
  };
}

function elementSourceRect(element: Element): MetricEditorSourceRect {
  const rect = elementRect(element);
  return {
    ...rect,
    documentLeft: rect.left + window.scrollX,
    documentTop: rect.top + window.scrollY,
  };
}

function sourceRectAtCurrentScroll(source: MetricEditorSourceRect): MetricEditorRect {
  return {
    left: source.documentLeft - window.scrollX,
    top: source.documentTop - window.scrollY,
    width: source.width,
    height: source.height,
  };
}

function metricEditorTargetRect(): MetricEditorRect {
  const workspace = document.querySelector<HTMLElement>('.workspace');
  if (!workspace) {
    return {
      left: 0,
      top: 0,
      width: Math.max(window.innerWidth, 1),
      height: Math.max(window.innerHeight, 1),
    };
  }

  const rect = workspace.getBoundingClientRect();
  const styles = window.getComputedStyle(workspace);
  const paddingLeft = Number.parseFloat(styles.paddingLeft) || 0;
  const paddingRight = Number.parseFloat(styles.paddingRight) || 0;
  const paddingBottom = Number.parseFloat(styles.paddingBottom) || 0;
  const topbar = workspace.querySelector<HTMLElement>('.topbar');
  const left = Math.max(12, rect.left + paddingLeft);
  const top = Math.max(12, topbar ? topbar.getBoundingClientRect().bottom + 20 : rect.top);
  const rightSpace = Math.max(12, window.innerWidth - rect.right + paddingRight);
  const width = Math.max(320, window.innerWidth - left - rightSpace);
  const height = Math.max(520, window.innerHeight - top - paddingBottom);

  return { left, top, width, height };
}

function captureMetricCardRects(): void {
  metricEditorSourceRects.clear();
  document.querySelectorAll<HTMLElement>('[data-metric-key]').forEach((element) => {
    const key = element.dataset.metricKey as HistoryMetricKey | undefined;
    if (key) {
      metricEditorSourceRects.set(key, elementSourceRect(element));
    }
  });
}

function metricCardSourceRect(key: HistoryMetricKey, element?: Element | null): MetricEditorSourceRect | null {
  const sourceElement = element ?? document.querySelector<HTMLElement>(`[data-metric-key="${key}"]`);
  if (sourceElement) {
    const rect = elementSourceRect(sourceElement);
    if (rect.width > 1 && rect.height > 1) {
      metricEditorLastSourceRect = rect;
      metricEditorSourceRects.set(key, rect);
      return rect;
    }
  }
  const cachedRect = metricEditorSourceRects.get(key);
  if (cachedRect) {
    metricEditorLastSourceRect = cachedRect;
    return cachedRect;
  }
  if (metricEditorLastSourceRect) {
    return metricEditorLastSourceRect;
  }
  return null;
}

function fallbackMetricCardRect(target: MetricEditorRect): MetricEditorRect {
  return {
    left: target.left + target.width / 2 - 120,
    top: target.top + target.height / 2 - 80,
    width: 240,
    height: 160,
  };
}

function metricCardRect(key: HistoryMetricKey, element?: Element | null): MetricEditorRect {
  const source = metricCardSourceRect(key, element);
  if (source) {
    return sourceRectAtCurrentScroll(source);
  }
  const target = metricEditorTargetRect();
  return fallbackMetricCardRect(target);
}

function setMetricEditorMotion(target: MetricEditorRect, source: MetricEditorRect): void {
  metricEditorStyle.value = {
    '--metric-editor-left': `${target.left}px`,
    '--metric-editor-top': `${target.top}px`,
    '--metric-editor-width': `${target.width}px`,
    '--metric-editor-height': `${target.height}px`,
    '--metric-editor-motion-x': `${source.left - target.left}px`,
    '--metric-editor-motion-y': `${source.top - target.top}px`,
    '--metric-editor-scale-x': String(source.width / target.width),
    '--metric-editor-scale-y': String(source.height / target.height),
  };
}

function updateMetricEditorMotion(key: HistoryMetricKey, element?: Element | null): void {
  const target = metricEditorTargetRect();
  const source = metricCardRect(key, element);
  setMetricEditorMotion(target, source);
}

function updateMetricEditorClosingMotion(key: HistoryMetricKey): void {
  const target = metricEditorStageRef.value ? elementRect(metricEditorStageRef.value) : metricEditorTargetRect();
  const source = metricCardRect(key);
  setMetricEditorMotion(target, source);
}

function hydrateMetricTargetDraft(key: HistoryMetricKey): void {
  selectedMetricKey.value = key;
  const range = metricTargetRanges.value[key];
  targetMinDraft.value = String(range.min);
  targetMaxDraft.value = String(range.max);
  targetRangeError.value = '';
  targetRangeSavedMessage.value = '';
  targetRangeSaving.value = false;
}

function openMetricEditor(key: HistoryMetricKey, event?: MouseEvent | KeyboardEvent): void {
  const sourceElement = event?.currentTarget instanceof Element ? event.currentTarget : null;
  if (selectedMetricKey.value && selectedMetricKey.value !== key) {
    const currentIndex = historyMetricDefinitions.findIndex((metric) => metric.key === selectedMetricKey.value);
    const nextIndex = historyMetricDefinitions.findIndex((metric) => metric.key === key);
    metricEditorTransition.value = nextIndex > currentIndex ? 'switch-next' : 'switch-prev';
    hydrateMetricTargetDraft(key);
    scheduleMetricEditorTransitionClear();
    metricEditorChartActive.value = true;
    return;
  }
  captureMetricCardRects();
  updateMetricEditorMotion(key, sourceElement);
  metricEditorTransition.value = 'opening';
  hydrateMetricTargetDraft(key);
  scheduleMetricEditorChartActivation();
  scheduleMetricEditorTransitionClear();
}

function switchMetricEditor(direction: -1 | 1): void {
  if (!selectedMetricKey.value) {
    return;
  }
  const currentIndex = historyMetricDefinitions.findIndex((metric) => metric.key === selectedMetricKey.value);
  const nextIndex = (currentIndex + direction + historyMetricDefinitions.length) % historyMetricDefinitions.length;
  metricEditorTransition.value = direction > 0 ? 'switch-next' : 'switch-prev';
  hydrateMetricTargetDraft(historyMetricDefinitions[nextIndex].key);
  metricEditorChartActive.value = true;
  scheduleMetricEditorTransitionClear();
}

function closeMetricEditor(): void {
  if (!selectedMetricKey.value) {
    return;
  }
  updateMetricEditorClosingMotion(selectedMetricKey.value);
  metricEditorTransition.value = 'closing';
  metricEditorChartActive.value = false;
  clearMetricEditorChartTimer();
  targetRangeError.value = '';
  targetRangeSavedMessage.value = '';
  targetRangeSaving.value = false;
  if (targetRangeSavedTimer) {
    window.clearTimeout(targetRangeSavedTimer);
    targetRangeSavedTimer = undefined;
  }
  if (metricEditorTimer) {
    window.clearTimeout(metricEditorTimer);
  }
  metricEditorTimer = window.setTimeout(() => {
    selectedMetricKey.value = null;
    metricEditorTransition.value = '';
  }, 360);
}

async function saveMetricTargetRange(): Promise<void> {
  if (!selectedMetricKey.value) {
    return;
  }
  const min = Number(targetMinDraft.value);
  const max = Number(targetMaxDraft.value);
  if (!Number.isFinite(min) || !Number.isFinite(max)) {
    targetRangeError.value = '请输入有效数字';
    targetRangeSavedMessage.value = '';
    return;
  }
  if (min > max) {
    targetRangeError.value = '目标下限不能高于上限';
    targetRangeSavedMessage.value = '';
    return;
  }
  targetRangeSaving.value = true;
  targetRangeSavedMessage.value = '正在保存目标区间...';
  metricTargetRanges.value = {
    ...metricTargetRanges.value,
    [selectedMetricKey.value]: { min, max },
  };
  targetRangeError.value = '';
  await savePersistentDashboardStateNow();
  try {
    await saveAlarmSettings(latest.value?.device_id ?? 'greenhouse_001_s3', metricTargetRanges.value);
    alarmSettingsSyncPending.value = false;
  } catch (error) {
    console.warn('Alarm reminder settings sync failed.', error);
    alarmSettingsSyncPending.value = true;
  }
  targetRangeSaving.value = false;
  targetRangeSavedMessage.value = alarmSettingsSyncPending.value
    ? '目标范围已保存，报警提醒暂未同步，将自动重试'
    : `已保存：${min} - ${max} ${selectedMetricDefinition.value?.unit ?? ''}`.trim();
  if (targetRangeSavedTimer) {
    window.clearTimeout(targetRangeSavedTimer);
  }
  targetRangeSavedTimer = window.setTimeout(() => {
    targetRangeSavedMessage.value = '';
    targetRangeSavedTimer = undefined;
  }, 2200);
}

async function syncDeviceAlarmSettings(pushLocalRanges = false): Promise<void> {
  const deviceId = latest.value?.device_id ?? 'greenhouse_001_s3';
  try {
    if (pushLocalRanges) {
      await saveAlarmSettings(deviceId, metricTargetRanges.value);
      alarmSettingsSyncPending.value = false;
      return;
    }
    const settings = await getAlarmSettings(deviceId, metricTargetRanges.value);
    if (settings.configured) {
      metricTargetRanges.value = persistedMetricTargetRanges(settings.ranges);
    } else {
      await saveAlarmSettings(deviceId, metricTargetRanges.value);
    }
    alarmSettingsSyncPending.value = false;
  } catch (error) {
    console.warn('Alarm reminder settings unavailable.', error);
    alarmSettingsSyncPending.value = true;
  }
}

async function confirmAlarmHandled(alarm: AlarmRecord): Promise<void> {
  if (alarm.state !== 'open' || acknowledgingAlarmId.value) {
    return;
  }
  acknowledgingAlarmId.value = alarm.id;
  alarmActionMessage.value = '';
  try {
    const updated = await acknowledgeAlarm(alarm.id);
    alarms.value = alarms.value.map((item) => item.id === updated.id ? updated : item);
    alarmActionMessage.value = '已确认处理，我们会继续观察后续数据。';
  } catch (error) {
    console.warn('Alarm acknowledgement failed.', error);
    alarmActionMessage.value = '暂时无法确认，请稍后重试。';
  } finally {
    acknowledgingAlarmId.value = '';
  }
}

function clampAssistantWidth(width: number): number {
  if (typeof window === 'undefined') {
    return Math.min(Math.max(width, minAssistantWidth), defaultAssistantWidth);
  }
  const maxByViewport = window.innerWidth * maxAssistantViewportRatio;
  const maxByWorkspace = window.innerWidth - minWorkspaceWidth;
  const maxWidth = Math.max(minAssistantWidth, Math.min(maxByViewport, maxByWorkspace));
  return Math.min(Math.max(width, minAssistantWidth), maxWidth);
}

function requestAssistantLayoutResize(): void {
  if (typeof window === 'undefined') {
    return;
  }
  window.requestAnimationFrame(() => {
    window.dispatchEvent(new Event('resize'));
  });
}

function applyPendingAssistantResize(): void {
  assistantResizeFrame = 0;
  if (!assistantResizing.value || typeof window === 'undefined') {
    return;
  }
  assistantWidth.value = clampAssistantWidth(window.innerWidth - pendingAssistantResizeClientX);
}

function scheduleAssistantResize(clientX: number): void {
  if (typeof window === 'undefined') {
    return;
  }
  pendingAssistantResizeClientX = clientX;
  if (assistantResizeFrame) {
    return;
  }
  assistantResizeFrame = window.requestAnimationFrame(applyPendingAssistantResize);
}

function handleAssistantResizeMove(event: PointerEvent): void {
  if (!assistantResizing.value) {
    return;
  }
  scheduleAssistantResize(event.clientX);
}

function stopAssistantResize(): void {
  if (typeof window === 'undefined') {
    return;
  }
  window.removeEventListener('pointermove', handleAssistantResizeMove);
  window.removeEventListener('pointerup', stopAssistantResize);
  window.removeEventListener('pointercancel', stopAssistantResize);
  document.body.classList.remove('is-resizing-assistant');
  if (assistantResizeFrame) {
    window.cancelAnimationFrame(assistantResizeFrame);
    assistantResizeFrame = 0;
  }
  if (assistantResizing.value) {
    assistantWidth.value = clampAssistantWidth(window.innerWidth - pendingAssistantResizeClientX);
    assistantResizing.value = false;
    requestAssistantLayoutResize();
    schedulePersistentDashboardStateSave();
  }
}

function startAssistantResize(event: PointerEvent): void {
  if (typeof window === 'undefined' || window.innerWidth <= 860) {
    return;
  }
  event.preventDefault();
  assistantResizing.value = true;
  pendingAssistantResizeClientX = event.clientX;
  document.body.classList.add('is-resizing-assistant');
  assistantWidth.value = clampAssistantWidth(window.innerWidth - event.clientX);
  window.addEventListener('pointermove', handleAssistantResizeMove);
  window.addEventListener('pointerup', stopAssistantResize);
  window.addEventListener('pointercancel', stopAssistantResize);
}

function resetAssistantWidth(): void {
  assistantWidth.value = clampAssistantWidth(defaultAssistantWidth);
  requestAssistantLayoutResize();
  schedulePersistentDashboardStateSave();
}

function handleAssistantViewportResize(): void {
  assistantWidth.value = clampAssistantWidth(assistantWidth.value);
  requestAssistantLayoutResize();
}

watch(activeView, (view, previousView) => {
  if (previousView === 'overview' && view !== 'overview') {
    restoreSavedCameraPositionConfig();
  }
  if (view !== 'realtime') {
    closeMetricEditor();
  }
  if (view === 'knowledge' && agriSources.value.length === 0) {
    void refreshAgriSources();
  }
  syncAiAnalysisSchedule();
  schedulePersistentDashboardStateSave();
});

watch(pageVisible, () => {
  syncAiAnalysisSchedule();
});

watch(assistantOpen, (open) => {
  if (open) {
    void scrollAssistantToBottom();
    void nextTick(resizeChatInput);
  } else {
    assistantShowScrollButton.value = false;
  }
  schedulePersistentDashboardStateSave();
});

watch([weatherCity, weatherPanelOpen], () => {
  schedulePersistentDashboardStateSave();
});

watch(knowledgeQuestion, () => {
  schedulePersistentDashboardStateSave(800);
});

watch(chatInput, () => {
  void nextTick(resizeChatInput);
  schedulePersistentDashboardStateSave(800);
});

function riskLabel(level: AiAnalysisResponse['risk_level']): string {
  if (level === 'high') {
    return '高风险';
  }
  if (level === 'medium') {
    return '中等风险';
  }
  return '低风险';
}

function weatherValueText(value: unknown, unit = ''): string {
  if (value === null || value === undefined || value === '') {
    return '暂无';
  }
  return `${value}${unit}`;
}

function weatherModuleReason(module: { available: boolean; reason?: string } | undefined): string {
  if (!module) {
    return '暂未加载';
  }
  return module.available ? '' : '暂未开通';
}

function weatherCityLabel(city: WeatherCityOption): string {
  return weatherLocationLabel(city.path || city.name || city.id || '未知城市');
}

function weatherCityValue(city: WeatherCityOption): string {
  return city.name || city.id || weatherCityLabel(city);
}

function weatherLocationLabel(value: string): string {
  const parts = value
    .split(/[,\s·]+/)
    .map((part) => part.trim())
    .filter((part) => part && part !== '中国' && part !== 'CN');
  const uniqueParts = parts.filter((part, index) => parts.indexOf(part) === index);
  if (uniqueParts.length >= 3) {
    return `${uniqueParts[0]} · ${uniqueParts[1]}`;
  }
  if (uniqueParts.length >= 2) {
    return `${uniqueParts[0]} · ${uniqueParts[1]}`;
  }
  return uniqueParts[0] || value;
}

function weatherDayLabel(item: WeatherDailyItem, index: number): string {
  if (index === 0) {
    return '今天';
  }
  if (index === 1) {
    return '明天';
  }
  return weatherDateText(item.date);
}

function weatherConditionText(item: WeatherDailyItem): string {
  const day = item.condition_day || '--';
  const night = item.condition_night || '--';
  return day === night ? day : `${day}转${night}`;
}

function weatherRainText(item: WeatherDailyItem): string {
  if (typeof item.rainfall === 'number' && item.rainfall > 0) {
    return `降雨 ${item.rainfall}mm`;
  }
  if (typeof item.precip === 'number' && item.precip > 0) {
    const precip = item.precip <= 1 ? Math.round(item.precip * 100) : Math.round(item.precip);
    return `降雨概率 ${precip}%`;
  }
  return '降雨少';
}

function buildWeatherImpactTips(): string[] {
  const tips: string[] = [];
  const sensors = latest.value?.sensors;
  const rainyDays = weatherDailyItems.value.filter((item) => {
    const text = `${item.condition_day ?? ''}${item.condition_night ?? ''}`;
    return /雨|雪|雷|storm|rain|shower/i.test(text) || (typeof item.rainfall === 'number' && item.rainfall > 0);
  }).length;
  const highHumidityDays = weatherDailyItems.value.filter((item) => typeof item.humidity === 'number' && item.humidity >= 80).length;
  const maxHigh = Math.max(...weatherDailyItems.value.map((item) => item.high ?? -Infinity));

  if (rainyDays > 0 || highHumidityDays > 0) {
    tips.push('未来几天偏湿或有降雨，建议重点关注棚内湿度，必要时提前通风降湿。');
  }
  if (sensors && sensors.humidity > 70) {
    tips.push(`当前棚内湿度 ${sensors.humidity}%RH 偏高，天气偏湿时更容易增加叶面病害风险。`);
  }
  if (Number.isFinite(maxHigh) && maxHigh >= 32) {
    tips.push('室外最高温较高，午后注意遮阳、补水和风机联动，避免棚温快速升高。');
  }
  if (sensors && sensors.light < metricTargetRanges.value.light.min) {
    tips.push('当前棚内光照偏低，阴雨天气下可考虑延长补光或适当打开卷帘。');
  }
  if (tips.length === 0) {
    tips.push('未来天气对棚内管理压力不大，保持当前监测频率即可。');
  }
  return tips.slice(0, 3);
}

function weatherDateText(value?: string | null): string {
  if (!value) {
    return '暂无时间';
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: value.includes('T') ? '2-digit' : undefined,
    minute: value.includes('T') ? '2-digit' : undefined,
  }).format(date);
}

function setKnowledgeError(action: string, error: unknown): void {
  console.warn(`${action} failed.`, error);
  knowledgeError.value = `${action}没有完成：${userErrorText(error)}`;
}

function replaceAgriSource(nextSource: AgriSourceInfo): void {
  agriSources.value = agriSources.value.map((source) => (
    source.sourceId === nextSource.sourceId ? nextSource : source
  ));
}

async function refreshAgriSources(): Promise<void> {
  agriSourcesLoading.value = true;
  try {
    agriSources.value = await getAgriSources();
    agriSourceError.value = '';
  } catch (error) {
    agriSourceError.value = userErrorText(error, '在线农业知识源状态暂时无法获取。');
  } finally {
    agriSourcesLoading.value = false;
  }
}

async function toggleAgriSource(source: AgriSourceInfo): Promise<void> {
  if (agriSourceBusyId.value) return;
  agriSourceBusyId.value = source.sourceId;
  try {
    replaceAgriSource(await updateAgriSource(source.sourceId, !source.enabled));
    agriSourceError.value = '';
  } catch (error) {
    agriSourceError.value = userErrorText(error, '来源设置没有保存。');
  } finally {
    agriSourceBusyId.value = null;
  }
}

async function testOnlineAgriSource(source: AgriSourceInfo): Promise<void> {
  if (agriSourceBusyId.value) return;
  agriSourceBusyId.value = source.sourceId;
  try {
    const result = await testAgriSource(source.sourceId);
    replaceAgriSource(result.source);
    agriSourceError.value = '';
  } catch (error) {
    agriSourceError.value = userErrorText(error, '测试连接没有完成。');
    await refreshAgriSources();
  } finally {
    agriSourceBusyId.value = null;
  }
}

async function refreshKnowledge(preferredKbId = selectedKbId.value): Promise<void> {
  try {
    const bases = await getKnowledgeBases();
    knowledgeBases.value = [...bases];
    if (bases.length === 0) {
      selectedKbId.value = 0;
      knowledgeItems.value = [];
      knowledgeError.value = '';
      return;
    }
    const selected = bases.find((item) => item.kbId === preferredKbId) ?? bases[0];
    selectedKbId.value = selected.kbId;
    knowledgeItems.value = await getKnowledgeItems(selected.kbId);
    knowledgeError.value = '';
    schedulePersistentDashboardStateSave();
  } catch (error) {
    setKnowledgeError('加载知识库', error);
  }
}

function weatherPayloadFromBundle(bundle: WeatherBundle): WeatherPayload | null {
  const data = bundle.current.available ? bundle.current.data : null;
  if (!data) {
    return null;
  }
  return {
    location: weatherLocationLabel(data.location),
    condition: data.condition,
    temperature: data.temperature,
    humidity: data.humidity,
    wind_direction: data.wind_direction,
    wind_level: data.wind_level,
    updated_at: data.updated_at,
  };
}

async function loadWeather(city = weatherCity.value): Promise<WeatherBundle | null> {
  weatherLoading.value = true;
  try {
    const bundle = await getWeatherBundle(city);
    weatherBundle.value = bundle;
    currentWeather.value = weatherPayloadFromBundle(bundle);
    weatherError.value = weatherModuleReason(bundle.current);
    return bundle;
  } catch (error) {
    weatherBundle.value = null;
    currentWeather.value = null;
    weatherError.value = userErrorText(error, '天气信息暂时无法获取，请稍后重试。');
    console.warn('Weather bundle failed to load.', error);
    try {
      currentWeather.value = await getCurrentWeather(city);
    } catch {
      // Keep the explicit bundle error when the secondary request also fails.
    }
    return null;
  } finally {
    weatherLoading.value = false;
  }
}

function openWeatherPanel(): void {
  weatherPanelOpen.value = true;
  schedulePersistentDashboardStateSave();
  if (!weatherBundle.value && !weatherLoading.value) {
    void loadWeather();
  }
}

function closeWeatherPanel(): void {
  weatherPanelOpen.value = false;
  weatherCityDropdownOpen.value = false;
  schedulePersistentDashboardStateSave();
}

async function searchWeatherCities(): Promise<void> {
  const query = weatherCityDraft.value.trim();
  if (!query) {
    weatherCityOptions.value = [];
    return;
  }
  try {
    weatherPickerMode.value = 'search';
    weatherCityOptions.value = await getWeatherCities(query);
  } catch (error) {
    weatherCityOptions.value = [];
    weatherError.value = userErrorText(error, '城市搜索没有完成，请稍后重试。');
  }
}

function scheduleWeatherCitySearch(): void {
  weatherCityDropdownOpen.value = true;
  weatherPickerMode.value = 'search';
  const query = weatherCityDraft.value.trim();
  if (weatherCitySearchTimer) {
    window.clearTimeout(weatherCitySearchTimer);
    weatherCitySearchTimer = undefined;
  }
  if (!query) {
    weatherCityOptions.value = [];
    weatherPickerMode.value = 'provinces';
    return;
  }
  weatherCitySearchTimer = window.setTimeout(() => {
    weatherCitySearchTimer = undefined;
    void searchWeatherCities();
  }, 180);
}

function openWeatherCityDropdown(): void {
  weatherCityDropdownOpen.value = true;
  weatherPickerMode.value = 'search';
  if (weatherCityDraft.value.trim()) {
    void searchWeatherCities();
  }
}

function openWeatherProvinceDropdown(): void {
  weatherCityDropdownOpen.value = true;
  weatherPickerMode.value = 'provinces';
  weatherSelectedProvince.value = '';
}

function returnToWeatherProvinces(): void {
  weatherSelectedProvince.value = '';
  if (weatherCityDraft.value.trim()) {
    weatherPickerMode.value = 'search';
    void searchWeatherCities();
    return;
  }
  weatherPickerMode.value = 'provinces';
}

async function applyWeatherCity(city = weatherCityDraft.value): Promise<void> {
  const nextCity = city.trim();
  if (!nextCity) {
    return;
  }
  weatherCity.value = nextCity;
  weatherCityDraft.value = nextCity;
  weatherCityOptions.value = [];
  weatherCityDropdownOpen.value = false;
  schedulePersistentDashboardStateSave();
  await loadWeather(nextCity);
}

async function selectWeatherCity(city: WeatherCityOption): Promise<void> {
  if (city.level === 'province' && !city.direct) {
    weatherSelectedProvince.value = city.name ?? '';
    weatherPickerMode.value = 'cities';
    return;
  }
  await applyWeatherCity(weatherCityValue(city));
}

async function confirmWeatherCitySearch(): Promise<void> {
  if (weatherSearchOptions.value.length === 1) {
    await selectWeatherCity(weatherSearchOptions.value[0]);
  }
}

function handleCameraAnalysisUpdated(result: DiseaseDetectionResult | null): void {
  cameraAnalysisResult.value = result;
}

function handleCropPositionsUpdated(result: CurrentCropPositionsResult | null): void {
  currentCropPositions.value = result;
}

async function loadCurrentCropPositions(): Promise<void> {
  try {
    currentCropPositions.value = await getCurrentCropPositions();
  } catch (error) {
    console.warn('Current crop positions unavailable.', error);
  }
}

function selectWaterGunCropTarget(crop: CropPositionInfo): void {
  if (crop.coordinate_status !== 'located' || typeof crop.ground_range_mm !== 'number' || typeof crop.bearing_deg !== 'number') {
    return;
  }
  waterGunRangeMm.value = Math.round(crop.ground_range_mm * 10) / 10;
  waterGunBearingDeg.value = Math.round(crop.bearing_deg * 10) / 10;
  waterGunTargetSource.value = 'vision';
  waterGunTargetLabel.value = crop.crop_name || crop.label;
  waterGunMessage.value = waterGunDynamicActive.value ? '已切换到视觉识别作物目标，动态目标正在更新。' : '已选择视觉识别作物目标，尚未发送。';
  if (waterGunDynamicActive.value) scheduleWaterGunDynamicSend(true);
}

function isPositionQuestion(question: string): boolean {
  const compact = question.replace(/\s+/g, '');
  return /距离|多远|位置|坐标|方位|角度|极坐标|在哪(?:里|儿)?|什么地方|何处|在何方|什么方位/.test(compact);
}

function pendingPositionSelection(): PositionLocateResult | null {
  return positionSelectionSession.value;
}

function pendingPositionTargetLabel(): string {
  return pendingPositionSelection()?.candidates[0]?.label ?? '';
}

function isPositionRefinement(question: string, result: PositionLocateResult | null): boolean {
  if (!result || question.trim().length === 0) return false;
  const compact = question.replace(/\s+/g, '').toLowerCase();
  const labels = result.candidates
    .map((candidate) => candidate.label.replace(/\s+/g, '').toLowerCase())
    .filter(Boolean);
  if (labels.some((label) => compact.includes(label))) return true;

  // A short visual/spatial description following a multiple-target result is
  // treated as a continuation, even when the user does not repeat the object name.
  const hasDiscriminatingFeature = /左|右|中间|中央|最近|最远|前面|后面|上面|下面|旁边|靠近|第[一二三四五六七八九十\d]+|银|金色|黑|白|灰|红|橙|黄|绿|青|蓝|紫|粉|透明|深色|浅色|金属|塑料|木质|玻璃|长|短|大|小|圆|方|宽|窄|粗|细|亮|暗|带有|有个|有一|没有|无/.test(compact);
  return compact.length <= 40 && hasDiscriminatingFeature;
}

function formatPositionReply(result: PositionLocateResult): string {
  if (result.status === 'located' && result.selected) {
    const item = result.selected;
    const side = item.bearing_deg > 0 ? '右' : item.bearing_deg < 0 ? '左' : '正前方';
    return `已定位到${item.label}。它距摄像头约 **${Math.round(item.camera_range_mm)} mm**；从上方看，位于 A 点${side} **${Math.abs(item.bearing_deg).toFixed(1)}°**，A→B 平面距离约 **${Math.round(item.ground_range_mm)} mm**。`;
  }
  return result.message;
}

function positionAnchorTypeLabel(type: PositionLocateResult['candidates'][number]['anchor_type']): string {
  return {
    visual_center: '物体视觉中心',
    surface_center: '物体表面中心',
    footprint_center: '物体底面中心',
    custom: 'AI 选择点',
  }[type] ?? 'AI 选择点';
}

function positionStrategySummary(result: PositionLocateResult): string {
  const candidate = result.selected;
  if (!candidate) return '按本轮候选目标定位';
  if (candidate.height_fallback) return '按桌面投影定位';
  return `按${positionAnchorTypeLabel(candidate.anchor_type)}定位`;
}

const positionCaptureTtlMs = 24 * 60 * 60 * 1000;
const positionCaptureRetryDelayMs = 800;
const positionCaptureMaxRetries = 5;

function positionCaptureKey(result: PositionLocateResult): string {
  return result.annotated_image_url ?? '';
}

function positionCaptureState(result: PositionLocateResult): PositionCaptureLoadState {
  const key = positionCaptureKey(result);
  return positionCaptureStates.value[key] ?? { attempts: 0, retryToken: 0, verifying: false, expired: false };
}

function positionCaptureExpiredByTime(result: PositionLocateResult, now = Date.now()): boolean {
  return Number.isFinite(result.captured_at) && now - result.captured_at >= positionCaptureTtlMs;
}

function isPositionCaptureExpired(result: PositionLocateResult): boolean {
  const state = positionCaptureState(result);
  return state.expired || positionCaptureExpiredByTime(result);
}

function positionCaptureRetryExhausted(result: PositionLocateResult): boolean {
  const state = positionCaptureState(result);
  return !state.expired && state.attempts >= positionCaptureMaxRetries;
}

function withPositionCaptureRetryToken(url: string, token: number): string {
  if (token <= 0) return url;
  const separator = url.includes('?') ? '&' : '?';
  return `${url}${separator}retry=${token}`;
}

function positionCaptureImageSrc(result: PositionLocateResult): string {
  const url = resolveApiAssetUrl(result.annotated_image_url);
  if (!url) return '';
  return withPositionCaptureRetryToken(url, positionCaptureState(result).retryToken);
}

function updatePositionCaptureState(key: string, patch: Partial<PositionCaptureLoadState>): void {
  const current = positionCaptureStates.value[key] ?? { attempts: 0, retryToken: 0, verifying: false, expired: false };
  positionCaptureStates.value = {
    ...positionCaptureStates.value,
    [key]: { ...current, ...patch },
  };
}

function openPositionCapture(result: PositionLocateResult): void {
  if (!result.annotated_image_url || isPositionCaptureExpired(result)) return;
  positionImageModal.value = {
    result,
    title: result.selected?.label ? `${result.selected.label} 定位截图` : '本轮定位截图',
    capturedAt: result.captured_at,
  };
}

function closePositionCapture(): void {
  positionImageModal.value = null;
}

function retryPositionCapture(result: PositionLocateResult): void {
  const key = positionCaptureKey(result);
  if (!key) return;
  const state = positionCaptureState(result);
  updatePositionCaptureState(key, {
    attempts: 0,
    retryToken: state.retryToken + 1,
    verifying: false,
    expired: false,
  });
}

async function handlePositionCaptureLoadError(result: PositionLocateResult): Promise<void> {
  const key = positionCaptureKey(result);
  if (!key) return;
  if (positionCaptureExpiredByTime(result)) {
    updatePositionCaptureState(key, { expired: true, verifying: false });
    return;
  }
  const state = positionCaptureState(result);
  if (state.expired || state.verifying) return;
  const attempts = state.attempts + 1;
  updatePositionCaptureState(key, { attempts, verifying: true });
  const resolvedUrl = resolveApiAssetUrl(result.annotated_image_url);
  if (!resolvedUrl) {
    updatePositionCaptureState(key, { verifying: false });
    return;
  }

  try {
    const response = await fetch(withPositionCaptureRetryToken(resolvedUrl, Date.now()), { cache: 'no-store' });
    if (response.status === 404) {
      updatePositionCaptureState(key, { expired: true, verifying: false });
      return;
    }
  } catch {
    // 网络或缓存层的临时失败不代表截图过期；下面继续安排重试。
  }

  if (attempts >= positionCaptureMaxRetries) {
    updatePositionCaptureState(key, { verifying: false });
    return;
  }

  window.setTimeout(() => {
    const latest = positionCaptureState(result);
    if (latest.expired) return;
    updatePositionCaptureState(key, {
      verifying: false,
      retryToken: latest.retryToken + 1,
    });
  }, positionCaptureRetryDelayMs);
}

function handleGlobalKeydown(event: KeyboardEvent): void {
  if (event.key === 'Escape' && positionImageModal.value) {
    closePositionCapture();
  }
}

async function loadCameraPositionConfig(): Promise<void> {
  const [saved, cameraConfig] = await Promise.all([
    getCameraPositionConfig(),
    getBackendCameraConfig().catch(() => null),
  ]);
  if (cameraConfig) backendCameraConfig.value = cameraConfig;
  if (saved) {
    cameraPositionConfig.value = { ...defaultCameraPositionConfig, ...saved };
    cameraDistortionText.value = cameraPositionConfig.value.distortion.join(', ');
    cameraPositionConfigMessage.value = saved.fx > 0 && saved.fy > 0 ? '定位参数已从后端加载。' : cameraPositionConfigMessage.value;
  }
  rememberSavedCameraPositionConfig();
}

function rememberSavedCameraPositionConfig(): void {
  savedCameraPositionConfigSnapshot = {
    ...cameraPositionConfig.value,
    distortion: [...cameraPositionConfig.value.distortion],
  };
  savedBackendCameraConfigSnapshot = { ...backendCameraConfig.value };
}

function restoreSavedCameraPositionConfig(): void {
  if (cameraPositionConfigSaving.value) return;
  cameraPositionConfig.value = {
    ...savedCameraPositionConfigSnapshot,
    distortion: [...savedCameraPositionConfigSnapshot.distortion],
  };
  backendCameraConfig.value = { ...savedBackendCameraConfigSnapshot };
  cameraDistortionText.value = savedCameraPositionConfigSnapshot.distortion.join(', ');
}

function handleCameraPositionConfigToggle(event: Event): void {
  const details = event.currentTarget as HTMLDetailsElement;
  if (!details.open) restoreSavedCameraPositionConfig();
}

function normalizedCameraPositionConfig(): CameraPositionConfig {
  const distortion = cameraDistortionText.value
    .split(',')
    .map((value) => Number(value.trim()))
    .filter((value) => Number.isFinite(value))
    .slice(0, 5);
  return { ...cameraPositionConfig.value, distortion };
}

async function saveCurrentCameraPositionConfig(): Promise<void> {
  cameraPositionConfigSaving.value = true;
  try {
    cameraPositionConfig.value = normalizedCameraPositionConfig();
    await Promise.all([
      saveCameraPositionConfig(cameraPositionConfig.value),
      saveBackendCameraConfig(backendCameraConfig.value),
    ]);
    rememberSavedCameraPositionConfig();
    cameraPositionConfigMessage.value = '定位参数和后端摄像头配置已保存，下一次定位立即生效。';
  } catch (error) {
    cameraPositionConfigMessage.value = userErrorText(error, '定位参数保存失败，请稍后重试。');
  } finally {
    cameraPositionConfigSaving.value = false;
  }
}

function clearAiAnalysisTimer(): void {
  if (aiAnalysisTimer !== undefined) {
    window.clearTimeout(aiAnalysisTimer);
    aiAnalysisTimer = undefined;
  }
}

function syncAiAnalysisSchedule(): void {
  clearAiAnalysisTimer();
  if (!aiAnalysisViewActive.value || !latest.value || aiAnalysisRequest) {
    return;
  }

  const elapsed = aiAnalysisCompletedAt.value === null
    ? aiAnalysisIntervalMs
    : Date.now() - aiAnalysisCompletedAt.value;
  const delay = Math.max(0, aiAnalysisIntervalMs - elapsed);
  if (delay === 0) {
    void refreshAiAnalysis('auto');
    return;
  }

  aiAnalysisTimer = window.setTimeout(() => {
    aiAnalysisTimer = undefined;
    void refreshAiAnalysis('auto');
  }, delay);
}

async function refreshAiAnalysis(retrievalMode: RetrievalMode = 'force'): Promise<void> {
  if (aiAnalysisRequest) {
    return aiAnalysisRequest;
  }
  if (!latest.value || !aiAnalysisViewActive.value) {
    return;
  }

  clearAiAnalysisTimer();
  aiAnalysisLoading.value = true;
  const telemetry = latest.value;
  const request = (async () => {
    try {
      aiAnalysis.value = await analyzeFarm(telemetry, {
        weather: currentWeather.value,
        weatherBundle: weatherBundle.value,
        history: historyPoints.value,
        disease: diseaseResult.value,
        cameraAnalysis: cameraAnalysisResult.value,
        retrievalMode,
      });
    } finally {
      aiAnalysisCompletedAt.value = Date.now();
      aiAnalysisLoading.value = false;
      aiAnalysisRequest = null;
      syncAiAnalysisSchedule();
    }
  })();
  aiAnalysisRequest = request;
  return request;
}

function handleDocumentVisibilityChange(): void {
  const wasVisible = pageVisible.value;
  pageVisible.value = document.visibilityState === 'visible';
  if (!wasVisible && pageVisible.value) {
    void cameraGrowthPanelRef.value?.captureAndAnalyze();
  }
}

function numberSensor(sensors: Record<string, number | null>, key: string): number | null {
  const value = sensors[key];
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function mergeRealHistoryPoints(...sources: HistoryPoint[][]): HistoryPoint[] {
  const cutoff = historyMinute(Date.now()) - historyWindowMaxDurationMs;
  const latestPointByMinute = new Map<number, HistoryPoint>();
  sources.forEach((points) => {
    points.forEach((point) => {
      if (!Number.isFinite(point.timestamp) || point.timestamp < cutoff) {
        return;
      }
      const bucket = historyMinute(point.timestamp);
      const existing = latestPointByMinute.get(bucket);
      if (!existing || point.timestamp >= existing.timestamp) {
        latestPointByMinute.set(bucket, point);
      }
    });
  });
  return [...latestPointByMinute.values()].sort((left, right) => left.timestamp - right.timestamp);
}

function refreshHistoryWindowEnd(): void {
  const latestTimestamp = historyPoints.value.reduce<number | null>((latest, point) => (
    latest === null || point.timestamp > latest ? point.timestamp : latest
  ), null);
  historyWindowEnd.value = historyMinute(latestTimestamp ?? Date.now());
}

function mergeLiveHistoryPoint(state: SiteState): void {
  const temperature = numberSensor(state.sensors, 'temperature_c');
  const light = numberSensor(state.sensors, 'illuminance_lux');
  const co2 = numberSensor(state.sensors, 'co2_ppm');
  const soilMoisture = numberSensor(state.sensors, 'soil_moisture_pct');
  if (temperature === null && light === null && co2 === null && soilMoisture === null) {
    return;
  }
  const timestamp = state.updated_at || Date.now();
  const point: HistoryPoint = {
    timestamp,
    temperature,
    light,
    co2,
    soil_moisture: soilMoisture,
    humidity: numberSensor(state.sensors, 'humidity_pct'),
    gas_resistance: numberSensor(state.sensors, 'gas_resistance_ohm'),
    soil_ec: numberSensor(state.sensors, 'soil_ec_ms_cm'),
  };
  historyPoints.value = mergeRealHistoryPoints(historyPoints.value, [point]);
  refreshHistoryWindowEnd();
}

function historyValueText(value: number | null, unit: string): string {
  return typeof value === 'number' && Number.isFinite(value) ? `${numberText(value)} ${unit}` : '--';
}

async function calibrateHistory(): Promise<void> {
  try {
    historyPoints.value = mergeRealHistoryPoints(historyPoints.value, await getSiteHistory(12));
  } catch (error) {
    console.warn('History calibration failed.', error);
  } finally {
    refreshHistoryWindowEnd();
  }
}

async function loadDashboard(isBackground = false): Promise<void> {
  if (isBackground) {
    refreshing.value = true;
  } else {
    loading.value = true;
  }
  try {
    const nextLatest = await getLatestTelemetry();
    latest.value = nextLatest;
    const initialHistoryRequest = isBackground ? null : getSiteHistory(12);
    const [siteResult, alarmsResult, healthResult, weatherResult] = await Promise.allSettled([
      getSiteState(),
      getAlarmRecords(),
      getDeviceHealth(),
      loadWeather(weatherCity.value),
    ]);
    if (siteResult.status === 'fulfilled') {
      siteState.value = siteResult.value;
      latest.value = siteStateToTelemetry(siteResult.value);
    } else {
      console.warn('Site state failed to load.', siteResult.reason);
    }
    if (initialHistoryRequest) {
      try {
        historyPoints.value = mergeRealHistoryPoints(historyPoints.value, await initialHistoryRequest);
        refreshHistoryWindowEnd();
      } catch (error) {
        console.warn('History data failed to load.', error);
      }
    }
    if (alarmsResult.status === 'fulfilled') {
      alarms.value = alarmsResult.value;
    } else {
      console.warn('Alarm records failed to load.', alarmsResult.reason);
    }
    if (healthResult.status === 'fulfilled') {
      deviceHealth.value = healthResult.value;
    } else {
      console.warn('Device health failed to load.', healthResult.reason);
    }
    if (weatherResult.status === 'rejected') {
      console.warn('Weather data failed to load.', weatherResult.reason);
    }
    if (alarmSettingsSyncPending.value) {
      void syncDeviceAlarmSettings(true);
    }
  } finally {
    loading.value = false;
    refreshing.value = false;
  }
}

async function refreshDashboardAndCapture(): Promise<void> {
  await loadDashboard(true);
  if (aiAnalysisViewActive.value) {
    await refreshAiAnalysis();
  }
  if (cameraPanelActive.value) {
    await cameraGrowthPanelRef.value?.captureAndAnalyze();
  }
}

/*
 * Retired actuator controls: the confirmed hardware scope contains only the
 * water gun. This block is retained temporarily as inert historical context
 * while API compatibility is removed from the backend in a later contract
 * revision. It must not be re-enabled without a confirmed actuator contract.
 */
/*
async function applyCommand(command: string, value: number, reason: string): Promise<void> {
  if (!latest.value) {
    return;
  }
  const target = command.startsWith('pump_')
    ? 'pump'
    : command.startsWith('light_')
      ? 'grow_light'
      : command.startsWith('heater_')
        ? 'heater'
        : null;
  if (target) {
    const percentValue = value <= 1 ? Math.round(value * 100) : Math.round(value);
    const queued = await sendSiteCommand(target, percentValue, reason);
    siteCommandResults.value = [queued, ...siteCommandResults.value.filter((item) => item.command_id !== queued.command_id)].slice(0, 20);
    return;
  }
  const payload: DeviceCommand = {
    device_id: latest.value.device_id,
    command,
    value,
    reason,
  };
  const result = await sendDeviceCommand(payload);
  const nextStatus = statusAfterCommand(latest.value.status, command, value);
  const normalizedResult = { ...result, status: nextStatus };
  persistedDeviceStatus = nextStatus;
  commandResults.value = [normalizedResult, ...commandResults.value].slice(0, 10);
  latest.value = {
    ...latest.value,
    timestamp: normalizedResult.executed_at,
    status: nextStatus,
  };
  void savePersistentDashboardStateNow();
}

async function setSiteActuatorMaster(target: SiteActuatorTarget, enabled: boolean): Promise<void> {
  if (siteActuatorBusy.value) {
    return;
  }
  const label = siteActuatorDefinitions.find((item) => item.target === target)?.label ?? target;
  siteActuatorBusy.value = target;
  siteControlMessage.value = '';
  try {
    const result = await sendSiteCommand(target, enabled ? 100 : 0, `Web 手动${enabled ? '开启' : '关闭'}${label}`);
    siteCommandResults.value = [result, ...siteCommandResults.value.filter((item) => item.command_id !== result.command_id)].slice(0, 20);
    await refreshSiteSnapshot();
    siteControlMessage.value = `${label}已${enabled ? '开启' : '关闭'}，C5 与页面状态已同步。`;
  } catch (error) {
    siteControlMessage.value = userErrorText(error, `${label}控制失败，请检查后端连接后重试。`);
  } finally {
    siteActuatorBusy.value = null;
  }
}

async function toggleDevice(
  isActive: boolean,
  onCommand: string,
  offCommand: string,
  onReason: string,
  offReason: string,
): Promise<void> {
  await applyCommand(isActive ? offCommand : onCommand, isActive ? 0 : 1, isActive ? offReason : onReason);
}
function commandResultText(result: CommandResult): string {
  return result.command.reason || (result.success ? '设备状态已更新。' : result.message);
}

function commandActionText(command: DeviceCommand): string {
  const labels: Record<string, string> = {
    light_on: '开启补光灯',
    light_off: '关闭补光灯',
  };
  return labels[command.command] ?? '设备状态更新';
}
function aiCommandText(command: { command: string; value: number }): string {
  return commandActionText({
    device_id: latest.value?.device_id ?? '',
    command: command.command,
    value: command.value,
    reason: '',
  });
}

*/

function actionPayloadText(action: AssistantAction, key: string, fallback = ''): string {
  const value = action.payload[key];
  return typeof value === 'string' && value.trim().length > 0 ? value.trim() : fallback;
}

function actionPayloadErrorText(payload: Record<string, unknown>, fallback = '操作没有完成，请稍后重试。'): string {
  const code = typeof payload.error_code === 'string' ? payload.error_code : '';
  if (code === 'device_offline') {
    return '普通 ESP32 当前离线，请检查供电、MQTT 或串口连接后重试。';
  }
  if (code === 'position_expired') {
    const target = typeof payload.target_label === 'string' && payload.target_label.trim() ? payload.target_label.trim() : '目标';
    return `定位结果已过期，请重新识别${target}后再喷水。`;
  }
  const rawError = payload.error;
  const message = typeof rawError === 'string'
    ? rawError
    : isPlainRecord(rawError) && typeof rawError.message === 'string'
      ? rawError.message
      : fallback;
  if (message.includes('普通 ESP32') || message.includes('设备暂未连接')) {
    return '普通 ESP32 当前离线，请检查供电、MQTT 或串口连接后重试。';
  }
  if (message.includes('定位结果已过期')) {
    const target = typeof payload.target_label === 'string' && payload.target_label.trim() ? payload.target_label.trim() : '目标';
    return `定位结果已过期，请重新识别${target}后再喷水。`;
  }
  if (message.includes('本地后端未连接')) {
    return '本地后端未连接，请重启前端和 API 后重试。';
  }
  return message;
}

function assistantActionErrorText(error: unknown, fallback = '操作没有完成，请稍后重试。'): string {
  return actionPayloadErrorText({ error: userErrorText(error, fallback) }, fallback);
}

function actionPayloadNumber(action: AssistantAction, key: string, fallback = 0): number {
  const value = action.payload[key];
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === 'string' && value.trim().length > 0) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : fallback;
  }
  return fallback;
}

function assistantActionStatusText(action: AssistantAction): string {
  if (action.status === 'confirmed') {
    return '已确认，等待设备回执';
  }
  if (action.status === 'executed') {
    return '已执行';
  }
  if (action.status === 'canceled') {
    return '已取消';
  }
  if (action.status === 'failed') {
    return action.error ?? '执行失败';
  }
  if (assistantExecutingActionId.value === action.id) {
    return '执行中';
  }
  return '';
}

function assistantActionConfirmText(action: AssistantAction): string {
  if (assistantExecutingActionId.value === action.id) {
    return '处理中';
  }
  const choiceLabel = actionPayloadText(action, 'choice_label');
  if (choiceLabel) {
    return choiceLabel;
  }
  if (action.type === 'water_gun_target') {
    return '确认喷水';
  }
  return '确认执行';
}

function assistantActionsHeading(actions: AssistantAction[]): string {
  if (actions.some((action) => action.type === 'reply_choice')) {
    return '请选择一个选项';
  }
  if (actions.length > 1 && actions.every((action) => actionPayloadText(action, 'choice_group').length > 0)) {
    return '请选择一个补光档位';
  }
  return '待确认操作';
}

function assistantReplyChoiceActions(actions: AssistantAction[]): AssistantAction[] {
  return actions.filter((action) => (
    action.type === 'reply_choice'
    && (action.status === 'pending' || action.status === 'failed' || action.status === undefined)
  ));
}

function assistantHasVisibleActions(actions: AssistantAction[]): boolean {
  return actions.some((action) => action.type !== 'reply_choice') || assistantReplyChoiceActions(actions).length > 0;
}

function resolveAssistantChoiceGroup(selected: AssistantAction): void {
  const choiceGroup = actionPayloadText(selected, 'choice_group');
  chatMessages.value.forEach((message) => {
    message.suggested_actions?.forEach((action) => {
      if (action.type !== 'reply_choice') return;
      if (choiceGroup && actionPayloadText(action, 'choice_group') !== choiceGroup) return;
      action.status = action.id === selected.id ? 'executed' : 'canceled';
      action.error = '';
    });
  });
  chatMessages.value = [...chatMessages.value];
  syncActiveAssistantThreadMessages();
  schedulePersistentDashboardStateSave();
}

function setAssistantActionStatus(action: AssistantAction, status: AssistantAction['status'], error = ''): void {
  action.status = status;
  action.error = error;
  chatMessages.value = [...chatMessages.value];
  syncActiveAssistantThreadMessages();
  schedulePersistentDashboardStateSave();
}

async function executeAssistantAction(action: AssistantAction): Promise<void> {
  if (assistantExecutingActionId.value || action.status === 'executed' || action.status === 'canceled') {
    return;
  }
  assistantExecutingActionId.value = action.id;
  let completedStatus: AssistantAction['status'] = 'executed';
  try {
    if (action.payload._assistant_v2 === true) {
      const decided = await decideSharedAssistantAction(action.id, 'confirm');
      if (!['confirmed', 'executed'].includes(decided.state)) {
        throw new UserFacingError(actionPayloadErrorText(decided.payload, '后端没有接受这次确认，请重新发起操作。'));
      }
      const decidedWaterGun = decided.payload.water_gun;
      if (action.type === 'water_gun_target' && decidedWaterGun && typeof decidedWaterGun === 'object') {
        syncWaterGunState(decidedWaterGun as WaterGunState);
      }
      completedStatus = decided.state === 'executed' ? 'executed' : 'confirmed';
      await refreshSiteSnapshot();
    } else if (action.type === 'navigate_view') {
      const view = actionPayloadText(action, 'view');
      if (!isViewKey(view)) {
        throw new Error('未知页面');
      }
      activeView.value = view;
    } else if (action.type === 'open_panel') {
      const panel = actionPayloadText(action, 'panel');
      if (panel === 'smart_control') {
        activeView.value = 'control';
      } else if (panel === 'knowledge') {
        activeView.value = 'knowledge';
      } else if (panel === 'disease_upload') {
        activeView.value = 'disease';
      } else {
        assistantOpen.value = true;
      }
    } else if (action.type === 'refresh_data') {
      await loadDashboard(true);
    } else if (action.type === 'knowledge_base') {
      activeView.value = 'knowledge';
      const operation = actionPayloadText(action, 'operation');
      const kbId = actionPayloadNumber(action, 'kbId', selectedKbId.value);
      if (operation === 'create') {
        const saved = await createKnowledgeBase(actionPayloadText(action, 'name'), actionPayloadText(action, 'description'));
        await refreshKnowledge(saved.kbId);
      } else if (operation === 'update') {
        await updateKnowledgeBase(kbId, actionPayloadText(action, 'name'), actionPayloadText(action, 'description'));
        await refreshKnowledge(kbId);
      } else if (operation === 'delete') {
        await deleteKnowledgeBase(kbId);
        await refreshKnowledge();
      } else if (operation === 'select') {
        await selectKnowledgeBase(kbId);
      } else {
        throw new Error('未知知识库操作');
      }
    } else if (action.type === 'knowledge_item') {
      activeView.value = 'knowledge';
      const operation = actionPayloadText(action, 'operation');
      const kbId = actionPayloadNumber(action, 'kbId', selectedKbId.value);
      const itemId = actionPayloadNumber(action, 'itemId');
      if (kbId > 0 && selectedKbId.value !== kbId) {
        await selectKnowledgeBase(kbId);
      }
      if (operation === 'create') {
        await addKnowledgeItem(kbId, actionPayloadText(action, 'title'), actionPayloadText(action, 'content'));
        knowledgeItems.value = await getKnowledgeItems(kbId);
      } else if (operation === 'update') {
        await updateKnowledgeItem(kbId, itemId, actionPayloadText(action, 'title'), actionPayloadText(action, 'content'));
        knowledgeItems.value = await getKnowledgeItems(kbId);
      } else if (operation === 'delete') {
        await deleteKnowledgeItem(kbId, itemId);
        knowledgeItems.value = await getKnowledgeItems(kbId);
      } else if (operation === 'select') {
        const item = knowledgeItems.value.find((entry) => entry.itemId === itemId);
        if (item) {
          beginEditKnowledgeItem(item);
        }
      } else {
        throw new Error('未知知识条目操作');
      }
    } else if (action.type === 'run_knowledge_analysis') {
      activeView.value = 'knowledge';
      const kbId = actionPayloadNumber(action, 'kbId', selectedKbId.value);
      if (kbId > 0 && selectedKbId.value !== kbId) {
        await selectKnowledgeBase(kbId);
      }
      const question = actionPayloadText(action, 'question');
      if (question.length > 0) {
        knowledgeQuestion.value = question;
      }
      await runKnowledgeAnalysis();
    }
    setAssistantActionStatus(action, completedStatus);
  } catch (error) {
    console.warn('Assistant action failed.', error);
    setAssistantActionStatus(action, 'failed', assistantActionErrorText(error, '操作没有完成，请稍后重试。'));
  } finally {
    assistantExecutingActionId.value = null;
    if (action.payload._assistant_v2 === true) {
      void refreshSharedAssistantConversation();
      void loadWaterGunControlState();
    }
  }
}

async function confirmAssistantAction(action: AssistantAction): Promise<void> {
  if (action.status !== 'pending' && action.status !== 'failed' && action.status !== undefined) {
    return;
  }
  await executeAssistantAction(action);
}

async function cancelAssistantAction(action: AssistantAction): Promise<void> {
  if (action.payload._assistant_v2 === true) {
    try {
      const decided = await decideSharedAssistantAction(action.id, 'cancel');
      const decidedWaterGun = decided.payload.water_gun;
      if (action.type === 'water_gun_target' && decidedWaterGun && typeof decidedWaterGun === 'object') {
        syncWaterGunState(decidedWaterGun as WaterGunState);
      }
    } catch (error) {
      setAssistantActionStatus(action, 'failed', assistantActionErrorText(error, '取消操作没有完成，请稍后重试。'));
      return;
    } finally {
      void refreshSharedAssistantConversation();
      void loadWaterGunControlState();
    }
  }
  setAssistantActionStatus(action, 'canceled');
}

async function selectAssistantReplyChoice(action: AssistantAction): Promise<void> {
  if (chatSending.value || assistantExecutingActionId.value || action.type !== 'reply_choice') {
    return;
  }
  const reply = actionPayloadText(action, 'reply');
  if (!reply) {
    setAssistantActionStatus(action, 'failed', '这个选项缺少可发送内容。');
    return;
  }
  assistantExecutingActionId.value = action.id;
  try {
    if (action.payload._assistant_v2 === true) {
      const decided = await decideSharedAssistantAction(action.id, 'confirm');
      if (decided.state !== 'executed') {
        throw new Error('后端没有接受这个选项。');
      }
    }
    resolveAssistantChoiceGroup(action);
    chatInput.value = reply;
    await nextTick(resizeChatInput);
  } catch (error) {
    setAssistantActionStatus(action, 'failed', assistantActionErrorText(error, '选项没有提交，请重新选择。'));
    return;
  } finally {
    assistantExecutingActionId.value = null;
  }
  await sendChat();
}

function errorText(error: unknown): string {
  return userErrorText(error);
}

function imageFileValidationError(file: File): string {
  const extension = file.name.split('.').pop()?.toLowerCase() ?? '';
  const allowedByExtension = ['jpg', 'jpeg', 'png', 'webp'].includes(extension);
  if (!allowedUploadImageTypes.has(file.type.toLowerCase()) && !allowedByExtension) {
    return '只支持 JPG、PNG、WebP 图片。';
  }
  if (file.size > maxUploadImageBytes) {
    return '图片不能超过 10MB。';
  }
  return '';
}

function droppedSingleFile(event: DragEvent): File | null {
  const files = Array.from(event.dataTransfer?.files ?? []);
  return files.length === 1 ? files[0] : null;
}

function isFileDrag(event: DragEvent): boolean {
  return Array.from(event.dataTransfer?.types ?? []).includes('Files');
}

function handleImageDragOver(event: DragEvent): void {
  if (event.dataTransfer) {
    event.dataTransfer.dropEffect = 'copy';
  }
}

function handleDiseaseDragEnter(event: DragEvent): void {
  if (!isFileDrag(event)) {
    return;
  }
  diseaseDragDepth += 1;
  diseaseDragActive.value = true;
}

function handleDiseaseDragLeave(): void {
  diseaseDragDepth = Math.max(0, diseaseDragDepth - 1);
  if (diseaseDragDepth === 0) {
    diseaseDragActive.value = false;
  }
}

async function handleDiseaseDrop(event: DragEvent): Promise<void> {
  diseaseDragDepth = 0;
  diseaseDragActive.value = false;
  const file = droppedSingleFile(event);
  if (!file) {
    diseaseUploadError.value = '一次只能拖入一张图片。';
    return;
  }
  await acceptDiseaseFile(file);
}

function handleChatDragEnter(event: DragEvent): void {
  if (!isFileDrag(event)) {
    return;
  }
  chatDragDepth += 1;
  chatDragActive.value = true;
}

function handleChatDragLeave(): void {
  chatDragDepth = Math.max(0, chatDragDepth - 1);
  if (chatDragDepth === 0) {
    chatDragActive.value = false;
  }
}

function handleChatDrop(event: DragEvent): void {
  chatDragDepth = 0;
  chatDragActive.value = false;
  const file = droppedSingleFile(event);
  if (!file) {
    chatImageError.value = '一次只能拖入一张图片。';
    return;
  }
  attachChatImage(file);
}

function revokeCurrentDiseaseBlob(): void {
  if (diseaseImageUrl.value.startsWith('blob:')) {
    URL.revokeObjectURL(diseaseImageUrl.value);
  }
}

function diseasePhotoDateKey(createdAt: string): string {
  const key = createdAt.slice(0, 10);
  return /^\d{4}-\d{2}-\d{2}$/.test(key) ? key : 'unknown';
}

function diseasePhotoDateLabel(dateKey: string): string {
  if (dateKey === 'unknown') {
    return '未知日期';
  }
  const [year, month, day] = dateKey.split('-').map((item) => Number(item));
  return `${year}年${month}月${day}日`;
}

function diseasePhotoTimeLabel(createdAt: string): string {
  return createdAt.length > 10 ? createdAt.slice(11) : createdAt;
}

function diseasePhotoSizeLabel(size: number): string {
  if (!Number.isFinite(size) || size <= 0) {
    return '未知大小';
  }
  if (size >= 1024 * 1024) {
    return `${(size / 1024 / 1024).toFixed(1)} MB`;
  }
  return `${Math.max(1, Math.round(size / 1024))} KB`;
}

function diseasePhotoAnalysis(photo: DiseasePhotoInfo | null): DiseaseDetectionResult | null {
  if (!photo?.analysisResult || typeof photo.analysisResult !== 'object') {
    return null;
  }
  return photo.analysisResult;
}

function upsertDiseasePhoto(photo: DiseasePhotoInfo): void {
  const index = diseasePhotos.value.findIndex((item) => item.photoId === photo.photoId);
  if (index >= 0) {
    diseasePhotos.value = [
      ...diseasePhotos.value.slice(0, index),
      photo,
      ...diseasePhotos.value.slice(index + 1),
    ];
    return;
  }
  diseasePhotos.value = [photo, ...diseasePhotos.value];
}

async function refreshDiseasePhotoLibrary(): Promise<void> {
  diseasePhotoLoading.value = true;
  try {
    diseasePhotos.value = await getDiseasePhotos();
    diseasePhotoError.value = '';
    if (selectedDiseasePhoto.value) {
      selectedDiseasePhoto.value = diseasePhotos.value.find((photo) => photo.photoId === selectedDiseasePhoto.value?.photoId) ?? null;
    }
  } catch (error) {
    diseasePhotoError.value = `读取图片库失败：${errorText(error)}`;
  } finally {
    diseasePhotoLoading.value = false;
  }
}

async function openDiseasePhotoLibrary(): Promise<void> {
  diseasePhotoLibraryOpen.value = true;
  selectedDiseasePhoto.value = null;
  await refreshDiseasePhotoLibrary();
}

function closeDiseasePhotoLibrary(): void {
  diseasePhotoLibraryOpen.value = false;
  selectedDiseasePhoto.value = null;
}

function selectDiseasePhoto(photo: DiseasePhotoInfo): void {
  selectedDiseasePhoto.value = photo;
  selectedDiseasePhotoImageError.value = false;
  currentDiseasePhotoId.value = photo.photoId;
  revokeCurrentDiseaseBlob();
  diseaseImageUrl.value = photo.url;
  diseaseImageLoadError.value = false;
  diseaseResult.value = diseasePhotoAnalysis(photo);
  diseaseUploadError.value = diseaseResult.value ? '' : '这张图片还没有保存识别结果，可以重新上传或重新分析后保存。';
}

async function processDiseaseFile(file: File): Promise<void> {
  revokeCurrentDiseaseBlob();
  const previewUrl = URL.createObjectURL(file);
  diseaseImageUrl.value = previewUrl;
  diseaseImageLoadError.value = false;
  diseaseResult.value = null;
  currentDiseasePhotoId.value = null;
  diseaseUploadError.value = '';
  diseaseLoading.value = true;

  let uploadedPhoto: DiseasePhotoInfo | null = null;
  try {
    try {
      uploadedPhoto = await uploadDiseasePhoto(file);
      upsertDiseasePhoto(uploadedPhoto);
      currentDiseasePhotoId.value = uploadedPhoto.photoId;
      diseaseImageUrl.value = uploadedPhoto.url;
      URL.revokeObjectURL(previewUrl);
    } catch (error) {
      diseaseUploadError.value = `图片保存到后端失败：${errorText(error)}。当前只显示临时预览，刷新后不会保留。`;
      console.warn('Disease photo upload failed.', error);
    }

    const analysisImageUrl = uploadedPhoto?.url ?? previewUrl;
    const result = {
      ...await analyzeDiseaseImage(file, analysisImageUrl),
      image_url: analysisImageUrl,
    };
    diseaseResult.value = result;

    if (uploadedPhoto) {
      const savedPhoto = await saveDiseasePhotoAnalysis(uploadedPhoto.photoId, result);
      upsertDiseasePhoto(savedPhoto);
      selectedDiseasePhoto.value = selectedDiseasePhoto.value?.photoId === savedPhoto.photoId ? savedPhoto : selectedDiseasePhoto.value;
      diseasePhotoError.value = '';
    }
  } catch (error) {
    diseaseUploadError.value = `病害识别失败：${errorText(error)}`;
  } finally {
    diseaseLoading.value = false;
  }
}

async function acceptDiseaseFile(file: File): Promise<void> {
  const validationError = imageFileValidationError(file);
  if (validationError) {
    diseaseUploadError.value = validationError;
    return;
  }
  await processDiseaseFile(file);
}

function clipboardImageExtension(type: string): string {
  if (type === 'image/jpeg') {
    return 'jpg';
  }
  if (type === 'image/webp') {
    return 'webp';
  }
  return 'png';
}

async function pasteDiseaseImage(): Promise<void> {
  diseaseUploadError.value = '';
  if (!window.isSecureContext || !navigator.clipboard || typeof navigator.clipboard.read !== 'function') {
    diseaseUploadError.value = '当前浏览器无法直接读取剪贴板图片，请改用选择图片或拖入图片。';
    return;
  }

  try {
    const items = await navigator.clipboard.read();
    for (const item of items) {
      const imageType = item.types.find((type) => allowedUploadImageTypes.has(type.toLowerCase()));
      if (!imageType) {
        continue;
      }
      const blob = await item.getType(imageType);
      const extension = clipboardImageExtension(blob.type || imageType);
      const file = new File([blob], `clipboard-image-${Date.now()}.${extension}`, {
        type: blob.type || imageType,
      });
      await acceptDiseaseFile(file);
      return;
    }
    throw new UserFacingError('剪贴板中没有可用图片，请先复制一张图片或截取屏幕。');
  } catch (error) {
    console.warn('Clipboard image read failed.', error);
    diseaseUploadError.value = userErrorText(
      error,
      '没有读取到剪贴板图片，请允许剪贴板权限，或改用选择图片。',
    );
  }
}

async function handleDiseaseUpload(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) {
    return;
  }
  try {
    await acceptDiseaseFile(file);
  } finally {
    input.value = '';
  }
}

function clearDiseaseImage(): void {
  revokeCurrentDiseaseBlob();
  diseaseImageUrl.value = '';
  diseaseImageLoadError.value = false;
  diseaseResult.value = null;
  currentDiseasePhotoId.value = null;
  diseaseUploadError.value = '';
}

async function removeDiseasePhoto(photo: DiseasePhotoInfo): Promise<void> {
  const confirmed = window.confirm(`确定删除这张图片吗？\n${photo.originalName || '未命名图片'}\n删除后本地图片文件和识别结果都会移除。`);
  if (!confirmed) {
    return;
  }
  diseasePhotoDeletingId.value = photo.photoId;
  try {
    await deleteDiseasePhoto(photo.photoId);
    diseasePhotos.value = diseasePhotos.value.filter((item) => item.photoId !== photo.photoId);
    if (selectedDiseasePhoto.value?.photoId === photo.photoId) {
      selectedDiseasePhoto.value = null;
    }
    if (currentDiseasePhotoId.value === photo.photoId) {
      clearDiseaseImage();
    }
    diseasePhotoError.value = '';
  } catch (error) {
    diseasePhotoError.value = `删除图片失败：${errorText(error)}`;
  } finally {
    diseasePhotoDeletingId.value = null;
  }
}

function attachChatImage(file: File): void {
  const validationError = imageFileValidationError(file);
  if (validationError) {
    chatImageError.value = validationError;
    return;
  }
  if (chatImageUrl.value.startsWith('blob:')) {
    URL.revokeObjectURL(chatImageUrl.value);
  }
  chatImageUrl.value = URL.createObjectURL(file);
  chatImageFileName.value = file.name;
  chatImageFile.value = file;
  chatImageError.value = '';
}

function handleChatImageUpload(event: Event): void {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  if (file) {
    attachChatImage(file);
  }
  input.value = '';
}

function clearChatImage(): void {
  if (chatImageUrl.value.startsWith('blob:')) {
    URL.revokeObjectURL(chatImageUrl.value);
  }
  chatImageUrl.value = '';
  chatImageFileName.value = '';
  chatImageFile.value = null;
  chatImageError.value = '';
}

function isAssistantMessagesAtBottom(element: HTMLElement): boolean {
  return element.scrollHeight - element.scrollTop - element.clientHeight <= 40;
}

function updateAssistantScrollState(): void {
  const element = assistantMessagesRef.value;
  if (!element) {
    assistantAtBottom.value = true;
    assistantShowScrollButton.value = false;
    return;
  }
  const atBottom = isAssistantMessagesAtBottom(element);
  assistantAtBottom.value = atBottom;
  assistantShowScrollButton.value = !atBottom;
}

async function scrollAssistantToBottom(smooth = false): Promise<void> {
  await nextTick();
  const element = assistantMessagesRef.value;
  if (!element) {
    return;
  }
  element.scrollTo({
    top: element.scrollHeight,
    behavior: smooth ? 'smooth' : 'auto',
  });
  window.requestAnimationFrame(updateAssistantScrollState);
}

function handleAssistantMessagesScroll(): void {
  updateAssistantScrollState();
}

function resetAssistantThreadRename(): void {
  renamingAssistantThreadId.value = '';
  assistantThreadNameDraft.value = '';
}

function createNewAssistantThread(): void {
  if (chatSending.value) {
    return;
  }
  syncActiveAssistantThreadMessages();
  const activeThread = assistantThreads.value.find((thread) => thread.id === activeAssistantThreadId.value);
  const activeMessages = activeThread?.messages ?? chatMessages.value;
  if (!assistantThreadHasConversationContent(activeMessages)) {
    assistantHistoryOpen.value = false;
    resetAssistantThreadRename();
    void scrollAssistantToBottom();
    void nextTick(resizeChatInput);
    return;
  }
  clearChatImage();
  const thread = createAssistantThread();
  assistantThreads.value = [thread, ...assistantThreads.value];
  activeAssistantThreadId.value = thread.id;
  chatMessages.value = thread.messages;
  assistantHistoryOpen.value = false;
  resetAssistantThreadRename();
  void scrollAssistantToBottom();
  void nextTick(resizeChatInput);
  schedulePersistentDashboardStateSave();
}

function switchAssistantThread(threadId: string): void {
  if (chatSending.value || threadId === activeAssistantThreadId.value) {
    assistantHistoryOpen.value = false;
    return;
  }
  const thread = assistantThreads.value.find((item) => item.id === threadId);
  if (!thread) {
    return;
  }
  syncActiveAssistantThreadMessages();
  clearChatImage();
  activeAssistantThreadId.value = thread.id;
  chatMessages.value = thread.messages.length > 0 ? thread.messages : [createAssistantWelcomeMessage()];
  assistantHistoryOpen.value = false;
  resetAssistantThreadRename();
  void scrollAssistantToBottom();
  schedulePersistentDashboardStateSave();
}

function beginRenameAssistantThread(thread: AssistantThread): void {
  renamingAssistantThreadId.value = thread.id;
  assistantThreadNameDraft.value = thread.title;
}

function commitRenameAssistantThread(threadId: string): void {
  const title = assistantThreadNameDraft.value.trim();
  if (!title) {
    return;
  }
  assistantThreads.value = assistantThreads.value.map((thread) => (
    thread.id === threadId ? { ...thread, title } : thread
  ));
  resetAssistantThreadRename();
  schedulePersistentDashboardStateSave();
}

function toggleAssistantThreadPinned(threadId: string): void {
  assistantThreads.value = assistantThreads.value.map((thread) => (
    thread.id === threadId ? { ...thread, pinned: !thread.pinned, updated_at: Date.now() } : thread
  ));
  schedulePersistentDashboardStateSave();
}

function deleteAssistantThread(threadId: string): void {
  if (chatSending.value) {
    return;
  }
  const nextThreads = assistantThreads.value.filter((thread) => thread.id !== threadId);
  if (nextThreads.length === 0) {
    const thread = createAssistantThread();
    assistantThreads.value = [thread];
    activeAssistantThreadId.value = thread.id;
    chatMessages.value = thread.messages;
  } else {
    assistantThreads.value = nextThreads;
    if (threadId === activeAssistantThreadId.value) {
      const nextActiveThread = [...nextThreads].sort((left, right) => {
        if (left.pinned !== right.pinned) {
          return left.pinned ? -1 : 1;
        }
        return right.updated_at - left.updated_at;
      })[0];
      activeAssistantThreadId.value = nextActiveThread.id;
      chatMessages.value = nextActiveThread.messages.length > 0 ? nextActiveThread.messages : [createAssistantWelcomeMessage()];
    }
  }
  resetAssistantThreadRename();
  void scrollAssistantToBottom();
  schedulePersistentDashboardStateSave();
}

function resizeChatInput(): void {
  const input = chatInputRef.value;
  if (!input) {
    return;
  }
  input.style.height = 'auto';
  const nextHeight = Math.min(input.scrollHeight, 154);
  input.style.height = `${nextHeight}px`;
  input.style.overflowY = input.scrollHeight > 154 ? 'auto' : 'hidden';
}

function waitForAssistantTyping(ms: number): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

function updateChatMessage(messageId: string, patch: Partial<ChatMessage>): void {
  chatMessages.value = chatMessages.value.map((message) => (
    message.id === messageId ? { ...message, ...patch } : message
  ));
}

function replaceChatMessage(messageId: string, nextMessage: ChatMessage): void {
  const index = chatMessages.value.findIndex((message) => message.id === messageId);
  if (index < 0) {
    chatMessages.value = [...chatMessages.value, nextMessage];
    return;
  }
  chatMessages.value = [
    ...chatMessages.value.slice(0, index),
    nextMessage,
    ...chatMessages.value.slice(index + 1),
  ];
}

function stopAssistantThinking(): void {
  if (assistantThinkingTimer !== undefined) {
    window.clearInterval(assistantThinkingTimer);
    assistantThinkingTimer = undefined;
  }
}

function startAssistantThinking(messageId: string): void {
  stopAssistantThinking();
  let dotCount = 0;
  assistantThinkingTimer = window.setInterval(() => {
    dotCount = dotCount >= 3 ? 1 : dotCount + 1;
    updateChatMessage(messageId, { content: '。'.repeat(dotCount) });
  }, 360);
}

async function revealAssistantMessage(finalMessage: ChatMessage, replaceMessageId: string, shouldFollow: boolean): Promise<void> {
  stopAssistantThinking();
  const runId = ++assistantTypeRunId;
  const chars = Array.from(finalMessage.content);
  const step = chars.length > 360 ? 6 : chars.length > 180 ? 4 : 2;
  const draftMessage: ChatMessage = {
    ...finalMessage,
    content: '',
    references: undefined,
    suggested_actions: undefined,
    suggested_commands: undefined,
    typing: true,
  };
  replaceChatMessage(replaceMessageId, draftMessage);

  let index = 0;
  while (index < chars.length) {
    if (runId !== assistantTypeRunId) {
      return;
    }
    index = Math.min(index + step, chars.length);
    updateChatMessage(finalMessage.id, { content: chars.slice(0, index).join('') });
    if (shouldFollow && assistantAtBottom.value) {
      await scrollAssistantToBottom();
    } else {
      await nextTick();
      updateAssistantScrollState();
    }
    await waitForAssistantTyping(22);
  }

  if (runId !== assistantTypeRunId) {
    return;
  }
  replaceChatMessage(finalMessage.id, { ...finalMessage, typing: false });
  syncActiveAssistantThreadMessages();
  if (shouldFollow && assistantAtBottom.value) {
    await scrollAssistantToBottom();
  } else {
    await nextTick();
    updateAssistantScrollState();
  }
  schedulePersistentDashboardStateSave();
}

function handleChatKeydown(event: KeyboardEvent): void {
  if (event.key !== 'Enter' || event.shiftKey || event.isComposing) {
    return;
  }
  event.preventDefault();
  void sendChat();
}

function clearChatComposerInput(): void {
  chatInput.value = '';
  voiceInputPrefix = '';
  voiceInputSuffix = '';
  voiceCurrentTranscript = '';
  void nextTick(resizeChatInput);
}

function stopVoiceInputAfterSend(): void {
  if (!listening.value && !activeBrowserSpeechRecognition) {
    return;
  }
  stopBrowserSpeechInput();
  listening.value = false;
  voiceRecognitionHadError = false;
  voiceMessage.value = '语音输入已随消息发送停止';
}

async function openAssistantPreferences(): Promise<void> {
  assistantPreferencesOpen.value = true;
  assistantPreferencesLoading.value = true;
  try {
    assistantPreferences.value = await getAssistantPreferences();
  } catch (error) {
    console.warn('Assistant preferences could not be loaded.', error);
  } finally {
    assistantPreferencesLoading.value = false;
  }
}

async function removeAssistantPreference(key: string): Promise<void> {
  assistantPreferencesLoading.value = true;
  try {
    assistantPreferences.value = await deleteAssistantPreference(key);
  } catch (error) {
    console.warn('Assistant preference could not be removed.', error);
  } finally {
    assistantPreferencesLoading.value = false;
  }
}

async function sendChat(): Promise<void> {
  if (!latest.value || chatSending.value) {
    return;
  }
  const question = chatInput.value.trim();
  if (question.length === 0 && chatImageUrl.value.length === 0) {
    return;
  }
  const pendingImageUrl = chatImageUrl.value;
  const pendingImageFile = chatImageFile.value;
  const useAssistantV2 = !pendingImageFile && !pendingImageUrl;
  const seedHistory = chatMessages.value
    .filter((message) => !message.typing && message.content.trim().length > 0)
    .slice(-30)
    .map((message) => ({
      id: message.id.slice(0, 80),
      role: message.role,
      content: message.content.slice(0, 2000),
      created_at: message.created_at,
    }));
  const pendingPosition = pendingPositionSelection();
  const pendingTargetLabel = pendingPositionTargetLabel();
  const positionRefinement = isPositionRefinement(question, pendingPosition);
  const positionQuestion = !useAssistantV2 && (isPositionQuestion(question) || positionRefinement);
  if (!positionQuestion) {
    positionSelectionSession.value = null;
  }
  const realtimePositionFrame = positionQuestion ? await cameraGrowthPanelRef.value?.captureCurrentFrame() : null;
  const messageImageFile = realtimePositionFrame ?? pendingImageFile;
  const messageImageUrl = messageImageFile ? URL.createObjectURL(messageImageFile) : pendingImageUrl;
  stopVoiceInputAfterSend();
  clearChatComposerInput();
  const userMessage: ChatMessage = {
    id: `user-${Date.now()}`,
    role: 'user',
    content: question || '请分析这张作物图片。',
    image_url: messageImageUrl || undefined,
    created_at: Date.now(),
  };
  if (messageImageUrl.startsWith('blob:')) {
    sentChatImageUrls.add(messageImageUrl);
  }
  const thinkingMessage: ChatMessage = {
    id: `assistant-thinking-${Date.now()}`,
    role: 'assistant',
    content: '。。。',
    created_at: Date.now(),
    typing: true,
  };
  chatMessages.value = [...chatMessages.value, userMessage, thinkingMessage];
  syncActiveAssistantThreadMessages(true);
  schedulePersistentDashboardStateSave();
  await scrollAssistantToBottom();
  startAssistantThinking(thinkingMessage.id);
  chatSending.value = true;
  try {
    if (useAssistantV2) {
      chatSendingStage.value = 'chat';
      stopAssistantThinking();
      updateChatMessage(thinkingMessage.id, { content: '正在结合当前对话理解你的意思…' });
      const accepted = await createAssistantTurn({
        session_id: activeAssistantThreadId.value,
        site_id: defaultSiteId,
        channel: 'web',
        message_id: userMessage.id,
        text: userMessage.content,
        seed_history: seedHistory,
      });
      const response = await streamAssistantTurn(accepted.turn_id, (progressText) => {
        stopAssistantThinking();
        updateChatMessage(thinkingMessage.id, { content: progressText });
      });
      const resolvedAction = response.message.context?.resolved_action;
      if (isPlainRecord(resolvedAction)) {
        syncAssistantV2ActionState(
          String(resolvedAction.id ?? ''),
          String(resolvedAction.state ?? ''),
          isPlainRecord(resolvedAction.payload) ? resolvedAction.payload : {},
        );
      }
      const contextPosition = response.message.context?.position_result as PositionLocateResult | undefined;
      const v2Actions = (response.actions ?? response.message.suggested_actions ?? []).map((action) => ({
        ...action,
        payload: { ...action.payload, _assistant_v2: true },
      }));
      const shouldFollowResponse = assistantAtBottom.value;
      await revealAssistantMessage(
        {
          ...response.message,
          referencesVerified: true,
          suggested_actions: v2Actions,
          position_result: contextPosition,
        },
        thinkingMessage.id,
        shouldFollowResponse,
      );
      clearChatImage();
      return;
    }
    if (positionQuestion) {
      if (!realtimePositionFrame) {
        throw new Error('无法获取实时摄像头画面，请先进入总览页并确认摄像头已连接。');
      }
      chatSendingStage.value = 'vision';
      stopAssistantThinking();
      updateChatMessage(thinkingMessage.id, { content: '正在识别当前画面并计算位置…' });
      const locatorQuestion = positionRefinement && pendingTargetLabel
        ? `这是对上一轮 ${pendingPosition?.candidates.length ?? 0} 个“${pendingTargetLabel}”候选的继续筛选。`
          + `用户本轮描述是：“${userMessage.content}”。请比较画面中的同类候选，只返回符合本轮颜色、材质、形状、大小或相对位置描述的目标。`
        : userMessage.content;
      const positionResult = await locateCameraObject(realtimePositionFrame, locatorQuestion, normalizedCameraPositionConfig());
      if (!positionRefinement) {
        positionSelectionSession.value = positionResult.status === 'multiple' ? positionResult : null;
      }
      const shouldFollowResponse = assistantAtBottom.value;
      await revealAssistantMessage(
        {
          id: `assistant-position-${Date.now()}`,
          role: 'assistant',
          content: formatPositionReply(positionResult),
          created_at: Date.now(),
          position_result: positionResult,
        },
        thinkingMessage.id,
        shouldFollowResponse,
      );
      clearChatImage();
      return;
    }
    let chatDiseaseContext = diseaseResult.value;
    if (pendingImageFile) {
      chatSendingStage.value = 'vision';
      stopAssistantThinking();
      updateChatMessage(thinkingMessage.id, { content: '正在识别图片，请稍候…' });
      chatDiseaseContext = await analyzeDiseaseImage(pendingImageFile, pendingImageUrl);
    }
    chatSendingStage.value = 'chat';
    updateChatMessage(thinkingMessage.id, { content: '正在结合识别结果生成回答…' });
    startAssistantThinking(thinkingMessage.id);
    const response = await sendExpertChatMessage({
      question: userMessage.content,
      image_url: pendingImageUrl || undefined,
      latest: latest.value,
      disease: chatDiseaseContext,
      weather: currentWeather.value,
      weather_bundle: weatherBundle.value,
      ai_analysis: aiAnalysis.value,
      camera_analysis: cameraAnalysisResult.value,
      knowledge_base_id: selectedKbId.value || undefined,
      current_view: activeView.value,
      knowledge_bases: knowledgeBases.value,
      knowledge_items: knowledgeItems.value,
      retrieval_mode: 'auto',
    });
    const shouldFollowResponse = assistantAtBottom.value;
    await revealAssistantMessage(
      { ...response.message, referencesVerified: true },
      thinkingMessage.id,
      shouldFollowResponse,
    );
    clearChatImage();
  } catch (error) {
    const shouldFollowResponse = assistantAtBottom.value;
    const failureContent = chatSendingStage.value === 'vision'
      ? `图片识别没有完成：${userErrorText(error, '请确认摄像头和视觉识别服务均已连接，然后重试。')}`
      : '智能助手暂时无法回答，请稍后重试；如持续无法使用，请联系平台管理员。';
    await revealAssistantMessage(
      {
        id: `assistant-error-${Date.now()}`,
        role: 'assistant',
        content: failureContent,
        created_at: Date.now(),
      },
      thinkingMessage.id,
      shouldFollowResponse,
    );
  } finally {
    stopAssistantThinking();
    chatSending.value = false;
    chatSendingStage.value = 'idle';
    schedulePersistentDashboardStateSave();
  }
}

function setChatInputFromVoice(transcript: string): void {
  chatInput.value = `${voiceInputPrefix}${transcript}${voiceInputSuffix}`;
  void nextTick(() => {
    const input = chatInputRef.value;
    if (!input) {
      return;
    }
    resizeChatInput();
    const caretPosition = voiceInputPrefix.length + transcript.length;
    // Writing a recognition result needs to keep the caret visible. This focus
    // is programmatic, though, so it must not be treated as the user choosing
    // to edit the composer and stopping the active recognition session.
    applyingVoiceTranscriptFocus = true;
    try {
      input.focus();
    } finally {
      applyingVoiceTranscriptFocus = false;
    }
    input.setSelectionRange(caretPosition, caretPosition);
  });
}

function getBrowserSpeechRecognition(): SpeechRecognitionConstructor | null {
  const speechWindow = window as Window & {
    SpeechRecognition?: SpeechRecognitionConstructor;
    webkitSpeechRecognition?: SpeechRecognitionConstructor;
  };
  return speechWindow.SpeechRecognition ?? speechWindow.webkitSpeechRecognition ?? null;
}

function clearVoiceSilenceStopTimer(): void {
  if (voiceSilenceStopTimer !== undefined) {
    window.clearTimeout(voiceSilenceStopTimer);
    voiceSilenceStopTimer = undefined;
  }
}

function stopVoiceInputForSilence(): void {
  if (!listening.value && !activeBrowserSpeechRecognition) {
    return;
  }
  stopBrowserSpeechInput();
  listening.value = false;
  voiceRecognitionHadError = false;
  voiceMessage.value = '连续静音 3 秒，语音输入已自动停止';
}

function scheduleVoiceSilenceStop(): void {
  clearVoiceSilenceStopTimer();
  if (!listening.value || !activeBrowserSpeechRecognition) {
    return;
  }
  voiceSilenceStopTimer = window.setTimeout(() => {
    voiceSilenceStopTimer = undefined;
    stopVoiceInputForSilence();
  }, voiceSilenceStopDelayMs);
}

function stopBrowserSpeechInput(): void {
  clearVoiceSilenceStopTimer();
  voiceSpeechActive = false;
  const recognition = activeBrowserSpeechRecognition;
  activeBrowserSpeechRecognition = null;
  if (!recognition) {
    return;
  }
  recognition.onstart = null;
  recognition.onspeechstart = null;
  recognition.onspeechend = null;
  recognition.onresult = null;
  recognition.onerror = null;
  recognition.onend = null;
  recognition.stop();
}

function startBrowserSpeechInput(): boolean {
  const Recognition = getBrowserSpeechRecognition();
  if (!Recognition) {
    voiceMessage.value = '当前浏览器不支持实时语音输入，请使用 Chrome/Edge 或手动输入。';
    listening.value = false;
    return false;
  }

  const recognition = new Recognition();
  voiceRecognitionHadError = false;
  activeBrowserSpeechRecognition = recognition;
  recognition.lang = 'zh-CN';
  recognition.continuous = true;
  recognition.interimResults = true;
  recognition.maxAlternatives = 1;
  recognition.onstart = () => {
    voiceSpeechActive = false;
    scheduleVoiceSilenceStop();
  };
  recognition.onspeechstart = () => {
    voiceSpeechActive = true;
    clearVoiceSilenceStopTimer();
  };
  recognition.onspeechend = () => {
    voiceSpeechActive = false;
    scheduleVoiceSilenceStop();
  };
  recognition.onresult = (event) => {
    let transcript = '';
    for (let index = 0; index < event.results.length; index += 1) {
      transcript += event.results[index][0]?.transcript ?? '';
    }
    const cleanTranscript = transcript.trim();
    if (cleanTranscript) {
      voiceCurrentTranscript = cleanTranscript;
      setChatInputFromVoice(cleanTranscript);
      voiceMessage.value = '正在使用浏览器实时语音输入，文字已同步到输入框';
    }
    if (!voiceSpeechActive) {
      // Fallback for browsers that do not emit speech boundary events.
      scheduleVoiceSilenceStop();
    }
  };
  recognition.onerror = () => {
    clearVoiceSilenceStopTimer();
    voiceRecognitionHadError = true;
    voiceMessage.value = '浏览器语音输入失败，请检查麦克风权限或输入设备。';
    listening.value = false;
    activeBrowserSpeechRecognition = null;
  };
  recognition.onend = () => {
    clearVoiceSilenceStopTimer();
    voiceSpeechActive = false;
    listening.value = false;
    activeBrowserSpeechRecognition = null;
    if (voiceRecognitionHadError) {
      return;
    }
    voiceMessage.value = voiceCurrentTranscript.trim().length > 0
      ? '语音已写入输入框'
      : '浏览器语音输入已结束，没有识别到有效文字';
  };

  try {
    recognition.start();
    listening.value = true;
    scheduleVoiceSilenceStop();
    voiceMessage.value = '正在启动浏览器实时语音输入...';
    return true;
  } catch (error) {
    console.warn('Browser speech input failed to start.', error);
    voiceMessage.value = userErrorText(error, '语音输入启动失败，请检查麦克风权限后重试。');
    activeBrowserSpeechRecognition = null;
    listening.value = false;
    return false;
  }
}

function stopVoiceInput(): void {
  if (activeBrowserSpeechRecognition) {
    stopBrowserSpeechInput();
    listening.value = false;
    voiceMessage.value = voiceCurrentTranscript.trim().length > 0 ? '语音已写入输入框' : '语音输入已停止';
    return;
  }
  listening.value = false;
  voiceMessage.value = '语音输入已停止';
}

function stopVoiceInputForTextEdit(): void {
  if (applyingVoiceTranscriptFocus) {
    return;
  }
  if (!listening.value && !activeBrowserSpeechRecognition) {
    return;
  }
  stopVoiceInput();
}

function prepareVoiceInputSession(): void {
  const input = chatInputRef.value;
  const selectionStart = input?.selectionStart ?? chatInput.value.length;
  const selectionEnd = input?.selectionEnd ?? chatInput.value.length;
  voiceInputPrefix = chatInput.value.slice(0, selectionStart);
  voiceInputSuffix = chatInput.value.slice(selectionEnd);
  voiceCurrentTranscript = '';
  voiceRecognitionHadError = false;
}

function startVoiceInput(): void {
  if (listening.value) {
    stopVoiceInput();
    return;
  }
  if (activeBrowserSpeechRecognition) {
    stopBrowserSpeechInput();
  }
  prepareVoiceInputSession();
  startBrowserSpeechInput();
}

async function selectKnowledgeBase(kbId: number): Promise<void> {
  try {
    selectedKbId.value = kbId;
    knowledgeItems.value = await getKnowledgeItems(kbId);
    knowledgeAnswer.value = null;
    knowledgeError.value = '';
    await savePersistentDashboardStateNow();
  } catch (error) {
    setKnowledgeError('切换知识库', error);
  }
}

function beginEditKnowledgeBase(item: KnowledgeBaseInfo): void {
  editingKbId.value = item.kbId;
  kbNameDraft.value = item.name;
  kbDescriptionDraft.value = item.description;
  knowledgeBaseDialogOpen.value = true;
}

function beginCreateKnowledgeBase(): void {
  editingKbId.value = 0;
  kbNameDraft.value = '';
  kbDescriptionDraft.value = '';
  knowledgeBaseDialogOpen.value = true;
}

function closeKnowledgeBaseDialog(): void {
  knowledgeBaseDialogOpen.value = false;
  editingKbId.value = 0;
  kbNameDraft.value = '番茄结果期管理';
  kbDescriptionDraft.value = '结果期水肥、光照、病害管理经验';
}

function beginEditKnowledgeItem(item: KnowledgeItemInfo): void {
  editingItemId.value = item.itemId;
  itemTitleDraft.value = item.title;
  itemContentDraft.value = item.content;
  knowledgeItemDialogOpen.value = true;
}

function beginCreateKnowledgeItem(): void {
  if (selectedKbId.value <= 0) {
    return;
  }
  editingItemId.value = 0;
  itemTitleDraft.value = '';
  itemContentDraft.value = '';
  knowledgeItemDialogOpen.value = true;
}

function closeKnowledgeItemDialog(): void {
  knowledgeItemDialogOpen.value = false;
  editingItemId.value = 0;
  itemTitleDraft.value = '番茄高湿病害风险';
  itemContentDraft.value = '番茄在高湿、通风不足时容易出现叶斑病和霜霉病，应先通风降湿并减少叶面结露。';
}

function confirmKnowledgeChange(message: string): boolean {
  return window.confirm(message);
}

async function saveKnowledgeBase(): Promise<void> {
  const name = kbNameDraft.value.trim();
  if (name.length === 0) {
    return;
  }
  const description = kbDescriptionDraft.value.trim();
  if (editingKbId.value > 0 && !confirmKnowledgeChange(`确认保存对知识库「${name}」的修改吗？`)) {
    return;
  }
  try {
    const saved = editingKbId.value > 0
      ? await updateKnowledgeBase(editingKbId.value, name, description)
      : await createKnowledgeBase(name, description);
    closeKnowledgeBaseDialog();
    await refreshKnowledge(saved.kbId);
    knowledgeError.value = '';
  } catch (error) {
    setKnowledgeError('保存知识库', error);
  }
}

async function removeKnowledgeBase(kbId: number): Promise<void> {
  const target = knowledgeBases.value.find((base) => base.kbId === kbId);
  const name = target?.name ?? '该知识库';
  if (!confirmKnowledgeChange(`确认删除知识库「${name}」吗？该知识库下的知识条目也会一起删除。`)) {
    return;
  }
  try {
    await deleteKnowledgeBase(kbId);
    if (editingKbId.value === kbId) {
      closeKnowledgeBaseDialog();
    }
    await refreshKnowledge();
    knowledgeError.value = '';
  } catch (error) {
    setKnowledgeError('删除知识库', error);
  }
}

async function saveKnowledgeItem(): Promise<void> {
  if (selectedKbId.value <= 0) {
    return;
  }
  const title = itemTitleDraft.value.trim();
  const content = itemContentDraft.value.trim();
  if (title.length === 0 || content.length === 0) {
    return;
  }
  if (editingItemId.value > 0 && !confirmKnowledgeChange(`确认保存对知识条目「${title}」的修改吗？`)) {
    return;
  }
  try {
    if (editingItemId.value > 0) {
      await updateKnowledgeItem(selectedKbId.value, editingItemId.value, title, content);
    } else {
      await addKnowledgeItem(selectedKbId.value, title, content);
    }
    closeKnowledgeItemDialog();
    knowledgeItems.value = await getKnowledgeItems(selectedKbId.value);
    knowledgeError.value = '';
  } catch (error) {
    setKnowledgeError('保存知识条目', error);
  }
}

async function removeKnowledgeItem(itemId: number): Promise<void> {
  if (selectedKbId.value <= 0) {
    return;
  }
  const target = knowledgeItems.value.find((item) => item.itemId === itemId);
  const title = target?.title ?? '该知识条目';
  if (!confirmKnowledgeChange(`确认删除知识条目「${title}」吗？删除后无法在页面中恢复。`)) {
    return;
  }
  try {
    await deleteKnowledgeItem(selectedKbId.value, itemId);
    if (editingItemId.value === itemId) {
      closeKnowledgeItemDialog();
    }
    knowledgeItems.value = await getKnowledgeItems(selectedKbId.value);
    knowledgeError.value = '';
  } catch (error) {
    setKnowledgeError('删除知识条目', error);
  }
}

async function runKnowledgeAnalysis(): Promise<void> {
  if (selectedKbId.value <= 0 || knowledgeLoading.value) {
    return;
  }
  knowledgeLoading.value = true;
  try {
    knowledgeAnswer.value = await analyzeKnowledge(selectedKbId.value, latest.value?.device_id ?? 'field_001', knowledgeQuestion.value.trim());
    knowledgeError.value = '';
    await savePersistentDashboardStateNow();
  } catch (error) {
    setKnowledgeError('知识库分析', error);
  } finally {
    knowledgeLoading.value = false;
  }
}

async function initializeDashboard(): Promise<void> {
  const stateLoad = loadPersistentDashboardState().catch((error) => {
    console.warn('Dashboard state restore failed.', error);
  });
  await Promise.race([
    stateLoad,
    waitForAssistantTyping(220),
  ]);
  await loadDashboard();
  await stateLoad;
  await syncDeviceAlarmSettings();
  void loadCameraPositionConfig();
  syncAiAnalysisSchedule();
  void refreshKnowledge(selectedKbId.value);
  void refreshAgriSources();
  persistentStateReady = true;
  void stateLoad.then(() => {
    void refreshKnowledge(selectedKbId.value);
  });
}

async function refreshSiteSnapshot(): Promise<void> {
  try {
    const state = await getSiteState();
    siteState.value = state;
    latest.value = siteStateToTelemetry(state);
    mergeLiveHistoryPoint(state);
  } catch (error) {
    console.warn('Site snapshot refresh failed.', error);
  }
}

function sharedStateToAssistantStatus(state: string): AssistantAction['status'] | null {
  if (state === 'pending') return 'pending';
  if (state === 'confirmed') return 'confirmed';
  if (state === 'executed') return 'executed';
  if (state === 'canceled') return 'canceled';
  if (state === 'failed' || state === 'expired') return 'failed';
  return null;
}

function syncAssistantV2ActionState(id: string, state: string, payload: Record<string, unknown> = {}): void {
  if (!id) return;
  const status = sharedStateToAssistantStatus(state);
  if (!status) return;
  let changed = false;
  chatMessages.value = chatMessages.value.map((message) => {
    if (!message.suggested_actions?.some((action) => action.id === id && action.payload._assistant_v2 === true)) {
      return message;
    }
    const actions = message.suggested_actions.map((action) => {
      if (action.id !== id || action.payload._assistant_v2 !== true) return action;
      changed = true;
      const error = actionPayloadErrorText(
        payload,
        state === 'expired' ? '操作已超时，请重新发起。' : '',
      );
      return { ...action, status, error };
    });
    return { ...message, suggested_actions: actions };
  });
  if (changed) {
    syncActiveAssistantThreadMessages();
    schedulePersistentDashboardStateSave();
  }
}

function syncAssistantV2ActionsFromConversation(conversation: SharedAssistantConversation): void {
  conversation.messages.forEach((message) => {
    message.actions.forEach((action) => {
      syncAssistantV2ActionState(action.id, action.state, action.payload);
    });
  });
}

async function refreshSharedAssistantConversation(sessionId?: string): Promise<void> {
  try {
    const conversation = await getSharedAssistantConversation(
      sessionId || sharedAssistantConversation.value.session_id || undefined,
    );
    sharedAssistantConversation.value = conversation;
    syncAssistantV2ActionsFromConversation(conversation);
  } catch (error) {
    console.warn('Shared assistant conversation refresh failed.', error);
  }
}

function sharedActionPayloadText(action: SharedAssistantAction, key: string, fallback = ''): string {
  const value = action.payload[key];
  return typeof value === 'string' && value.trim().length > 0 ? value.trim() : fallback;
}

function sharedReplyChoiceActions(actions: SharedAssistantAction[]): SharedAssistantAction[] {
  return actions.filter((action) => (
    action.type === 'reply_choice'
    && action.state === 'pending'
  ));
}

function sharedActionStatusText(action: SharedAssistantAction): string {
  if (action.state === 'failed' || action.state === 'expired') {
    return actionPayloadErrorText(action.payload, action.state === 'expired' ? '操作已超时，请重新发起。' : '操作没有完成，请稍后重试。');
  }
  if (action.state === 'confirmed') return '已确认，等待设备回执';
  if (action.state === 'executed') return '已选择';
  if (action.state === 'canceled') return '已取消';
  return '';
}

function startSiteEventStream(): void {
  closeSiteEvents?.();
  closeSiteEvents = subscribeSiteEvents(
    (eventType, data) => {
      siteEventsConnected.value = true;
      if (eventType === 'telemetry' || eventType === 'device_status' || eventType === 'capabilities') {
        const state = data as SiteState;
        siteState.value = state;
        latest.value = siteStateToTelemetry(state);
        if (eventType === 'telemetry') {
          mergeLiveHistoryPoint(state);
        }
      } else if (eventType === 'water_gun') {
        syncWaterGunState(data as WaterGunState, false, hasLocalDynamicTarget());
      } else if (eventType === 'assistant_message') {
        const messageSessionId = typeof data === 'object' && data !== null &&
          'session_id' in data && typeof data.session_id === 'string'
          ? data.session_id
          : undefined;
        void refreshSharedAssistantConversation(messageSessionId);
      } else if (eventType === 'assistant_action') {
        void refreshSharedAssistantConversation();
      }
    },
    () => {
      siteEventsConnected.value = false;
    },
    () => {
      siteEventsConnected.value = true;
      void refreshSiteSnapshot();
      void refreshSharedAssistantConversation();
    },
  );
}

async function sendSharedAssistantText(text: string): Promise<void> {
  const response = await sendSharedAssistantMessage(
    text,
    sharedAssistantConversation.value.session_id || undefined,
  );
  sharedAssistantConversation.value = await getSharedAssistantConversation(response.session_id);
  syncAssistantV2ActionsFromConversation(sharedAssistantConversation.value);
}

async function submitSharedAssistantMessage(): Promise<void> {
  const text = sharedAssistantInput.value.trim();
  if (!text || sharedAssistantBusy.value) return;
  sharedAssistantBusy.value = true;
  try {
    await sendSharedAssistantText(text);
    sharedAssistantInput.value = '';
  } finally {
    sharedAssistantBusy.value = false;
  }
}

async function decideSharedAction(action: SharedAssistantAction, decision: 'confirm' | 'cancel'): Promise<void> {
  // The confirmed hardware scope exposes only water-gun actions. Refusing the
  // retired action types at the UI boundary prevents an old C5 conversation
  // from accidentally issuing a fan, light or pump command through the API.
  if (sharedAssistantActionBusy.value || action.state !== 'pending' || action.type !== 'water_gun_target') return;
  sharedAssistantActionBusy.value = action.id;
  try {
    const decided = await decideSharedAssistantAction(action.id, decision);
    if (!['confirmed', 'executed', 'canceled'].includes(decided.state)) {
      throw new UserFacingError(actionPayloadErrorText(decided.payload, '后端没有接受这次操作，请重新发起。'));
    }
    const decidedWaterGun = decided.payload.water_gun;
    if (decidedWaterGun && typeof decidedWaterGun === 'object') {
      syncWaterGunState(decidedWaterGun as WaterGunState);
    }
  } catch (error) {
    action.state = 'failed';
    action.payload = {
      ...action.payload,
      error: assistantActionErrorText(error, '操作没有完成，请稍后重试。'),
    };
    sharedAssistantConversation.value = { ...sharedAssistantConversation.value };
  } finally {
    await refreshSharedAssistantConversation();
    await loadWaterGunControlState();
    sharedAssistantActionBusy.value = '';
  }
}

async function selectSharedReplyChoice(action: SharedAssistantAction): Promise<void> {
  if (sharedAssistantActionBusy.value || action.state !== 'pending' || action.type !== 'reply_choice') return;
  const reply = sharedActionPayloadText(action, 'reply');
  if (!reply) {
    action.state = 'failed';
    action.payload = { ...action.payload, error: '这个选项缺少可发送内容。' };
    sharedAssistantConversation.value = { ...sharedAssistantConversation.value };
    return;
  }
  sharedAssistantActionBusy.value = action.id;
  try {
    const decided = await decideSharedAssistantAction(action.id, 'confirm');
    if (decided.state !== 'executed') {
      throw new UserFacingError(actionPayloadErrorText(decided.payload, '后端没有接受这个选项，请重新选择。'));
    }
    await sendSharedAssistantText(reply);
  } catch (error) {
    action.state = 'failed';
    action.payload = {
      ...action.payload,
      error: assistantActionErrorText(error, '选项没有提交，请重新选择。'),
    };
    sharedAssistantConversation.value = { ...sharedAssistantConversation.value };
  } finally {
    await refreshSharedAssistantConversation();
    sharedAssistantActionBusy.value = '';
  }
}

function sharedActionLabel(action: SharedAssistantAction): string {
  if (action.type === 'water_gun_target') return '确认水枪喷射目标';
  if (action.type === 'reply_choice') return sharedActionPayloadText(action, 'choice_label', '选择此项');
  return '不支持的历史控制操作';
}

function persistDashboardBeforeUnload(): void {
  void savePersistentDashboardStateNow();
}

onMounted(() => {
  ensureAssistantThreadState();
  void initializeDashboard();
  startSiteEventStream();
  void refreshSharedAssistantConversation();
  void loadCurrentCropPositions();
  void loadWaterGunControlState();
  document.addEventListener('visibilitychange', handleDocumentVisibilityChange);
  window.addEventListener('resize', handleAssistantViewportResize);
  window.addEventListener('keydown', handleGlobalKeydown);
  window.addEventListener('beforeunload', persistDashboardBeforeUnload);
  waterGunCountdownTimer = window.setInterval(() => {
    waterGunCountdownNow.value = Date.now();
  }, 500);
  refreshTimer = window.setInterval(() => {
    void loadDashboard(true);
  }, 5000);
  historyCalibrationTimer = window.setInterval(() => {
    void calibrateHistory();
  }, 60_000);
});

onBeforeUnmount(() => {
  stopWaterGunHeartbeat();
  if (waterGunCountdownTimer !== undefined) window.clearInterval(waterGunCountdownTimer);
  waterGunCountdownTimer = undefined;
  closeSiteEvents?.();
  closeSiteEvents = undefined;
  if (persistentStateSaveTimer) {
    window.clearTimeout(persistentStateSaveTimer);
    persistentStateSaveTimer = undefined;
  }
  if (weatherCitySearchTimer) {
    window.clearTimeout(weatherCitySearchTimer);
    weatherCitySearchTimer = undefined;
  }
  stopAssistantResize();
  clearAiAnalysisTimer();
  document.removeEventListener('visibilitychange', handleDocumentVisibilityChange);
  window.removeEventListener('resize', handleAssistantViewportResize);
  window.removeEventListener('keydown', handleGlobalKeydown);
  window.removeEventListener('beforeunload', persistDashboardBeforeUnload);
  if (refreshTimer) {
    window.clearInterval(refreshTimer);
  }
  if (historyCalibrationTimer) {
    window.clearInterval(historyCalibrationTimer);
  }
  if (metricEditorTimer) {
    window.clearTimeout(metricEditorTimer);
  }
  if (metricEditorChartTimer) {
    window.clearTimeout(metricEditorChartTimer);
  }
  if (targetRangeSavedTimer) {
    window.clearTimeout(targetRangeSavedTimer);
  }
  stopAssistantThinking();
  assistantTypeRunId += 1;
  if (diseaseImageUrl.value.startsWith('blob:')) {
    URL.revokeObjectURL(diseaseImageUrl.value);
  }
  if (chatImageUrl.value.startsWith('blob:')) {
    URL.revokeObjectURL(chatImageUrl.value);
  }
  sentChatImageUrls.forEach((url) => URL.revokeObjectURL(url));
  sentChatImageUrls.clear();
  stopBrowserSpeechInput();
});
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar">
      <div class="brand">
        <div class="brand__icon">
          <Cpu :size="25" />
        </div>
        <div>
          <strong>智慧农业终端</strong>
          <span>大棚管理平台</span>
        </div>
      </div>

      <nav class="nav-list" aria-label="页面导航">
        <button
          v-for="item in navItems"
          :key="item.key"
          class="nav-item"
          :class="{ 'nav-item--active': activeView === item.key }"
          type="button"
          @click="requestViewChange(item.key)"
        >
          <component :is="item.icon" :size="19" />
          <span>{{ item.label }}</span>
        </button>
      </nav>

      <button class="assistant-launcher" type="button" :class="{ 'assistant-launcher--open': assistantOpen }" @click="assistantOpen = !assistantOpen">
        <Bot :size="24" />
        <span>AI 助手</span>
      </button>
    </aside>

    <div class="content-layout" :class="contentLayoutClass" :style="contentLayoutStyle">
    <main class="workspace">
      <header class="topbar">
        <div>
          <p class="eyebrow">智慧农业管理平台</p>
          <h1>智慧大棚远程监控与 AI 管理平台</h1>
        </div>
        <div class="topbar__actions">
          <StatusPill :label="deviceDisplayName" state="neutral" />
          <StatusPill :label="deviceOnlineLabel" :state="deviceOnlineState" />
          <StatusPill :label="`${activeAlarms} 条未处理报警`" :state="activeAlarms > 0 ? 'watch' : 'good'" />
          <button class="icon-button" type="button" title="刷新数据" @click="refreshDashboardAndCapture">
            <RefreshCw :class="{ spinning: refreshing }" :size="19" />
          </button>
        </div>
      </header>

      <section v-if="loading" class="loading-panel">
        <Activity :size="34" />
        <span>正在读取大棚环境数据...</span>
      </section>

      <template v-else-if="latest">
        <section v-show="activeView === 'overview'" class="view-stack">
          <div class="hero-panel" :class="{ 'hero-panel--weather-open': weatherPanelOpen }">
            <div v-if="!weatherPanelOpen" class="hero-panel__copy">
              <p class="eyebrow">大棚运行状态</p>
              <h2>设备正在监测温湿度、光照、二氧化碳、空气湿度和土壤肥力</h2>
              <p>{{ lastDataUpdateText(deviceHealth?.last_telemetry_at ?? latest.timestamp) }}，系统持续跟踪环境变化、作物健康和设备运行状态。</p>
              <div class="hero-status-list">
                <StatusPill v-for="item in statusSummary" :key="item.label" :label="item.label" :state="item.state" />
              </div>
            </div>
            <section v-else class="weather-detail-panel">
              <div class="weather-detail-panel__header">
                <div>
                  <p class="eyebrow">天气详情</p>
                  <h2>{{ weatherPanelTitle }}</h2>
                  <p>天气会进入 AI 农事建议依据，下面只展示大棚管理需要看的内容。</p>
                </div>
                <div class="weather-detail-panel__actions">
                  <button class="icon-button" type="button" title="刷新天气" :disabled="weatherLoading" @click="loadWeather()">
                    <RefreshCw :class="{ spinning: weatherLoading }" :size="18" />
                  </button>
                  <button class="icon-button" type="button" title="关闭天气详情" @click="closeWeatherPanel">
                    <X :size="18" />
                  </button>
                </div>
              </div>
              <div class="weather-toolbar">
                <div class="weather-city-picker">
                  <input
                    v-model="weatherCityDraft"
                    type="search"
                    placeholder="输入城市，如 无锡 / 北京 / 上海"
                    @focus="openWeatherCityDropdown"
                    @input="scheduleWeatherCitySearch"
                    @keydown.enter.prevent="confirmWeatherCitySearch"
                  />
                  <button class="text-button" type="button" @click="openWeatherProvinceDropdown">切换城市</button>
                  <div v-if="weatherCityDropdownOpen" class="weather-city-dropdown">
                    <div v-if="weatherPickerMode === 'cities'" class="weather-city-dropdown__header">
                      <button type="button" @mousedown.prevent="returnToWeatherProvinces">返回省份</button>
                      <strong>{{ weatherSelectedProvince }}</strong>
                    </div>
                    <button
                      v-for="city in weatherSearchOptions"
                      :key="city.id || weatherCityLabel(city)"
                      type="button"
                      @mousedown.prevent="selectWeatherCity(city)"
                    >
                      <strong>{{ city.name }}</strong>
                      <span v-if="city.level === 'province'">{{ city.direct ? '直接选择' : '查看市级地区' }}</span>
                      <span v-else>{{ city.province || weatherCityLabel(city).split(' · ').slice(1).join(' · ') }}</span>
                    </button>
                    <p v-if="weatherPickerMode === 'search' && weatherCityDraft.trim() && !weatherSearchOptions.length">没有找到相关省市</p>
                  </div>
                </div>
              </div>
              <p v-if="weatherError" class="form-error">{{ weatherError }}</p>
              <div class="weather-detail-grid">
                <article class="weather-now-card">
                  <CloudSun :size="34" />
                  <div>
                    <span>当前天气</span>
                    <strong>{{ weatherCurrentDetail?.condition || currentWeather?.condition || '暂无' }} · {{ weatherValueText(weatherCurrentDetail?.temperature ?? currentWeather?.temperature, ' 摄氏度') }}</strong>
                    <small>更新时间 {{ formatDateTime(weatherCurrentDetail?.updated_at ?? currentWeather?.updated_at ?? Date.now()) }}</small>
                  </div>
                </article>
                <article class="weather-impact-card">
                  <span>对大棚的影响</span>
                  <ul>
                    <li v-for="tip in weatherImpactTips" :key="tip">{{ tip }}</li>
                  </ul>
                </article>
                <article class="weather-forecast-card">
                  <div class="weather-section-title">
                    <span>未来三天</span>
                    <small>{{ weatherDailyItems.length ? '根据心知天气逐日预报' : weatherModuleReason(weatherBundle?.daily) || '暂无预报' }}</small>
                  </div>
                  <div v-if="weatherDailyItems.length" class="weather-forecast-list">
                    <div v-for="(item, index) in weatherDailyItems.slice(0, 3)" :key="item.date" class="weather-forecast-item">
                      <strong>{{ weatherDayLabel(item, index) }}</strong>
                      <b>{{ weatherConditionText(item) }}</b>
                      <small>{{ weatherValueText(item.low, '°') }} - {{ weatherValueText(item.high, '°') }}</small>
                      <small>{{ weatherRainText(item) }} · 湿度 {{ weatherValueText(item.humidity, '%') }}</small>
                      <small>{{ item.wind_direction || '风向暂无' }} {{ item.wind_scale ? `${item.wind_scale}级` : '' }}</small>
                    </div>
                  </div>
                </article>
                <article v-if="weatherAlarmItems.length" class="weather-warning-card">
                  <span>天气预警</span>
                  <p v-for="item in weatherAlarmItems" :key="`${item.title}-${item.pub_date}`">{{ item.title || item.type }} {{ item.level || '' }}</p>
                </article>
              </div>
            </section>
            <div v-if="!weatherPanelOpen" class="hero-panel__status">
              <button v-if="currentWeather" class="weather-card weather-card--button" type="button" @click="openWeatherPanel">
                <div>
                  <CloudSun :size="28" />
                  <span>{{ weatherDisplayLocation }}</span>
                </div>
                <strong>{{ currentWeather.condition }} · {{ currentWeather.temperature }} 摄氏度</strong>
                <div class="weather-card__today">
                  <span><b>今日</b> {{ weatherTodayDetail.condition }}</span>
                  <span>{{ weatherTodayDetail.temperature }}</span>
                  <span>{{ weatherTodayDetail.rainfall }} · {{ weatherTodayDetail.humidity }}</span>
                  <span>{{ weatherTodayDetail.wind }}</span>
                </div>
                <time>更新 {{ formatDateTime(currentWeather.updated_at) }}</time>
              </button>
              <button v-else class="weather-card weather-card--button" type="button" @click="openWeatherPanel">
                <div>
                  <CloudSun :size="28" />
                  <span>{{ weatherCity }}</span>
                </div>
                <strong>{{ weatherLoading ? '天气加载中' : '天气暂不可用' }}</strong>
                <p>{{ weatherError || '点击打开天气详情并配置城市。' }}</p>
              </button>
            </div>
          </div>

          <div class="overview-live-layout">
            <CameraGrowthPanel
              ref="cameraGrowthPanelRef"
              :active="cameraPanelActive"
              :camera-position-config="cameraPositionConfig"
              @analysis-updated="handleCameraAnalysisUpdated"
              @crop-positions-updated="handleCropPositionsUpdated"
            />
            <section class="panel overview-metrics-panel">
              <div class="section-heading">
                <div>
                  <h2>参数实际值</h2>
                  <span>内容与原首页总览保持一致</span>
                </div>
              </div>
              <div class="overview-metric-list">
                <article
                  v-for="metric in overviewMetricCards"
                  :key="metric.title"
                  :class="['overview-metric-item', `overview-metric-item--${metric.state}`]"
                >
                  <div class="overview-metric-item__top">
                    <span>
                      <component :is="metric.icon" :size="18" />
                      {{ metric.title }}
                    </span>
                    <strong>{{ metric.statusLabel }}</strong>
                  </div>
                  <div class="overview-metric-item__value">
                    <b>{{ metric.value }}</b>
                    <em>{{ metric.unit }}</em>
                  </div>
                  <p>{{ metric.hint }}</p>
                </article>
              </div>
            </section>
          </div>

          <details class="panel camera-position-config" @toggle="handleCameraPositionConfigToggle">
            <summary>相机定位参数</summary>
            <p>用于计算 A→B 的平面距离和方位角。请使用棋盘格标定值；仅填写 58° 视场角不能保证定位精度。</p>
            <div class="camera-position-config__grid">
              <label>后端摄像头编号 <input v-model.number="backendCameraConfig.device_index" type="number" min="0" max="20" /></label>
              <label>采集宽度 <input v-model.number="backendCameraConfig.width" type="number" min="160" /></label>
              <label>采集高度 <input v-model.number="backendCameraConfig.height" type="number" min="120" /></label>
              <label>采集帧率 <input v-model.number="backendCameraConfig.fps" type="number" min="1" max="30" /></label>
              <label>图像宽度 <input v-model.number="cameraPositionConfig.image_width" type="number" min="1" /></label>
              <label>图像高度 <input v-model.number="cameraPositionConfig.image_height" type="number" min="1" /></label>
              <label>fx <input v-model.number="cameraPositionConfig.fx" type="number" min="0" step="0.01" /></label>
              <label>fy <input v-model.number="cameraPositionConfig.fy" type="number" min="0" step="0.01" /></label>
              <label>cx <input v-model.number="cameraPositionConfig.cx" type="number" min="0" step="0.01" /></label>
              <label>cy <input v-model.number="cameraPositionConfig.cy" type="number" min="0" step="0.01" /></label>
              <label>畸变 k1,k2,p1,p2,k3 <input v-model="cameraDistortionText" type="text" placeholder="例如 0.01,-0.02,0,0,0" /></label>
              <label>镜头高度（mm）<input v-model.number="cameraPositionConfig.camera_height_mm" type="number" min="1" step="0.1" /></label>
              <label>向下俯角（°）<input v-model.number="cameraPositionConfig.pitch_down_deg" type="number" min="-89" max="89" step="0.1" /></label>
              <label>水平朝向偏移（°）<input v-model.number="cameraPositionConfig.yaw_deg" type="number" min="-180" max="180" step="0.1" /></label>
              <label>横滚角（°）<input v-model.number="cameraPositionConfig.roll_deg" type="number" min="-180" max="180" step="0.1" /></label>
            </div>
            <div class="camera-position-config__actions">
              <button class="primary-button" type="button" :disabled="cameraPositionConfigSaving" @click="saveCurrentCameraPositionConfig">
                <Save :size="16" /> {{ cameraPositionConfigSaving ? '保存中' : '保存定位参数' }}
              </button>
              <span>{{ cameraPositionConfigMessage }}</span>
            </div>
          </details>

          <div class="two-column">
            <EChartPanel title="近 6 小时环境趋势" :option="overviewChartOption" :active="activeView === 'overview'" :min-width="multiMetricChartMinWidth">
              <template #toolbar>
                <div class="history-chart-toolbar">
                  <div class="history-selector" aria-label="历史曲线变量选择">
                    <button
                      v-for="metric in historyMetricDefinitions"
                      :key="metric.key"
                      type="button"
                      :class="{ selected: isHistoryMetricSelected(metric.key) }"
                      @click="toggleHistoryMetric(metric.key)"
                    >
                      <i :style="{ background: metric.color }"></i>
                      {{ metric.name }}
                    </button>
                  </div>
                  <label class="history-window-control">
                    <span>时间拉伸</span>
                    <input
                      type="range"
                      min="0"
                      max="100"
                      step="1"
                      :value="historyWindowSliderValue"
                      :aria-valuetext="historyWindowDurationLabel"
                      @input="updateHistoryWindowSlider"
                    />
                    <output>{{ historyWindowDurationLabel }}</output>
                  </label>
                </div>
              </template>
            </EChartPanel>
            <section class="panel">
              <div class="section-heading">
                <h2>AI 摘要</h2>
                <div class="ai-analysis-heading-actions">
                  <StatusPill
                    v-if="aiAnalysis"
                    :label="analysisStatusLabel(aiAnalysis)"
                    :state="analysisStatusState(aiAnalysis)"
                  />
                  <StatusPill
                    v-if="aiAnalysis"
                    :label="retrievalStatusLabel(aiAnalysis.retrievalStatus)"
                    :state="retrievalStatusState(aiAnalysis.retrievalStatus)"
                  />
                  <button class="icon-button" type="button" title="立即重新生成 AI 摘要并联网查询" :disabled="aiAnalysisLoading" @click="refreshAiAnalysis('force')">
                    <RefreshCw :class="{ spinning: aiAnalysisLoading }" :size="18" />
                  </button>
                </div>
              </div>
              <p class="ai-analysis-schedule">{{ aiAnalysisUpdateText }} · 仅在本页或 AI 农事建议页可见时每 2 分钟更新</p>
              <p class="summary-text">{{ aiAnalysis?.summary ?? (aiAnalysisLoading ? '正在生成 AI 摘要...' : '等待首次 AI 分析。') }}</p>
              <ul class="suggestion-list">
                <li v-for="suggestion in aiAnalysis?.suggestions" :key="suggestion">{{ suggestion }}</li>
              </ul>
              <div v-if="aiAnalysis?.references?.length" class="reference-list reference-list--panel">
                <strong>在线资料来源</strong>
                <a
                  v-for="refItem in aiAnalysis.references"
                  :key="referenceKey(refItem)"
                  :href="refItem.url || undefined"
                  target="_blank"
                  rel="noopener noreferrer"
                >{{ refItem.sourceName || refItem.title }}：{{ refItem.title }}</a>
              </div>
            </section>
          </div>
        </section>

        <section v-show="activeView === 'realtime'" class="view-stack realtime-view">
          <template v-if="!selectedMetricCard || !selectedMetricDefinition">
            <div class="section-heading">
              <h2>实时监测</h2>
              <span>5 秒自动刷新，展示农业核心环境指标</span>
            </div>
            <div class="realtime-grid">
              <article
                v-for="metric in realtimeMetricCards"
                :key="metric.key"
                :data-metric-key="metric.key"
                :class="['realtime-card', `realtime-card--${metric.state}`]"
                role="button"
                tabindex="0"
                @click="openMetricEditor(metric.key, $event)"
                @keydown.enter="openMetricEditor(metric.key, $event)"
              >
                <div class="realtime-card__header">
                  <span :style="{ color: metric.color }">
                    <component :is="metric.icon" :size="20" />
                    {{ metric.title }}
                  </span>
                  <strong>{{ metric.statusLabel }}</strong>
                </div>
                <div class="realtime-card__value">
                  <strong>{{ metric.value }}</strong>
                  <span>{{ metric.unit }}</span>
                </div>
                <dl>
                  <div>
                    <dt>目标区间</dt>
                    <dd>{{ metric.targetText.replace('目标 ', '') }}</dd>
                  </div>
                  <div>
                    <dt>趋势</dt>
                    <dd>{{ metric.trendText }}</dd>
                  </div>
                </dl>
                <p>{{ metric.aiInsight }}</p>
              </article>
            </div>

            <section class="panel ai-risk-panel">
              <div class="section-heading">
                <h2>AI 风险指数</h2>
                <StatusPill :label="aiRiskStatus.label" :state="aiRiskStatus.state" />
              </div>
              <div class="ai-risk-content">
                <div class="ai-risk-score" :class="`ai-risk-score--${aiRiskStatus.state}`">
                  <span>当前风险</span>
                  <div>
                    <strong>{{ aiRiskScore }}</strong>
                    <em>/100</em>
                  </div>
                  <i><b :style="{ width: `${aiRiskScore}%` }"></b></i>
                </div>
                <div class="ai-risk-detail">
                  <p>{{ aiRiskSummary }}</p>
                  <ul>
                    <li v-for="factor in aiRiskFactors" :key="factor.key" :class="`ai-risk-factor--${factor.state}`">
                      <span>{{ factor.label }}</span>
                      <em>{{ factor.detail }}</em>
                    </li>
                  </ul>
                </div>
              </div>
            </section>
          </template>

          <section
            v-else
            ref="metricEditorStageRef"
            :class="['metric-editor-stage', metricEditorTransition ? `metric-editor-stage--${metricEditorTransition}` : '']"
            :style="metricEditorStyle"
          >
            <button class="metric-editor-nav metric-editor-nav--prev" type="button" title="上一个变量" @click="switchMetricEditor(-1)">
              &lt;
            </button>
            <button class="metric-editor-nav metric-editor-nav--next" type="button" title="下一个变量" @click="switchMetricEditor(1)">
              &gt;
            </button>

            <article class="metric-editor-page metric-editor-page--current">
              <div class="metric-editor__header">
                <div>
                  <span :style="{ color: selectedMetricCard.color }">{{ selectedMetricCard.statusLabel }}</span>
                  <h2>{{ selectedMetricCard.title }}</h2>
                </div>
                <button class="icon-button" type="button" title="关闭详情" @click="closeMetricEditor">
                  <X :size="18" />
                </button>
              </div>

              <section class="metric-editor__value">
                <component :is="selectedMetricCard.icon" :size="34" :style="{ color: selectedMetricCard.color }" />
                <strong>{{ selectedMetricCard.value }}</strong>
                <span>{{ selectedMetricCard.unit }}</span>
              </section>

              <section class="target-editor">
                <div class="section-heading">
                  <h2>&#30446;&#26631;&#21306;&#38388;</h2>
                  <span>{{ selectedMetricCard.targetText }}</span>
                </div>
                <div class="target-editor__inputs">
                  <label>
                    <span>&#19979;&#38480;</span>
                    <input v-model="targetMinDraft" type="number" :step="selectedMetricInputStep" />
                  </label>
                  <label>
                    <span>&#19978;&#38480;</span>
                    <input v-model="targetMaxDraft" type="number" :step="selectedMetricInputStep" />
                  </label>
                </div>
                <p v-if="targetRangeError" class="form-error">{{ targetRangeError }}</p>
                <p v-if="targetRangeSavedMessage" class="form-success">{{ targetRangeSavedMessage }}</p>
                <button class="primary-button target-save-button" type="button" :class="{ 'target-save-button--saved': targetRangeSavedMessage && !targetRangeSaving }" :disabled="targetRangeSaving" @click="saveMetricTargetRange">
                  <RefreshCw v-if="targetRangeSaving" :size="18" class="spinning" />
                  <ShieldCheck v-else-if="targetRangeSavedMessage" :size="18" />
                  <Save v-else :size="18" />
                  {{ targetRangeSaving ? '保存中' : targetRangeSavedMessage ? '已保存' : '保存目标' }}
                </button>
              </section>

              <section class="metric-detail-panel">
                <dl>
                  <div>
                    <dt>趋势</dt>
                    <dd>{{ selectedMetricCard.trendText }}</dd>
                  </div>
                </dl>
                <p>{{ selectedMetricCard.aiInsight }}</p>
              </section>

              <EChartPanel
                :title="`${selectedMetricDefinition.name}\u8d8b\u52bf`"
                :option="selectedMetricChartOption"
                :active="metricEditorChartActive"
              />
            </article>
          </section>
        </section>

        <section v-show="activeView === 'history'" class="view-stack">
          <EChartPanel title="历史曲线" :option="historyChartOption" :active="activeView === 'history'" :min-width="multiMetricChartMinWidth">
            <template #toolbar>
                <div class="history-chart-toolbar">
                  <div class="history-selector" aria-label="历史曲线变量选择">
                    <button
                      v-for="metric in historyMetricDefinitions"
                      :key="metric.key"
                      type="button"
                      :class="{ selected: isHistoryMetricSelected(metric.key) }"
                      @click="toggleHistoryMetric(metric.key)"
                    >
                      <i :style="{ background: metric.color }"></i>
                      {{ metric.name }}
                    </button>
                  </div>
                  <label class="history-window-control">
                    <span>时间拉伸</span>
                    <input
                      type="range"
                      min="0"
                      max="100"
                      step="1"
                      :value="historyWindowSliderValue"
                      :aria-valuetext="historyWindowDurationLabel"
                      @input="updateHistoryWindowSlider"
                    />
                    <output>{{ historyWindowDurationLabel }}</output>
                  </label>
                </div>
            </template>
          </EChartPanel>
          <section class="panel">
            <div class="section-heading">
              <h2>历史采样列表</h2>
            </div>
            <div class="data-table data-table--five">
              <div class="data-table__head">
                <span>时间</span>
                <span>温度</span>
                <span>光照</span>
                <span>二氧化碳</span>
                <span>空气湿度</span>
              </div>
              <div v-for="point in historyPoints.slice(-8).reverse()" :key="point.timestamp" class="data-table__row">
                <span>{{ formatDateTime(point.timestamp) }}</span>
                <span>{{ historyValueText(point.temperature, '摄氏度') }}</span>
                <span>{{ historyValueText(point.light, 'lux') }}</span>
                <span>{{ historyValueText(point.co2, 'ppm') }}</span>
                <span>{{ historyValueText(point.soil_moisture, '%') }}</span>
              </div>
            </div>
          </section>
        </section>

        <section v-show="activeView === 'disease'" class="view-stack">
          <section class="panel">
            <div class="section-heading">
              <div class="section-heading__copy">
              <h2>病害识别</h2>
              <span>上传作物图片，识别健康问题并获得处理建议</span>
              </div>
              <button class="text-button" type="button" @click="openDiseasePhotoLibrary">
                <Image :size="18" /> 图片库
              </button>
            </div>
            <div class="disease-layout">
              <div class="image-uploader">
                <label
                  class="upload-drop"
                  :class="{ 'upload-drop--dragging': diseaseDragActive }"
                  @dragenter.prevent="handleDiseaseDragEnter"
                  @dragover.prevent="handleImageDragOver"
                  @dragleave.prevent="handleDiseaseDragLeave"
                  @drop.prevent="handleDiseaseDrop"
                >
                  <Upload :size="28" />
                  <strong>{{ diseaseDragActive ? '松开以上传并识别图片' : diseaseImageUrl ? '重新上传叶片图片' : '上传叶片图片' }}</strong>
                  <span>点击选择或拖入 jpg / png / webp，最大 10MB</span>
                  <input type="file" accept="image/jpeg,image/png,image/webp" :disabled="diseaseLoading" @change="handleDiseaseUpload" />
                </label>
                <div class="image-upload-actions">
                  <button class="text-button" type="button" :disabled="diseaseLoading" @click="pasteDiseaseImage">
                    <ClipboardPaste :size="17" /> {{ diseaseLoading ? '正在识别' : '粘贴图片' }}
                  </button>
                  <button v-if="diseaseImageUrl" class="text-button" type="button" :disabled="diseaseLoading" @click="clearDiseaseImage">
                    <X :size="16" /> 清除图片
                  </button>
                </div>
                <p v-if="diseaseUploadError" class="form-error disease-error">{{ diseaseUploadError }}</p>
              </div>
              <div class="detection-stage" :class="{ 'detection-stage--empty': !diseaseImageUrl || diseaseImageLoadError }">
                <div v-if="diseaseImageUrl && !diseaseImageLoadError" class="detection-media">
                  <img
                    :src="diseaseImageUrl"
                    alt="上传的作物图片"
                    @load="diseaseImageLoadError = false"
                    @error="diseaseImageLoadError = true"
                  />
                  <div
                    v-for="box in diseaseDetectionBoxes"
                    :key="box.id"
                    class="detect-box"
                    :style="{ left: `${box.bbox.x}%`, top: `${box.bbox.y}%`, width: `${box.bbox.width}%`, height: `${box.bbox.height}%` }"
                  >
                    <span>{{ box.label }} · {{ confidenceText(box.confidence) }}</span>
                  </div>
                </div>
                <div v-if="!diseaseImageUrl || diseaseImageLoadError" class="empty-visual">
                  <ImageOff v-if="diseaseImageLoadError" :size="46" />
                  <Image v-else :size="46" />
                  <strong>{{ diseaseImageLoadError ? '图片加载失败' : '等待上传图片' }}</strong>
                  <span>{{ diseaseImageLoadError ? '请重新选择、拖入或粘贴图片。' : '可以选择文件、拖入图片或点击粘贴图片。' }}</span>
                </div>
              </div>
            </div>
          </section>

          <section class="panel">
            <div class="section-heading">
              <h2>作物健康识别结果</h2>
            </div>
            <p v-if="diseaseLoading" class="summary-text">正在分析图片...</p>
            <template v-else-if="diseaseResult">
              <StatusPill
                v-if="diseaseResult.retrievalStatus"
                :label="retrievalStatusLabel(diseaseResult.retrievalStatus)"
                :state="retrievalStatusState(diseaseResult.retrievalStatus)"
              />
              <p class="summary-text">{{ diseaseResult.summary }}</p>
              <div class="result-grid">
                <article v-for="det in diseaseResult.detections" :key="det.id">
                  <strong>{{ det.label }}</strong>
                  <span>{{ confidenceText(det.confidence) }}</span>
                </article>
              </div>
              <p class="callout-text">{{ diseaseResult.explanation }}</p>
              <ul class="suggestion-list">
                <li v-for="suggestion in diseaseResult.suggestions" :key="suggestion">{{ suggestion }}</li>
              </ul>
              <div v-if="diseaseResult.references?.length" class="reference-list reference-list--panel">
                <strong>识别结果参考资料</strong>
                <a
                  v-for="refItem in diseaseResult.references"
                  :key="referenceKey(refItem)"
                  :href="refItem.url || undefined"
                  target="_blank"
                  rel="noopener noreferrer"
                >{{ refItem.sourceName || 'EPPO Global Database' }}｜{{ refItem.title }}</a>
              </div>
            </template>
            <p v-else class="empty-text">暂无识别结果，上传图片后会显示健康问题、判断依据和处理建议。</p>
          </section>
        </section>

        <div v-if="diseasePhotoLibraryOpen" class="modal-backdrop" @click.self="closeDiseasePhotoLibrary">
          <section class="modal-card disease-library-modal" role="dialog" aria-modal="true" aria-labelledby="disease-library-title">
            <div class="modal-card__header">
              <div>
                <span>病害识别图片</span>
                <h2 id="disease-library-title">图片库</h2>
              </div>
              <div class="disease-library-actions">
                <label class="text-button disease-library-upload">
                  <Upload :size="17" /> 上传图片
                  <input type="file" accept="image/*" @change="handleDiseaseUpload" />
                </label>
                <button class="icon-button" type="button" title="刷新图片库" @click="refreshDiseasePhotoLibrary">
                  <RefreshCw :class="{ spinning: diseasePhotoLoading }" :size="18" />
                </button>
                <button class="icon-button" type="button" title="关闭" @click="closeDiseasePhotoLibrary">
                  <X :size="18" />
                </button>
              </div>
            </div>

            <p v-if="diseasePhotoError" class="form-error disease-error">{{ diseasePhotoError }}</p>

            <div class="disease-library-body">
              <div class="disease-album">
                <p v-if="diseasePhotoLoading && diseasePhotos.length === 0" class="empty-text">正在读取图片库...</p>
                <p v-else-if="diseasePhotos.length === 0" class="empty-text">暂无已上传图片。</p>
                <section v-for="group in diseasePhotoGroups" :key="group.dateKey" class="disease-album-group">
                  <h3>{{ group.dateLabel }}</h3>
                  <div class="disease-photo-grid">
                    <button
                      v-for="photo in group.photos"
                      :key="photo.photoId"
                      class="disease-photo-tile"
                      :class="{ selected: selectedDiseasePhoto?.photoId === photo.photoId }"
                      type="button"
                      @click="selectDiseasePhoto(photo)"
                    >
                      <img :src="photo.url" :alt="photo.originalName || '病害识别图片'" loading="lazy" />
                      <span>{{ diseasePhotoTimeLabel(photo.createdAt) }}</span>
                    </button>
                  </div>
                </section>
              </div>

              <aside class="disease-photo-detail" :class="{ 'disease-photo-detail--empty': !selectedDiseasePhoto }">
                <template v-if="selectedDiseasePhoto">
                  <div class="disease-photo-detail__image">
                    <img
                      v-if="!selectedDiseasePhotoImageError"
                      :src="selectedDiseasePhoto.url"
                      :alt="selectedDiseasePhoto.originalName || '病害识别图片详情'"
                      @load="selectedDiseasePhotoImageError = false"
                      @error="selectedDiseasePhotoImageError = true"
                    />
                    <div v-else class="image-load-placeholder">
                      <ImageOff :size="34" />
                      <span>图片暂时无法显示</span>
                    </div>
                  </div>
                  <div class="disease-photo-detail__meta">
                    <strong>{{ selectedDiseasePhoto.originalName || '未命名图片' }}</strong>
                    <span>{{ selectedDiseasePhoto.createdAt }} · {{ diseasePhotoSizeLabel(selectedDiseasePhoto.size) }}</span>
                  </div>
                  <template v-if="selectedDiseasePhotoAnalysis">
                    <p class="summary-text">{{ selectedDiseasePhotoAnalysis.summary }}</p>
                    <div class="result-grid disease-photo-detail__results">
                      <article v-for="det in selectedDiseasePhotoAnalysis.detections" :key="det.id">
                        <strong>{{ det.label }}</strong>
                        <span>{{ confidenceText(det.confidence) }}</span>
                      </article>
                    </div>
                    <p class="callout-text">{{ selectedDiseasePhotoAnalysis.explanation }}</p>
                    <ul class="suggestion-list disease-photo-detail__suggestions">
                      <li v-for="suggestion in selectedDiseasePhotoAnalysis.suggestions" :key="suggestion">{{ suggestion }}</li>
                    </ul>
                  </template>
                  <p v-else class="empty-text">这张图片还没有保存识别结果。</p>
                  <button
                    class="text-button disease-delete-button"
                    type="button"
                    :disabled="diseasePhotoDeletingId === selectedDiseasePhoto.photoId"
                    @click="removeDiseasePhoto(selectedDiseasePhoto)"
                  >
                    <Trash2 :size="17" /> {{ diseasePhotoDeletingId === selectedDiseasePhoto.photoId ? '删除中...' : '删除图片' }}
                  </button>
                </template>
                <p v-else class="empty-text">点击左侧缩略图查看完整图片和识别结果。</p>
              </aside>
            </div>
          </section>
        </div>

        <section v-show="activeView === 'ai'" class="view-stack">
          <section class="panel ai-panel">
            <div class="section-heading">
              <h2>AI 农事建议</h2>
              <div class="ai-analysis-heading-actions">
                <StatusPill
                  v-if="aiAnalysis"
                  :label="analysisStatusLabel(aiAnalysis)"
                  :state="analysisStatusState(aiAnalysis)"
                />
                <StatusPill
                  v-if="aiAnalysis"
                  :label="retrievalStatusLabel(aiAnalysis.retrievalStatus)"
                  :state="retrievalStatusState(aiAnalysis.retrievalStatus)"
                />
                <button class="icon-button" type="button" title="立即重新生成农事建议并联网查询" :disabled="aiAnalysisLoading" @click="refreshAiAnalysis('force')">
                  <RefreshCw :class="{ spinning: aiAnalysisLoading }" :size="18" />
                </button>
              </div>
            </div>
            <p class="ai-analysis-schedule">{{ aiAnalysisUpdateText }} · 仅在总览或本页可见时每 2 分钟更新</p>
            <p class="summary-text">{{ aiAnalysis?.summary ?? (aiAnalysisLoading ? '正在生成 AI 农事建议...' : '等待首次 AI 分析。') }}</p>
            <div class="suggestion-grid">
              <article v-for="suggestion in aiAnalysis?.suggestions" :key="suggestion">
                <ShieldCheck :size="22" />
                <span>{{ suggestion }}</span>
              </article>
            </div>
          </section>

          <section class="panel">
            <div class="section-heading">
              <h2>分析依据</h2>
              <span>展示系统判断依据</span>
            </div>
            <ul class="suggestion-list">
              <li v-for="basis in aiAnalysis?.basis" :key="basis">{{ basis }}</li>
            </ul>
            <div v-if="aiAnalysis?.references?.length" class="reference-list reference-list--panel">
              <strong>官方资料引用</strong>
              <a
                v-for="refItem in aiAnalysis.references"
                :key="referenceKey(refItem)"
                :href="refItem.url || undefined"
                target="_blank"
                rel="noopener noreferrer"
              >{{ refItem.sourceName || '在线农业知识源' }}｜{{ refItem.title }}</a>
            </div>
          </section>
        </section>

        <section v-show="activeView === 'control'" class="view-stack">
          <section class="panel water-gun-panel">
            <div class="section-heading water-gun-heading">
              <div>
                <h2>水枪目标控制</h2>
                <span>拖动三角目标，设置水枪的瞄准位置。</span>
              </div>
              <div class="water-gun-heading__status">
                <div class="water-gun-mode-switch" role="group" aria-label="水枪控制模式">
                  <button type="button" :class="{ 'is-active': !waterGunDynamicActive }" @click="selectWaterGunMode('static')">静态模式</button>
                  <button type="button" :class="{ 'is-active': waterGunDynamicActive }" @click="selectWaterGunMode('dynamic')">动态模式</button>
                </div>
                <button
                  class="water-gun-state-button"
                  :class="{ 'is-on': waterGunSpraying }"
                  type="button"
                  :disabled="waterGunSprayActionDisabled"
                  @click="setWaterGunSprayEnabled(!waterGunSpraying)"
                >
                  <span></span>{{ waterGunSpraying ? '水枪开启' : '水枪关闭' }}
                </button>
              </div>
            </div>
            <div class="water-gun-layout">
              <div class="water-gun-field-wrap">
                <svg
                  ref="waterGunFieldRef"
                  class="water-gun-field"
                  viewBox="0 0 800 400"
                  role="application"
                  aria-label="水枪目标俯视极坐标控制区域"
                  @pointerdown="startWaterGunPointer"
                  @pointermove="moveWaterGunPointer"
                  @pointerup="endWaterGunPointer"
                  @pointercancel="endWaterGunPointer"
                >
                  <defs>
                    <linearGradient id="water-gun-field-bg" x1="0" y1="1" x2="0" y2="0">
                      <stop offset="0" stop-color="#e9f8f0" />
                      <stop offset="1" stop-color="#f8fcf9" />
                    </linearGradient>
                    <linearGradient id="water-gun-body" x1="0" y1="1" x2="0" y2="0">
                      <stop offset="0" stop-color="#10a9ad" />
                      <stop offset="1" stop-color="#33d1c6" />
                    </linearGradient>
                    <linearGradient id="water-gun-base" x1="0" y1="0" x2="1" y2="1">
                      <stop offset="0" stop-color="#ffb33c" />
                      <stop offset="1" stop-color="#ff6f61" />
                    </linearGradient>
                    <pattern id="water-gun-spray-pattern" width="8" height="8" patternUnits="userSpaceOnUse">
                      <rect width="8" height="8" fill="#168f8a" />
                      <circle cx="2" cy="2" r="1.2" fill="#bdf6ed" />
                      <circle cx="7" cy="6" r="1" fill="#7ee8dc" />
                    </pattern>
                  </defs>
                  <rect x="30" y="15" width="740" height="370" rx="16" fill="url(#water-gun-field-bg)" stroke="#8db89a" stroke-width="2" />
                  <path d="M400 385 V15 M30 200 H770" class="water-gun-grid-line" />
                  <path d="M215 15 V385 M585 15 V385 M30 107.5 H770 M30 292.5 H770" class="water-gun-grid-line water-gun-grid-line--minor" />
                  <text x="400" y="32" text-anchor="middle" class="water-gun-field-label">正前方 1200 mm</text>
                  <text x="44" y="375" class="water-gun-field-label">左 −</text>
                  <text x="756" y="375" text-anchor="end" class="water-gun-field-label">右 +</text>
                  <line x1="400" y1="385" :x2="waterGunMarker.x" :y2="waterGunMarker.y" class="water-gun-aim-line" />
                  <g class="water-gun-origin" transform="translate(400 385)">
                    <circle class="water-gun-base" r="23" />
                    <g class="water-gun-body" :transform="`rotate(${waterGunActualBearingDeg})`">
                      <rect x="-10" y="-48" width="20" height="37" rx="9" />
                      <rect class="water-gun-nozzle" x="-5" y="-70" width="10" height="29" rx="5" />
                      <rect class="water-gun-tip" x="-8" y="-74" width="16" height="8" rx="4" />
                      <path class="water-gun-wing" d="M-10 -34 L-24 -27 L-20 -14 L-8 -20 Z" />
                      <path class="water-gun-wing" d="M10 -34 L24 -27 L20 -14 L8 -20 Z" />
                      <circle class="water-gun-tank" cy="-23" r="8" />
                    </g>
                  </g>
                  <g
                    v-for="marker in waterGunCropMarkers"
                    :key="marker.crop.id"
                    class="water-gun-crop-marker"
                    :transform="`translate(${marker.point.x} ${marker.point.y})`"
                    role="button"
                    tabindex="0"
                    :aria-label="`选择作物目标 ${marker.crop.crop_name || marker.crop.label}`"
                    @pointerdown.stop
                    @click.stop="selectWaterGunCropTarget(marker.crop)"
                    @keydown.enter.stop.prevent="selectWaterGunCropTarget(marker.crop)"
                    @keydown.space.stop.prevent="selectWaterGunCropTarget(marker.crop)"
                  >
                    <title>{{ marker.crop.crop_name || marker.crop.label }}</title>
                    <circle class="water-gun-crop-marker__hit" r="15" />
                    <circle class="water-gun-crop-marker__dot" r="6" />
                    <text class="water-gun-crop-marker__label" x="10" y="-8">{{ marker.crop.crop_name || marker.crop.label }}</text>
                  </g>
                  <g
                    class="water-gun-target"
                    :class="{ 'water-gun-target--spraying': waterGunSpraying && !waterGunStaticDraftDirty, 'water-gun-target--draft': waterGunStaticDraftDirty, 'water-gun-target--outside': waterGunTargetOutside }"
                    :transform="`translate(${waterGunMarker.x} ${waterGunMarker.y})`"
                  >
                    <path d="M0 -15 L14 11 L-14 11 Z" :fill="waterGunSpraying && !waterGunStaticDraftDirty ? 'url(#water-gun-spray-pattern)' : '#7c8780'" />
                  </g>
                  <g v-if="waterGunTargetOutside" :transform="`translate(${waterGunMarker.x} ${waterGunMarker.y})`">
                    <rect x="-36" y="18" width="72" height="24" rx="12" class="water-gun-outside-badge" />
                    <text y="35" text-anchor="middle" class="water-gun-outside-text">范围外</text>
                  </g>
                </svg>
              </div>
              <aside class="water-gun-readout">
                <div v-if="waterGunTargetSource === 'vision'" class="water-gun-vision-notice">
                  <Bot :size="19" />
                  <div><strong>视觉识别目标</strong><span>{{ waterGunTargetLabel || '已识别物体' }}</span></div>
                </div>
                <div class="water-gun-compact-values">
                  <article><span>水平距离</span><strong>{{ Math.round(waterGunRangeMm) }} mm</strong></article>
                  <article><span>当前方向</span><strong>{{ waterGunBearingText }}</strong></article>
                </div>
                <p v-if="waterGunTargetOutside" class="water-gun-warning">
                  目标超出手动区域，三角形已停在对应边缘。
                </p>
                <p class="water-gun-message">{{ waterGunMessage }}</p>
                <div class="water-gun-actions">
                  <button v-if="!waterGunDynamicActive" class="primary-button" type="button" :disabled="waterGunBusy || !waterGunStaticDraftDirty" @click="waterGunStaticConfirmOpen = true">
                    <Send :size="17" /> 确认目标
                  </button>
                  <button
                    :class="waterGunSpraying ? 'danger-button' : 'water-gun-dynamic-button'"
                    type="button"
                    :disabled="waterGunSprayActionDisabled"
                    @click="setWaterGunSprayEnabled(!waterGunSpraying)"
                  >
                    <Droplets :size="17" /> {{ waterGunSpraying ? '关闭水枪' : '开启水枪' }}
                  </button>
                  <button
                    v-if="!waterGunDynamicActive && waterGunStaticDraftDirty"
                    class="water-gun-return-button"
                    type="button"
                    :disabled="waterGunBusy"
                    @click="returnWaterGunToActualTarget"
                  >
                    <RefreshCw :size="17" /> 回到原处
                  </button>
                </div>
                <section v-if="!waterGunDynamicActive" class="water-gun-schedule" aria-labelledby="water-gun-schedule-title">
                  <div class="water-gun-schedule__header">
                    <div><span id="water-gun-schedule-title">喷射时间</span><strong :class="{ 'is-active': waterGunSpraying, 'is-stopped': waterGunState?.stop_reason === 'timed_complete' }">{{ waterGunCountdownLabel }}</strong></div>
                  </div>
                  <div class="water-gun-schedule__modes" role="group" aria-label="喷射时间模式">
                    <button type="button" :class="{ 'is-active': waterGunSpraySchedule === 'timed' }" :disabled="waterGunSpraying" @click="selectWaterGunSpraySchedule('timed')">设置时间</button>
                    <button type="button" :class="{ 'is-active': waterGunSpraySchedule === 'continuous' }" :disabled="waterGunSpraying" @click="selectWaterGunSpraySchedule('continuous')">持续开启</button>
                  </div>
                  <div v-if="waterGunSpraySchedule === 'timed'" class="water-gun-duration-inputs">
                    <label><input v-model.number="waterGunDurationHours" type="number" min="0" max="23" step="1" :disabled="waterGunSpraying" /><span>时</span></label>
                    <label><input v-model.number="waterGunDurationMinutes" type="number" min="0" max="59" step="1" :disabled="waterGunSpraying" /><span>分</span></label>
                    <label><input v-model.number="waterGunDurationSeconds" type="number" min="0" max="59" step="1" :disabled="waterGunSpraying" /><span>秒</span></label>
                  </div>
                  <p v-if="waterGunTimedDurationError" class="water-gun-schedule__error">{{ waterGunTimedDurationError }}</p>
                  <p v-else-if="waterGunSpraySchedule === null" class="water-gun-schedule__error">目标已变更，请重新选择喷射时间。</p>
                </section>
              </aside>
            </div>
          </section>

          <!-- Retired: fan, curtain and physical alarm controls are not installed. -->
          <!--
          <section class="panel">
            <div class="section-heading">
              <div class="section-heading__copy">
                <h2>远程设备控制</h2>
                <span>页面与 C5 共用同一设备状态，语音确认或手动操作后会实时同步</span>
              </div>
            </div>
            <div class="site-link-status">
              <StatusPill :label="`SSE ${siteEventsConnected ? '已连接' : '重连中'}`" :state="siteEventsConnected ? 'good' : 'watch'" />
              <StatusPill :label="`S3 ${s3State?.online ? '在线' : '离线'}`" :state="s3State?.online ? 'good' : 'danger'" />
              <StatusPill :label="`C5 ${c5State?.online ? '在线' : '离线'}`" :state="c5State?.online ? 'good' : 'danger'" />
            </div>
            <div class="control-grid device-control-grid">
              <article
                v-for="actuator in siteActuatorCards"
                :key="actuator.target"
                class="control-card site-actuator-card"
                :class="{
                  'site-actuator-card--active': displayedActuatorMasterEnabled(actuator.target, actuator.state),
                  'site-actuator-card--danger': actuator.danger && displayedActuatorMasterEnabled(actuator.target, actuator.state),
                }"
              >
                <div class="site-actuator-card__header">
                  <span class="site-actuator-card__icon"><component :is="actuator.icon" :size="25" /></span>
                  <span
                    class="site-actuator-card__status"
                    :class="{ 'site-actuator-card__status--on': displayedActuatorMasterEnabled(actuator.target, actuator.state) }"
                  >
                    {{ displayedActuatorMasterEnabled(actuator.target, actuator.state) ? '运行中' : '已关闭' }}
                  </span>
                </div>
                <div class="site-actuator-card__copy">
                  <strong>{{ actuator.label }}</strong>
                  <span>{{ actuator.description }}</span>
                </div>
                <button
                  class="toggle-switch"
                  :class="{
                    'toggle-switch--on': displayedActuatorMasterEnabled(actuator.target, actuator.state),
                    'toggle-switch--danger': actuator.danger,
                  }"
                  type="button"
                  :disabled="siteActuatorBusy !== null"
                  :aria-label="`${displayedActuatorMasterEnabled(actuator.target, actuator.state) ? '关闭' : '开启'}${actuator.label}总开关`"
                  @click="setSiteActuatorMaster(actuator.target, !displayedActuatorMasterEnabled(actuator.target, actuator.state))"
                >
                  <span>{{ siteActuatorBusy === actuator.target ? '处理中' : '关闭' }}</span>
                  <span>{{ siteActuatorBusy === actuator.target ? '处理中' : '开启' }}</span>
                  <i></i>
                </button>
              </article>
            </div>
            <p v-if="siteControlMessage" class="site-control-message" aria-live="polite">{{ siteControlMessage }}</p>
          </section>
          -->

          <section class="panel shared-assistant-panel">
            <div class="section-heading">
              <div>
                <h2>现场 AI 共享会话</h2>
                <span>C5 语音请求与待确认操作会同步显示在这里</span>
              </div>
            </div>
            <div class="shared-assistant-list">
              <article v-for="message in sharedAssistantConversation.messages" :key="message.id" :class="`shared-message shared-message--${message.role}`">
                <strong>{{ message.role === 'assistant' ? '现场 AI' : message.channel === 'edge_text' ? 'C5 用户' : 'Web 用户' }}</strong>
                <p>{{ message.content }}</p>
                <div v-if="sharedReplyChoiceActions(message.actions).length" class="assistant-choice-list">
                  <button
                    v-for="action in sharedReplyChoiceActions(message.actions)"
                    :key="action.id"
                    class="assistant-choice-button"
                    type="button"
                    :disabled="!!sharedAssistantActionBusy"
                    @click="selectSharedReplyChoice(action)"
                  >
                    {{ sharedActionPayloadText(action, 'choice_label', sharedActionLabel(action)) }}
                  </button>
                </div>
                <div v-for="action in message.actions.filter((item) => item.type === 'water_gun_target')" :key="action.id" class="shared-action">
                  <span>{{ sharedActionLabel(action) }} · {{ action.state }}</span>
                  <em v-if="sharedActionStatusText(action)">{{ sharedActionStatusText(action) }}</em>
                  <div v-if="action.state === 'pending'">
                    <button type="button" :disabled="!!sharedAssistantActionBusy" @click="decideSharedAction(action, 'confirm')">确认</button>
                    <button type="button" class="text-button" :disabled="!!sharedAssistantActionBusy" @click="decideSharedAction(action, 'cancel')">取消</button>
                  </div>
                </div>
              </article>
              <p v-if="sharedAssistantConversation.messages.length === 0" class="empty-text">C5 尚未发起现场会话。</p>
            </div>
            <form class="shared-assistant-composer" @submit.prevent="submitSharedAssistantMessage">
              <input v-model="sharedAssistantInput" placeholder="可在这里测试：设置水枪目标、获取建议……" />
              <button type="submit" :disabled="sharedAssistantBusy || !sharedAssistantInput.trim()">{{ sharedAssistantBusy ? '处理中' : '发送' }}</button>
            </form>
          </section>

          <!-- Retired: these are receipts for the removed generic actuator API. -->
          <!--
          <section class="panel">
            <div class="section-heading">
              <h2>执行回执</h2>
            </div>
            <div class="command-list">
              <article v-for="result in siteCommandResults" :key="result.command_id">
                <strong>{{ siteActuatorDefinitions.find((item) => item.target === result.target)?.label ?? result.target }} → {{ siteCommandValueText(result) }}</strong>
                <span>{{ siteCommandStateText(result.state) }}</span>
                <time>{{ formatDateTime(result.created_at) }}</time>
              </article>
              <article v-for="result in commandResults" :key="result.executed_at">
                <strong>{{ commandActionText(result.command) }}</strong>
                <span>{{ commandResultText(result) }}</span>
                <time>{{ formatDateTime(result.executed_at) }}</time>
              </article>
              <p v-if="siteCommandResults.length === 0 && commandResults.length === 0" class="empty-text">暂无控制记录，点击上方按钮后会显示执行结果。</p>
            </div>
          </section>
          -->
        </section>

        <section v-show="activeView === 'knowledge'" class="view-stack">
          <p v-if="knowledgeError" class="form-error">{{ knowledgeError }}</p>
          <section class="panel agri-sources-panel">
            <div class="section-heading">
              <div>
                <h2>在线农业知识源</h2>
                <span>仅接入固定官方来源，资料按需查询并临时缓存，不保存外部全文</span>
              </div>
              <button class="icon-button" type="button" title="刷新来源状态" :disabled="agriSourcesLoading" @click="refreshAgriSources">
                <RefreshCw :class="{ spinning: agriSourcesLoading }" :size="18" />
              </button>
            </div>
            <p v-if="agriSourceError" class="form-error">{{ agriSourceError }}</p>
            <div class="agri-source-grid">
              <article v-for="source in agriSources" :key="source.sourceId" class="agri-source-card">
                <div class="agri-source-card__heading">
                  <div>
                    <strong>{{ source.name }}</strong>
                    <span>{{ source.sourceType === 'api' ? '官方 API' : '官方公开网页' }}</span>
                  </div>
                  <StatusPill :label="sourceStatusLabel(source)" :state="sourceStatusState(source)" />
                </div>
                <p>{{ source.description }}</p>
                <small>
                  {{ source.lastCheckedAt ? `最近检查 ${formatDateTime(Date.parse(source.lastCheckedAt))}` : '尚未进行连接检查' }}
                  <template v-if="source.lastError"> · {{ source.lastError }}</template>
                </small>
                <div class="agri-source-card__actions">
                  <button
                    class="toggle-switch"
                    :class="{ 'toggle-switch--on': source.enabled }"
                    type="button"
                    :disabled="agriSourceBusyId !== null || !source.configured"
                    :aria-label="`${source.enabled ? '停用' : '启用'} ${source.name}`"
                    @click="toggleAgriSource(source)"
                  >
                    <span>停用</span><span>启用</span><i></i>
                  </button>
                  <button
                    class="text-button"
                    type="button"
                    :disabled="agriSourceBusyId !== null || !source.configured"
                    @click="testOnlineAgriSource(source)"
                  >
                    {{ agriSourceBusyId === source.sourceId ? '测试中...' : '测试连接' }}
                  </button>
                </div>
                <em v-if="!source.configured">部署者配置 EPPO_API_KEY 后即可启用</em>
              </article>
              <p v-if="!agriSourcesLoading && agriSources.length === 0" class="empty-text">在线农业知识源状态暂时无法获取。</p>
            </div>
          </section>
          <div class="knowledge-layout">
            <section class="panel knowledge-parent-panel">
              <div class="section-heading">
                <div>
                  <h2>知识库管理</h2>
                  <span>已有知识库作为父级，选择后查看下方知识条目</span>
                </div>
                <button class="primary-button" type="button" @click="beginCreateKnowledgeBase">
                  <Plus :size="18" /> 新增知识库
                </button>
              </div>
              <div class="knowledge-tree">
                <article v-for="base in knowledgeBases" :key="base.kbId" :class="{ selected: selectedKbId === base.kbId }" @click="selectKnowledgeBase(base.kbId)">
                  <i class="knowledge-tree__line"></i>
                  <div class="knowledge-tree__body">
                    <div class="knowledge-tree__title">
                      <strong>{{ base.name }}</strong>
                      <em v-if="selectedKbId === base.kbId">当前知识库</em>
                    </div>
                    <span>{{ base.description || '暂无描述' }}</span>
                  </div>
                  <div class="row-actions">
                    <button class="icon-button" type="button" title="编辑" @click.stop="beginEditKnowledgeBase(base)">
                      <Pencil :size="16" />
                    </button>
                    <button class="icon-button" type="button" title="删除" @click.stop="removeKnowledgeBase(base.kbId)">
                      <Trash2 :size="16" />
                    </button>
                  </div>
                </article>
                <p v-if="knowledgeBases.length === 0" class="empty-text">暂无知识库，点击右上角按钮创建第一个知识库。</p>
              </div>
            </section>

            <section class="panel knowledge-child-panel">
              <div class="section-heading">
                <div>
                  <h2>{{ selectedKnowledgeBase?.name ?? '请选择知识库' }} / 知识条目</h2>
                  <span>{{ selectedKnowledgeBase ? '当前知识库下的子级内容' : '先在左侧选择一个父级知识库' }}</span>
                </div>
                <button class="primary-button" type="button" :disabled="selectedKbId <= 0" @click="beginCreateKnowledgeItem">
                  <Plus :size="18" /> 新增知识
                </button>
              </div>
              <div class="knowledge-child-list">
                <article v-for="item in knowledgeItems" :key="item.itemId">
                  <i class="knowledge-child-list__line"></i>
                  <div class="knowledge-child-list__body">
                    <strong>{{ item.title }}</strong>
                    <span>{{ item.content }}</span>
                  </div>
                  <div class="row-actions">
                    <button class="icon-button" type="button" title="编辑" @click.stop="beginEditKnowledgeItem(item)">
                      <Pencil :size="16" />
                    </button>
                    <button class="icon-button" type="button" title="删除" @click.stop="removeKnowledgeItem(item.itemId)">
                      <Trash2 :size="16" />
                    </button>
                  </div>
                </article>
                <p v-if="selectedKbId > 0 && knowledgeItems.length === 0" class="empty-text">当前知识库还没有条目，点击右上角新增知识。</p>
                <p v-if="selectedKbId <= 0" class="empty-text">请选择左侧知识库后查看子级知识条目。</p>
              </div>
            </section>
          </div>

          <section class="panel">
            <div class="section-heading">
              <h2>知识库增强分析</h2>
              <span>结合已保存的种植知识生成管理建议</span>
            </div>
            <div class="inline-form">
              <input v-model="knowledgeQuestion" placeholder="输入分析问题" />
              <button class="primary-button" type="button" :disabled="knowledgeLoading || selectedKbId <= 0" @click="runKnowledgeAnalysis">
                <Bot :size="18" /> {{ knowledgeLoading ? '分析中' : '生成管理建议' }}
              </button>
            </div>
            <template v-if="knowledgeAnswer">
              <p class="callout-text">{{ knowledgeAnswer.answer }}</p>
              <div class="reference-list reference-list--panel">
                <strong>引用片段</strong>
                <span v-for="refItem in knowledgeAnswer.references" :key="`${refItem.itemId}-${refItem.chunkId}`">
                  {{ refItem.title }}：{{ refItem.content }}
                </span>
              </div>
            </template>
          </section>

          <div v-if="knowledgeBaseDialogOpen" class="modal-backdrop" @click.self="closeKnowledgeBaseDialog">
            <section class="modal-card" role="dialog" aria-modal="true" aria-labelledby="knowledge-base-dialog-title">
              <div class="modal-card__header">
                <div>
                  <span>知识库父级</span>
                  <h2 id="knowledge-base-dialog-title">{{ editingKbId ? '编辑知识库' : '新增知识库' }}</h2>
                </div>
                <button class="icon-button" type="button" title="关闭" @click="closeKnowledgeBaseDialog">
                  <X :size="18" />
                </button>
              </div>
              <form class="modal-form" @submit.prevent="saveKnowledgeBase">
                <label>
                  <span>知识库名称</span>
                  <input v-model="kbNameDraft" placeholder="例如：番茄结果期管理" />
                </label>
                <label>
                  <span>知识库描述</span>
                  <textarea v-model="kbDescriptionDraft" placeholder="描述这组知识的适用场景"></textarea>
                </label>
                <div class="modal-card__actions">
                  <button class="text-button" type="button" @click="closeKnowledgeBaseDialog">取消</button>
                  <button class="primary-button" type="submit">
                    <Save :size="18" /> {{ editingKbId ? '保存修改' : '创建知识库' }}
                  </button>
                </div>
              </form>
            </section>
          </div>

          <div v-if="knowledgeItemDialogOpen" class="modal-backdrop" @click.self="closeKnowledgeItemDialog">
            <section class="modal-card" role="dialog" aria-modal="true" aria-labelledby="knowledge-item-dialog-title">
              <div class="modal-card__header">
                <div>
                  <span>{{ selectedKnowledgeBase?.name ?? '未选择知识库' }}</span>
                  <h2 id="knowledge-item-dialog-title">{{ editingItemId ? '编辑知识' : '新增知识' }}</h2>
                </div>
                <button class="icon-button" type="button" title="关闭" @click="closeKnowledgeItemDialog">
                  <X :size="18" />
                </button>
              </div>
              <form class="modal-form" @submit.prevent="saveKnowledgeItem">
                <label>
                  <span>知识标题</span>
                  <input v-model="itemTitleDraft" placeholder="例如：番茄高湿病害风险" />
                </label>
                <label>
                  <span>知识正文</span>
                  <textarea v-model="itemContentDraft" placeholder="输入具体知识内容"></textarea>
                </label>
                <div class="modal-card__actions">
                  <button class="text-button" type="button" @click="closeKnowledgeItemDialog">取消</button>
                  <button class="primary-button" type="submit">
                    <Save :size="18" /> {{ editingItemId ? '保存修改' : '创建知识' }}
                  </button>
                </div>
              </form>
            </section>
          </div>
        </section>

        <section v-show="activeView === 'alarms'" class="view-stack">
          <section class="panel">
            <div class="section-heading">
              <h2>报警记录</h2>
              <span>来自环境监测、设备连接、作物健康和智能分析</span>
            </div>
            <p v-if="alarmActionMessage" class="alarm-action-message">{{ alarmActionMessage }}</p>
            <div class="alarm-list">
              <p v-if="alarms.length === 0" class="alarm-empty">当前没有需要处理的提醒，大棚运行状态正常。</p>
              <article v-for="alarm in alarms" :key="alarm.id" :class="`alarm-card alarm-card--${alarm.level}`">
                <div>
                  <strong>{{ alarm.title }}</strong>
                  <span>{{ alarm.source }} · {{ formatDateTime(alarm.timestamp) }}</span>
                </div>
                <p>{{ alarm.detail }}</p>
                <div class="alarm-card__actions">
                  <StatusPill :label="alarmStateLabel(alarm)" :state="alarmStateLevel(alarm)" />
                  <button
                    v-if="alarm.state === 'open'"
                    class="text-button"
                    type="button"
                    :disabled="acknowledgingAlarmId === alarm.id"
                    @click="confirmAlarmHandled(alarm)"
                  >
                    {{ acknowledgingAlarmId === alarm.id ? '正在确认' : '确认已处理' }}
                  </button>
                </div>
              </article>
            </div>
          </section>
        </section>
      </template>
    </main>


      <div
        v-if="assistantOpen"
        class="assistant-resizer"
        role="separator"
        aria-orientation="vertical"
        aria-label="调整 AI 助手宽度"
        title="拖动调整宽度，双击恢复默认"
        @pointerdown="startAssistantResize"
        @dblclick="resetAssistantWidth"
      >
        <span class="assistant-resizer__tip">拖动调整宽度，双击恢复默认</span>
      </div>
      <aside
        v-if="assistantOpen"
        class="assistant-panel"
        :class="{ 'assistant-panel--dragging': chatDragActive }"
        @dragenter.prevent="handleChatDragEnter"
        @dragover.prevent="handleImageDragOver"
        @dragleave.prevent="handleChatDragLeave"
        @drop.prevent="handleChatDrop"
      >
        <div v-if="chatDragActive" class="assistant-drop-overlay">
          <Image :size="34" />
          <strong>松开以添加图片</strong>
          <span>发送后会先识别图片，再生成回答</span>
        </div>
        <div class="assistant-panel__header">
          <div>
            <span>全局对话 · {{ activeAssistantThread?.title ?? '新对话' }}</span>
            <h2>AI 助手</h2>
          </div>
          <div class="assistant-header-actions">
            <button class="icon-button" type="button" title="新对话" :disabled="chatSending" @click="createNewAssistantThread">
              <Plus :size="18" />
            </button>
            <button class="icon-button" type="button" title="历史对话" @click="assistantHistoryOpen = true">
              <History :size="18" />
            </button>
            <button class="icon-button" type="button" title="已记住的偏好" @click="openAssistantPreferences">
              <SlidersHorizontal :size="18" />
            </button>
            <button class="icon-button" type="button" title="关闭 AI 助手" @click="assistantOpen = false">
              <X :size="18" />
            </button>
          </div>
        </div>
        <div v-if="assistantPreferencesOpen" class="assistant-preferences-panel">
          <div>
            <strong>已记住的偏好</strong>
            <button class="icon-button" type="button" title="关闭偏好" @click="assistantPreferencesOpen = false">
              <X :size="16" />
            </button>
          </div>
          <p v-if="assistantPreferencesLoading">正在读取…</p>
          <p v-else-if="!assistantPreferences.length">还没有保存偏好。你可以在对话中明确说“记住……”。</p>
          <article v-for="preference in assistantPreferences" :key="preference.key">
            <span><b>{{ preference.key }}</b>：{{ preference.value }}</span>
            <button class="text-button" type="button" :disabled="assistantPreferencesLoading" @click="removeAssistantPreference(preference.key)">删除</button>
          </article>
        </div>
        <div class="assistant-voice-status">
          <StatusPill :label="voiceMessage" :state="listening ? 'watch' : 'neutral'" />
        </div>
        <div class="assistant-messages-wrap">
          <div ref="assistantMessagesRef" class="chat-list assistant-panel__messages" @scroll="handleAssistantMessagesScroll">
            <article
              v-for="message in chatMessages"
              :key="message.id"
              class="chat-bubble"
              :class="[`chat-bubble--${message.role}`, { 'chat-bubble--typing': message.typing }]"
            >
              <img v-if="message.image_url" :src="message.image_url" alt="问答附图" />
              <MarkdownContent
                v-if="message.role === 'assistant'"
                :content="message.content"
              />
              <p v-else>{{ message.content }}</p>
              <StatusPill
                v-if="message.role === 'assistant' && message.retrievalStatus && message.retrievalStatus !== 'not_used'"
                :label="retrievalStatusLabel(message.retrievalStatus)"
                :state="retrievalStatusState(message.retrievalStatus)"
              />
              <div v-if="message.position_result" class="position-result-card">
                <button
                  v-if="message.position_result.annotated_image_url && !isPositionCaptureExpired(message.position_result)"
                  class="position-result-card__capture"
                  type="button"
                  :title="positionCaptureRetryExhausted(message.position_result) ? '截图暂时加载失败，点击重试' : '点击查看本轮定位大图'"
                  @click="positionCaptureRetryExhausted(message.position_result) ? retryPositionCapture(message.position_result) : openPositionCapture(message.position_result)"
                >
                  <img
                    v-if="!positionCaptureRetryExhausted(message.position_result)"
                    :src="positionCaptureImageSrc(message.position_result)"
                    :alt="message.position_result.selected ? `${message.position_result.selected.label} 定位标注图` : '本轮定位标注图'"
                    @error="handlePositionCaptureLoadError(message.position_result)"
                  />
                  <ImageOff v-else :size="18" />
                  <span v-if="positionCaptureRetryExhausted(message.position_result)">
                    本轮实时截图暂时加载失败 · 点击重试
                  </span>
                  <span v-else>本轮实时截图 · {{ formatDateTime(message.position_result.captured_at) }} · 点击放大</span>
                </button>
                <p
                  v-else-if="message.position_result.annotated_image_url"
                  class="position-result-card__capture-error"
                >
                  这张定位截图已超过 24 小时或后端已找不到文件，请重新查询目标位置。
                </p>
                <template v-if="message.position_result.selected">
                  <strong>{{ message.position_result.selected.label }} 定位结果</strong>
                  <span>镜头直线距离 {{ Math.round(message.position_result.selected.camera_range_mm) }} mm</span>
                  <span>A→B 平面距离 {{ Math.round(message.position_result.selected.ground_range_mm) }} mm</span>
                  <span>方位角 {{ message.position_result.selected.bearing_deg.toFixed(1) }}°</span>
                  <span>{{ positionStrategySummary(message.position_result) }}</span>
                  <details class="position-result-details">
                    <summary>定位详情</summary>
                    <dl>
                      <div>
                        <dt>AI 选择点</dt>
                        <dd>{{ positionAnchorTypeLabel(message.position_result.selected.anchor_type) }}</dd>
                      </div>
                      <div>
                        <dt>AI 高度估计</dt>
                        <dd>{{ Math.round(message.position_result.selected.estimated_height_mm) }} mm</dd>
                      </div>
                      <div>
                        <dt>实际计算高度</dt>
                        <dd>{{ Math.round(message.position_result.selected.effective_height_mm) }} mm</dd>
                      </div>
                      <div>
                        <dt>高度可信度</dt>
                        <dd>{{ Math.round(message.position_result.selected.height_confidence * 100) }}%</dd>
                      </div>
                    </dl>
                    <p>{{ message.position_result.selected.anchor_reason }}</p>
                  </details>
                </template>
                <template v-else-if="message.position_result.candidates.length">
                  <strong>发现 {{ message.position_result.candidates.length }} 个候选目标</strong>
                  <span v-for="candidate in message.position_result.candidates" :key="candidate.id">
                    {{ candidate.label }}：{{ Math.round(candidate.ground_range_mm) }} mm，{{ candidate.bearing_deg.toFixed(1) }}°
                  </span>
                </template>
              </div>
              <div v-if="message.referencesVerified === true && message.references?.length" class="reference-list">
                <strong>资料引用</strong>
                <template v-for="refItem in message.references" :key="`${message.id}-${referenceKey(refItem)}`">
                  <a v-if="refItem.url" :href="refItem.url" target="_blank" rel="noopener noreferrer">
                    {{ refItem.sourceName || '在线农业知识源' }}｜{{ refItem.title }}：{{ refItem.content }}
                  </a>
                  <span v-else>{{ refItem.title }}：{{ refItem.content }}</span>
                </template>
              </div>
              <div
                v-if="message.suggested_actions?.length && assistantHasVisibleActions(message.suggested_actions)"
                class="assistant-actions"
              >
                <strong>{{ assistantActionsHeading(message.suggested_actions) }}</strong>
                <div v-if="assistantReplyChoiceActions(message.suggested_actions).length" class="assistant-choice-list">
                  <button
                    v-for="action in assistantReplyChoiceActions(message.suggested_actions)"
                    :key="action.id"
                    class="assistant-choice-button"
                    type="button"
                    :disabled="chatSending || !!assistantExecutingActionId"
                    @click="selectAssistantReplyChoice(action)"
                  >
                    {{ actionPayloadText(action, 'choice_label', action.title) }}
                  </button>
                </div>
                <template v-for="action in message.suggested_actions" :key="action.id">
                  <article
                    v-if="action.type !== 'reply_choice'"
                    class="assistant-action-card"
                    :class="`assistant-action-card--${action.risk}`"
                  >
                    <div class="assistant-action-card__body">
                      <b>{{ action.title }}</b>
                      <span>{{ action.description || 'AI 建议执行该操作，确认后才会生效。' }}</span>
                      <em v-if="assistantActionStatusText(action)">{{ assistantActionStatusText(action) }}</em>
                    </div>
                    <div v-if="action.status === 'pending' || action.status === 'failed' || !action.status" class="assistant-action-card__buttons">
                      <button
                        class="primary-button"
                        type="button"
                        :disabled="assistantExecutingActionId === action.id"
                        @click="confirmAssistantAction(action)"
                      >
                        {{ assistantActionConfirmText(action) }}
                      </button>
                      <button class="text-button" type="button" @click="cancelAssistantAction(action)">取消</button>
                    </div>
                  </article>
                </template>
              </div>
            </article>
          </div>
          <button
            v-if="assistantShowScrollButton"
            class="assistant-scroll-bottom"
            type="button"
            title="回到最新消息"
            aria-label="回到最新消息"
            @click="scrollAssistantToBottom(true)"
          >
            <ArrowDown :size="18" />
          </button>
        </div>
        <div v-if="chatImageUrl" class="chat-attachment">
          <img :src="chatImageUrl" alt="待发送图片" />
          <span :title="chatImageFileName">{{ chatImageFileName }}</span>
          <button class="icon-button" type="button" title="移除图片" @click="clearChatImage">
            <X :size="16" />
          </button>
        </div>
        <p v-if="chatImageError" class="form-error assistant-image-error">{{ chatImageError }}</p>
        <p v-if="chatSendingStage !== 'idle'" class="assistant-send-stage">
          {{ chatSendingStage === 'vision' ? '正在识别图片…' : '正在结合识别结果生成回答…' }}
        </p>
        <div class="chat-composer assistant-composer">
          <label class="icon-button" title="上传图片">
            <Image :size="18" />
            <input type="file" accept="image/jpeg,image/png,image/webp" :disabled="chatSending" @change="handleChatImageUpload" />
          </label>
          <button class="icon-button" type="button" :title="listening ? '停止语音输入' : '语音输入'" @click="startVoiceInput">
            <Mic :class="{ pulsing: listening }" :size="18" />
          </button>
          <textarea
            ref="chatInputRef"
            v-model="chatInput"
            placeholder="输入问题或操作需求，执行控制前我会先请你确认。"
            @pointerdown="stopVoiceInputForTextEdit"
            @focus="stopVoiceInputForTextEdit"
            @keydown="handleChatKeydown"
          ></textarea>
          <button class="primary-button" type="button" :disabled="chatSending" @click="sendChat">
            <Send :size="18" />
            {{ chatSending ? '发送中' : '发送' }}
          </button>
        </div>
      </aside>
      <div v-if="assistantHistoryOpen" class="modal-backdrop" @click.self="assistantHistoryOpen = false">
        <section class="modal-card assistant-history-modal" role="dialog" aria-modal="true" aria-labelledby="assistant-history-title">
          <div class="modal-card__header">
            <div>
              <span>AI 助手</span>
              <h2 id="assistant-history-title">历史对话</h2>
            </div>
            <button class="icon-button" type="button" title="关闭" @click="assistantHistoryOpen = false">
              <X :size="18" />
            </button>
          </div>
          <div class="assistant-history-list">
            <article
              v-for="thread in sortedAssistantThreads"
              :key="thread.id"
              class="assistant-history-item"
              :class="{ 'assistant-history-item--active': thread.id === activeAssistantThreadId, 'assistant-history-item--pinned': thread.pinned }"
            >
              <button class="assistant-history-item__main" type="button" :disabled="chatSending" @click="switchAssistantThread(thread.id)">
                <strong>
                  <Pin v-if="thread.pinned" :size="14" />
                  {{ thread.title }}
                </strong>
                <span>{{ assistantThreadPreview(thread) }}</span>
                <time>{{ formatDateTime(thread.updated_at) }}</time>
              </button>
              <div v-if="renamingAssistantThreadId === thread.id" class="assistant-history-rename">
                <input
                  v-model="assistantThreadNameDraft"
                  placeholder="对话名称"
                  @keydown.enter.prevent="commitRenameAssistantThread(thread.id)"
                  @keydown.esc.prevent="resetAssistantThreadRename"
                />
                <button class="icon-button" type="button" title="保存名称" @click="commitRenameAssistantThread(thread.id)">
                  <Save :size="16" />
                </button>
                <button class="icon-button" type="button" title="取消" @click="resetAssistantThreadRename">
                  <X :size="16" />
                </button>
              </div>
              <div v-else class="assistant-history-actions">
                <button class="icon-button" type="button" :title="thread.pinned ? '取消置顶' : '置顶对话'" @click="toggleAssistantThreadPinned(thread.id)">
                  <Pin :size="16" />
                </button>
                <button class="icon-button" type="button" title="重命名" @click="beginRenameAssistantThread(thread)">
                  <Pencil :size="16" />
                </button>
                <button class="icon-button" type="button" title="删除" :disabled="chatSending" @click="deleteAssistantThread(thread.id)">
                  <Trash2 :size="16" />
                </button>
              </div>
            </article>
          </div>
        </section>
      </div>
      <div v-if="positionImageModal" class="modal-backdrop position-capture-modal" @click.self="closePositionCapture">
        <section class="modal-card position-capture-modal__card" role="dialog" aria-modal="true" aria-labelledby="position-capture-title">
          <div class="modal-card__header">
            <div>
              <span>AI 实时定位依据</span>
              <h2 id="position-capture-title">{{ positionImageModal.title }}</h2>
            </div>
            <button class="icon-button" type="button" title="关闭" @click="closePositionCapture">
              <X :size="18" />
            </button>
          </div>
          <img
            v-if="!isPositionCaptureExpired(positionImageModal.result) && !positionCaptureRetryExhausted(positionImageModal.result)"
            :src="positionCaptureImageSrc(positionImageModal.result)"
            :alt="positionImageModal.title"
            @error="handlePositionCaptureLoadError(positionImageModal.result)"
          />
          <button
            v-else-if="!isPositionCaptureExpired(positionImageModal.result)"
            class="position-result-card__capture"
            type="button"
            @click="retryPositionCapture(positionImageModal.result)"
          >
            <ImageOff :size="18" />
            <span>截图暂时加载失败，点击重试。</span>
          </button>
          <p v-else class="position-result-card__capture-error">定位截图已超过 24 小时或后端已找不到文件，请重新查询目标位置。</p>
          <p>拍摄时间：{{ formatDateTime(positionImageModal.capturedAt) }}。绿色框表示目标，红点表示 AI 为本轮几何计算选择的定位点。</p>
        </section>
      </div>
      <div v-if="waterGunStaticConfirmOpen" class="modal-backdrop" @click.self="waterGunStaticConfirmOpen = false">
        <section class="modal-card water-gun-confirm-modal" role="dialog" aria-modal="true" aria-labelledby="water-gun-static-title">
          <div class="modal-card__header">
            <div><span>目标确认</span><h2 id="water-gun-static-title">{{ waterGunSpraying && waterGunStaticDraftDirty ? '更改正在喷射的目标？' : '瞄准这个位置？' }}</h2></div>
            <button class="icon-button" type="button" title="关闭" @click="waterGunStaticConfirmOpen = false"><X :size="18" /></button>
          </div>
          <div class="water-gun-confirm-values">
            <strong>{{ Math.round(waterGunRangeMm) }} mm</strong>
            <strong>{{ waterGunBearingDeg.toFixed(1) }}°</strong>
          </div>
          <div v-if="waterGunSpraying && waterGunStaticDraftDirty" class="water-gun-risk-callout">
            <AlertTriangle :size="23" />
            <p>当前正处于喷水状态，是否更改至 {{ Math.round(waterGunRangeMm) }} mm、{{ waterGunBearingText }}？确认后水枪默认关闭，需重新设置喷射时间并开启。</p>
          </div>
          <div class="modal-card__actions">
            <button class="water-gun-modal-choice is-cancel" type="button" :disabled="waterGunBusy" @click="waterGunStaticConfirmOpen = false">取消</button>
            <button class="water-gun-modal-choice is-confirm" type="button" :disabled="waterGunBusy" @click="confirmWaterGunStaticTarget">{{ waterGunBusy ? '处理中…' : '确认' }}</button>
          </div>
        </section>
      </div>
      <div v-if="waterGunDynamicConfirmOpen" class="modal-backdrop" @click.self="waterGunDynamicConfirmOpen = false">
        <section class="modal-card water-gun-confirm-modal" role="dialog" aria-modal="true" aria-labelledby="water-gun-dynamic-title">
          <div class="modal-card__header">
            <div><span>风险确认</span><h2 id="water-gun-dynamic-title">进入动态模式？</h2></div>
            <button class="icon-button" type="button" title="关闭" @click="waterGunDynamicConfirmOpen = false"><X :size="18" /></button>
          </div>
          <div class="water-gun-risk-callout">
            <AlertTriangle :size="23" />
            <p>动态模式会持续改变瞄准位置，进入后默认关闭喷水，请确认周围安全。</p>
          </div>
          <div class="modal-card__actions">
            <button class="water-gun-modal-choice is-cancel" type="button" :disabled="waterGunBusy" @click="waterGunDynamicConfirmOpen = false">取消</button>
            <button class="water-gun-modal-choice is-confirm" type="button" :disabled="waterGunBusy" @click="confirmWaterGunDynamicStart">{{ waterGunBusy ? '启动中…' : '确认进入' }}</button>
          </div>
        </section>
      </div>
    </div>
  </div>
</template>
