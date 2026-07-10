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
  CloudSun,
  Cpu,
  Database,
  Droplets,
  Fan,
  Gauge,
  History,
  Home,
  Image,
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
  Sprout,
  Sun,
  Thermometer,
  ToggleLeft,
  Trash2,
  Upload,
  Wind,
  X,
} from '@lucide/vue';
import EChartPanel from './components/EChartPanel.vue';
import MetricCard from './components/MetricCard.vue';
import StatusPill from './components/StatusPill.vue';
import {
  addKnowledgeItem,
  analyzeDiseaseImage,
  analyzeFarm,
  analyzeKnowledge,
  createKnowledgeBase,
  deleteDiseasePhoto,
  deleteKnowledgeBase,
  deleteKnowledgeItem,
  getAlarmRecords,
  getDiseasePhotos,
  getDeviceHistory,
  getCurrentWeather,
  getKnowledgeBases,
  getKnowledgeItems,
  getLatestTelemetry,
  getPersistedDashboardState,
  savePersistedDashboardState,
  saveDiseasePhotoAnalysis,
  sendDeviceCommand,
  sendExpertChatMessage,
  updateKnowledgeBase,
  updateKnowledgeItem,
  uploadDiseasePhoto,
} from './services/api';
import type {
  AiAnalysisResponse,
  AlarmRecord,
  AssistantAction,
  AssistantThread,
  ChatMessage,
  CommandResult,
  DeviceCommand,
  DeviceRuntimeStatus,
  DiseaseDetectionResult,
  DiseasePhotoInfo,
  HistoryPoint,
  KnowledgeAnalyzeResult,
  KnowledgeBaseInfo,
  KnowledgeItemInfo,
  MetricTargetRange,
  PersistedDashboardState,
  SmartControlDecision,
  SmartControlDemands,
  SmartControlParamKey,
  SmartControlParamState,
  StatusLevel,
  TelemetryPayload,
  WeatherPayload,
} from './types';
import { formatDateTime, formatTime, numberText } from './utils/format';
import {
  applySmartControlOverrides,
  clampControlValue,
  cloneSmartControlDemands,
  computeSmartControlDecision,
  defaultSmartControlParamStates,
  smartControlParamColor,
  smartControlParamKeys,
  smartControlParamLabel,
  smartControlValueFromDemands,
  zeroSmartControlDemands,
} from './services/smartControl';

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
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onerror: (() => void) | null;
  onend: (() => void) | null;
}

type SpeechRecognitionConstructor = new () => SpeechRecognitionLike;

type HistoryMetricKey = 'temperature' | 'humidity' | 'light' | 'co2' | 'soil_moisture' | 'soil_ec' | 'gas_resistance';

interface HistoryMetricDefinition {
  key: HistoryMetricKey;
  name: string;
  unit: string;
  color: string;
  value: (point: HistoryPoint) => number;
}

interface SmartControlParamVm {
  key: SmartControlParamKey;
  label: string;
  color: string;
  mode: 'auto' | 'manual';
  value: number;
  autoValue: number;
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

const historyMetricDefinitions: HistoryMetricDefinition[] = [
  { key: 'temperature', name: '温度', unit: '摄氏度', color: '#D68C1F', value: (point) => point.temperature },
  { key: 'humidity', name: '湿度', unit: '%RH', color: '#2C7DA0', value: (point) => point.humidity },
  { key: 'light', name: '光照', unit: 'lux', color: '#E6B325', value: (point) => point.light },
  { key: 'co2', name: 'CO2', unit: 'ppm', color: '#7A5CFA', value: (point) => point.co2 },
  { key: 'soil_moisture', name: '土壤湿度', unit: '%', color: '#2F8F4E', value: (point) => point.soil_moisture },
  { key: 'soil_ec', name: 'EC', unit: 'mS/cm', color: '#8A6A47', value: (point) => point.soil_ec },
  { key: 'gas_resistance', name: '空气质量', unit: 'Ω', color: '#53645A', value: (point) => point.gas_resistance },
];

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

function isSmartControlParamKey(value: unknown): value is SmartControlParamKey {
  return typeof value === 'string' && smartControlParamKeys.includes(value as SmartControlParamKey);
}

const activeView = ref<ViewKey>('overview');
const latest = ref<TelemetryPayload | null>(null);
const currentWeather = ref<WeatherPayload | null>(null);
const historyPoints = ref<HistoryPoint[]>([]);
const aiAnalysis = ref<AiAnalysisResponse | null>(null);
const alarms = ref<AlarmRecord[]>([]);
const commandResults = ref<CommandResult[]>([]);
const diseaseResult = ref<DiseaseDetectionResult | null>(null);
const diseaseImageUrl = ref('');
const diseaseLoading = ref(false);
const diseaseUploadError = ref('');
const diseasePhotoLibraryOpen = ref(false);
const diseasePhotos = ref<DiseasePhotoInfo[]>([]);
const selectedDiseasePhoto = ref<DiseasePhotoInfo | null>(null);
const currentDiseasePhotoId = ref<number | null>(null);
const diseasePhotoLoading = ref(false);
const diseasePhotoDeletingId = ref<number | null>(null);
const diseasePhotoError = ref('');
const chatMessages = ref<ChatMessage[]>([]);
const assistantThreads = ref<AssistantThread[]>([]);
const activeAssistantThreadId = ref('');
const assistantHistoryOpen = ref(false);
const renamingAssistantThreadId = ref('');
const assistantThreadNameDraft = ref('');
const chatInput = ref('番茄叶片有黄斑，结合当前环境应该怎么处理？');
const chatInputRef = ref<HTMLTextAreaElement | null>(null);
const chatImageUrl = ref('');
const chatImageFileName = ref('');
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
const assistantConfirmActionId = ref<string | null>(null);
const assistantExecutingActionId = ref<string | null>(null);
const smartControlPanelOpen = ref(false);
const smartControlEnabled = ref(true);
const smartControlAutoDemands = ref<SmartControlDemands>(cloneSmartControlDemands(zeroSmartControlDemands));
const smartControlEffectiveDemands = ref<SmartControlDemands>(cloneSmartControlDemands(zeroSmartControlDemands));
const smartControlDecision = ref<SmartControlDecision | null>(null);
const smartControlLastPublishAt = ref<number | null>(null);
const smartControlParamStates = ref<Record<SmartControlParamKey, SmartControlParamState>>(defaultSmartControlParamStates());
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
let metricEditorLastSourceRect: MetricEditorSourceRect | null = null;
const metricEditorSourceRects = new Map<HistoryMetricKey, MetricEditorSourceRect>();
let persistedDeviceStatus: DeviceRuntimeStatus | null = null;
let persistentStateReady = false;
let applyingPersistentState = false;
let persistentStateSaveTimer: number | undefined;

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
const activeAlarms = computed(() => alarms.value.filter((item) => !item.handled).length);
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
const selectedDiseasePhotoAnalysis = computed(() => diseasePhotoAnalysis(selectedDiseasePhoto.value));

const statusSummary = computed<Array<{ label: string; state: StatusLevel }>>(() => {
  const status = latest.value?.status;
  if (!status) {
    return [];
  }
  return [
    { label: `Wi-Fi ${status.wifi === 'connected' ? '已连接' : '异常'}`, state: status.wifi === 'connected' ? 'good' : 'danger' },
    { label: `MQTT ${status.mqtt === 'connected' ? '在线' : '离线'}`, state: status.mqtt === 'connected' ? 'good' : 'danger' },
    { label: status.fan ? '风机运行' : '风机待机', state: status.fan ? 'watch' : 'neutral' },
    { label: status.pump ? '水泵运行' : '水泵待机', state: status.pump ? 'watch' : 'neutral' },
    { label: status.light ? '补光开启' : '补光关闭', state: status.light ? 'watch' : 'neutral' },
    { label: status.curtain ? '卷帘打开' : '卷帘关闭', state: status.curtain ? 'good' : 'neutral' },
    { label: status.alarm ? '报警器开启' : '报警器关闭', state: status.alarm ? 'danger' : 'neutral' },
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
      hint: metricHint(status.kind, definition.key),
      state: status.state,
      icon: metricIcon(definition.key),
      color: definition.color,
      currentValue,
      statusLabel: status.label,
      targetText: `目标 ${range.min}-${range.max} ${definition.unit}`,
      trendText: metricTrendText(definition),
      aiInsight: metricAiInsight(status.kind, definition.key),
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
    return 'AI 未连接';
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
    return { label: 'AI 未连接', state: 'neutral' };
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

const smartControlParams = computed<SmartControlParamVm[]>(() => smartControlParamKeys.map((key) => {
  const state = smartControlParamStates.value[key];
  return {
    key,
    label: smartControlParamLabel(key),
    color: smartControlParamColor(key),
    mode: state.mode,
    value: smartControlValueFromDemands(key, smartControlEffectiveDemands.value),
    autoValue: smartControlValueFromDemands(key, smartControlAutoDemands.value),
  };
}));

const smartControlStatusState = computed<StatusLevel>(() => {
  if (!smartControlEnabled.value) {
    return 'neutral';
  }
  if (smartControlDecision.value?.riskLevel === 'urgent') {
    return 'danger';
  }
  if (smartControlDecision.value?.riskLevel === 'watch') {
    return 'watch';
  }
  return 'good';
});

const selectedMetricChartOption = computed<EChartsOption>(() => metricChartOptionFor(selectedMetricDefinition.value));

function metricChartOptionFor(metric: HistoryMetricDefinition | null): EChartsOption {
  if (!metric) {
    return {};
  }
  const labels = historyPoints.value.map((point) => formatTime(point.timestamp));
  const values = historyPoints.value.map(metric.value);
  const range = historyAxisRange(values);
  return {
    tooltip: { trigger: 'axis' },
    grid: { left: 58, right: 24, top: 34, bottom: 30 },
    xAxis: { type: 'category', boundaryGap: false, data: labels },
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
      data: values,
      color: metric.color,
      lineStyle: { width: 3, color: metric.color },
      itemStyle: { color: '#ffffff', borderColor: metric.color, borderWidth: 2 },
      emphasis: { focus: 'series', scale: 1.2 },
    }],
  };
}

const overviewChartOption = computed<EChartsOption>(() => buildMultiMetricChartOption(false));
const historyChartOption = computed<EChartsOption>(() => buildMultiMetricChartOption(true));
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
  const labels = historyPoints.value.map((point) => formatTime(point.timestamp));
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
    xAxis: { type: 'category', boundaryGap: false, data: labels },
    yAxis: selectedDefinitions.map((definition, index) => {
      const values = historyPoints.value.map(definition.value);
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
      data: historyPoints.value.map(definition.value),
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

function historyAxisRange(values: number[]): { min: number; max: number } {
  if (values.length === 0) {
    return { min: 0, max: 1 };
  }
  const minValue = Math.min(...values);
  const maxValue = Math.max(...values);
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

function isDeviceRuntimeStatus(value: unknown): value is DeviceRuntimeStatus {
  return isPlainRecord(value)
    && (value.wifi === 'connected' || value.wifi === 'disconnected' || value.wifi === 'warning')
    && (value.mqtt === 'connected' || value.mqtt === 'disconnected' || value.mqtt === 'warning')
    && typeof value.fan === 'number'
    && typeof value.pump === 'number'
    && typeof value.light === 'number'
    && typeof value.alarm === 'number'
    && typeof value.curtain === 'number';
}

function mergePersistedDeviceStatus(payload: TelemetryPayload): TelemetryPayload {
  if (!persistedDeviceStatus) {
    return payload;
  }
  return {
    ...payload,
    status: {
      ...payload.status,
      fan: persistedDeviceStatus.fan,
      pump: persistedDeviceStatus.pump,
      light: persistedDeviceStatus.light,
      alarm: persistedDeviceStatus.alarm,
      curtain: persistedDeviceStatus.curtain,
    },
  };
}

function statusAfterCommand(status: DeviceRuntimeStatus, command: string, value: number): DeviceRuntimeStatus {
  const nextStatus = { ...status };
  if (command.startsWith('fan_')) {
    nextStatus.fan = value;
  }
  if (command.startsWith('pump_')) {
    nextStatus.pump = value;
  }
  if (command.startsWith('light_')) {
    nextStatus.light = value;
  }
  if (command.startsWith('alarm_')) {
    nextStatus.alarm = value;
  }
  if (command.startsWith('curtain_')) {
    nextStatus.curtain = value;
  }
  return nextStatus;
}

function persistedSmartControlParamStates(value: unknown): Record<SmartControlParamKey, SmartControlParamState> {
  const states = defaultSmartControlParamStates();
  if (!isPlainRecord(value)) {
    return states;
  }
  smartControlParamKeys.forEach((key) => {
    const item = value[key];
    if (!isPlainRecord(item)) {
      return;
    }
    const mode = item.mode === 'manual' ? 'manual' : 'auto';
    const rawValue = typeof item.value === 'number' ? item.value : 0;
    const rawLastManualValue = typeof item.lastManualValue === 'number' ? item.lastManualValue : rawValue;
    states[key] = {
      key,
      mode,
      value: clampControlValue(rawValue),
      lastManualValue: clampControlValue(rawLastManualValue),
    };
  });
  return states;
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
    metricTargetRanges: metricTargetRanges.value,
    deviceStatus: latest.value?.status ?? persistedDeviceStatus ?? undefined,
    commandResults: commandResults.value.slice(0, 10),
    smartControlEnabled: smartControlEnabled.value,
    smartControlParamStates: smartControlParamStates.value,
    smartControlLastPublishAt: smartControlLastPublishAt.value,
    smartControlPanelOpen: smartControlPanelOpen.value,
    selectedKbId: selectedKbId.value,
    knowledgeQuestion: knowledgeQuestion.value,
    knowledgeAnswer: knowledgeAnswer.value,
    assistantOpen: assistantOpen.value,
    assistantWidth: assistantWidth.value,
    chatInput: chatInput.value,
    chatMessages: serializableChatMessages(),
    assistantThreads: serializableAssistantThreads(),
    activeAssistantThreadId: activeAssistantThreadId.value,
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
    if (Array.isArray(state.selectedHistoryMetricKeys)) {
      const historyKeys = state.selectedHistoryMetricKeys.filter((key): key is HistoryMetricKey => (
        typeof key === 'string' && historyMetricDefinitions.some((definition) => definition.key === key)
      ));
      if (historyKeys.length > 0) {
        selectedHistoryMetricKeys.value = historyKeys;
      }
    }
    metricTargetRanges.value = persistedMetricTargetRanges(state.metricTargetRanges);
    if (isDeviceRuntimeStatus(state.deviceStatus)) {
      persistedDeviceStatus = state.deviceStatus;
    }
    if (Array.isArray(state.commandResults)) {
      commandResults.value = state.commandResults.slice(0, 10);
    }
    if (typeof state.smartControlEnabled === 'boolean') {
      smartControlEnabled.value = state.smartControlEnabled;
    }
    smartControlParamStates.value = persistedSmartControlParamStates(state.smartControlParamStates);
    if (typeof state.smartControlLastPublishAt === 'number' || state.smartControlLastPublishAt === null) {
      smartControlLastPublishAt.value = state.smartControlLastPublishAt;
    }
    if (typeof state.smartControlPanelOpen === 'boolean') {
      smartControlPanelOpen.value = state.smartControlPanelOpen;
    }
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
    return 0;
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
    return 'CO2 浓度';
  }
  if (key === 'soil_moisture') {
    return '土壤湿度';
  }
  if (key === 'soil_ec') {
    return '土壤 EC';
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
    return Sprout;
  }
  if (key === 'soil_ec') {
    return Gauge;
  }
  return Leaf;
}

function metricValueText(key: HistoryMetricKey, value: number): string {
  if (key === 'soil_ec') {
    return numberText(value, 2);
  }
  if (key === 'temperature' || key === 'humidity' || key === 'soil_moisture') {
    return numberText(value);
  }
  return String(Math.round(value));
}

function metricTargetStatus(value: number, range: MetricTargetRange): { kind: 'high' | 'low' | 'normal'; label: string; state: 'danger' | 'low' | 'good' } {
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
  if (historyPoints.value.length < 2) {
    return '等待更多采样';
  }
  const current = definition.value(historyPoints.value[historyPoints.value.length - 1]);
  const previous = definition.value(historyPoints.value[historyPoints.value.length - 2]);
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
  syncSmartControlValues();
  await savePersistentDashboardStateNow();
  targetRangeSaving.value = false;
  targetRangeSavedMessage.value = `已保存：${min} - ${max} ${selectedMetricDefinition.value?.unit ?? ''}`.trim();
  if (targetRangeSavedTimer) {
    window.clearTimeout(targetRangeSavedTimer);
  }
  targetRangeSavedTimer = window.setTimeout(() => {
    targetRangeSavedMessage.value = '';
    targetRangeSavedTimer = undefined;
  }, 2200);
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

watch(activeView, (view) => {
  if (view !== 'realtime') {
    closeMetricEditor();
  }
  schedulePersistentDashboardStateSave();
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

watch(smartControlPanelOpen, () => {
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

function setKnowledgeError(action: string, error: unknown): void {
  const message = error instanceof Error ? error.message : '未知错误';
  knowledgeError.value = `${action}失败：${message}`;
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

async function loadDashboard(isBackground = false): Promise<void> {
  if (isBackground) {
    refreshing.value = true;
  } else {
    loading.value = true;
  }
  try {
    const nextLatest = mergePersistedDeviceStatus(await getLatestTelemetry());
    latest.value = nextLatest;
    const [historyResult, aiResult, alarmsResult, weatherResult] = await Promise.allSettled([
      getDeviceHistory(),
      analyzeFarm(nextLatest),
      getAlarmRecords(),
      getCurrentWeather(),
    ]);
    if (historyResult.status === 'fulfilled') {
      historyPoints.value = historyResult.value;
    } else {
      console.warn('History data failed to load.', historyResult.reason);
    }
    if (aiResult.status === 'fulfilled') {
      aiAnalysis.value = aiResult.value;
    } else {
      console.warn('AI analysis failed to load.', aiResult.reason);
    }
    if (alarmsResult.status === 'fulfilled') {
      alarms.value = alarmsResult.value;
    } else {
      console.warn('Alarm records failed to load.', alarmsResult.reason);
    }
    if (weatherResult.status === 'fulfilled') {
      currentWeather.value = weatherResult.value;
    } else {
      console.warn('Weather data failed to load.', weatherResult.reason);
    }
    syncSmartControlValues();
  } finally {
    loading.value = false;
    refreshing.value = false;
  }
}

async function applyCommand(command: string, value: number, reason: string): Promise<void> {
  if (!latest.value) {
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

function syncSmartControlValues(): void {
  if (!latest.value) {
    return;
  }
  const decision = computeSmartControlDecision(
    latest.value,
    historyPoints.value,
    metricTargetRanges.value,
    currentWeather.value,
    smartControlAutoDemands.value,
  );
  smartControlDecision.value = decision;
  smartControlAutoDemands.value = cloneSmartControlDemands(decision.demands);
  smartControlEffectiveDemands.value = smartControlEnabled.value
    ? applySmartControlOverrides(decision.demands, smartControlParamStates.value)
    : cloneSmartControlDemands(zeroSmartControlDemands);
}

function buildSmartControlCommand(action: 'smart_control_update' | 'smart_control_stop', demands: SmartControlDemands, reason: string): DeviceCommand {
  if (!latest.value) {
    throw new Error('No telemetry available');
  }
  const safeDemands = cloneSmartControlDemands(demands);
  const tempDemand = safeDemands.heat > 0 ? safeDemands.heat : -safeDemands.cool;
  const timestamp = Date.now();
  return {
    device_id: latest.value.device_id,
    command: action,
    value: action === 'smart_control_stop' ? 0 : 1,
    reason,
    action,
    fieldId: latest.value.device_id,
    fieldName: '智慧大棚',
    source: 'web_smart_control',
    demands: safeDemands,
    waterDemand: safeDemands.water,
    lightDemand: safeDemands.light,
    heatDemand: safeDemands.heat,
    coolDemand: safeDemands.cool,
    ventDemand: safeDemands.vent,
    co2Demand: safeDemands.co2,
    tempDemand,
    airDemand: safeDemands.vent,
    mistDemand: safeDemands.co2,
    timestamp,
  };
}

async function publishSmartControl(reason: string, action: 'smart_control_update' | 'smart_control_stop' = 'smart_control_update'): Promise<void> {
  if (!latest.value) {
    return;
  }
  const demands = action === 'smart_control_stop'
    ? cloneSmartControlDemands(zeroSmartControlDemands)
    : smartControlEffectiveDemands.value;
  const result = await sendDeviceCommand(buildSmartControlCommand(action, demands, reason));
  const nextStatus = { ...latest.value.status };
  const normalizedResult = { ...result, status: nextStatus };
  persistedDeviceStatus = nextStatus;
  commandResults.value = [normalizedResult, ...commandResults.value].slice(0, 10);
  smartControlLastPublishAt.value = result.executed_at;
  latest.value = {
    ...latest.value,
    timestamp: result.executed_at,
    status: nextStatus,
  };
  void savePersistentDashboardStateNow();
}

async function setSmartControlEnabled(enabled: boolean): Promise<void> {
  smartControlEnabled.value = enabled;
  syncSmartControlValues();
  await publishSmartControl(enabled ? '开启智能托管' : '关闭智能托管', enabled ? 'smart_control_update' : 'smart_control_stop');
}

async function setSmartParamManual(key: SmartControlParamKey): Promise<void> {
  const current = smartControlParamStates.value[key];
  const initialValue = current.lastManualValue > 0 ? current.lastManualValue : smartControlValueFromDemands(key, smartControlEffectiveDemands.value);
  smartControlEnabled.value = true;
  smartControlParamStates.value = {
    ...smartControlParamStates.value,
    [key]: {
      key,
      mode: 'manual',
      value: clampControlValue(initialValue),
      lastManualValue: clampControlValue(initialValue),
    },
  };
  syncSmartControlValues();
  await publishSmartControl(`${smartControlParamLabel(key)}切换手动`);
}

async function updateSmartParamManualValue(key: SmartControlParamKey, value: number): Promise<void> {
  const current = smartControlParamStates.value[key];
  if (current.mode !== 'manual') {
    return;
  }
  const safeValue = clampControlValue(value);
  smartControlParamStates.value = {
    ...smartControlParamStates.value,
    [key]: {
      ...current,
      value: safeValue,
      lastManualValue: safeValue,
    },
  };
  syncSmartControlValues();
  await publishSmartControl(`${smartControlParamLabel(key)}手动值调整`);
}

function handleSmartParamSliderChange(key: SmartControlParamKey, event: Event): void {
  const input = event.target as HTMLInputElement;
  void updateSmartParamManualValue(key, Number(input.value));
}

async function restoreSmartParamAuto(key: SmartControlParamKey): Promise<void> {
  const current = smartControlParamStates.value[key];
  const autoValue = smartControlValueFromDemands(key, smartControlAutoDemands.value);
  smartControlEnabled.value = true;
  smartControlParamStates.value = {
    ...smartControlParamStates.value,
    [key]: {
      ...current,
      mode: 'auto',
      value: autoValue,
    },
  };
  syncSmartControlValues();
  await publishSmartControl(`${smartControlParamLabel(key)}恢复自动`);
}

async function toggleSmartParamMode(key: SmartControlParamKey): Promise<void> {
  if (smartControlParamStates.value[key].mode === 'manual') {
    await restoreSmartParamAuto(key);
    return;
  }
  await setSmartParamManual(key);
}

async function setAllSmartParamsAuto(): Promise<void> {
  const nextStates = defaultSmartControlParamStates();
  smartControlParamKeys.forEach((key) => {
    const current = smartControlParamStates.value[key];
    nextStates[key] = {
      ...current,
      mode: 'auto',
      value: smartControlValueFromDemands(key, smartControlAutoDemands.value),
    };
  });
  smartControlEnabled.value = true;
  smartControlParamStates.value = nextStates;
  syncSmartControlValues();
  await publishSmartControl('一键自动托管');
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
  const command = result.command;
  if (command.command === 'smart_control_update') {
    const labelsText = smartControlParamKeys.map((key) => smartControlParamLabel(key)).join('、');
    if (command.reason === '一键自动托管') {
      return `已恢复${labelsText}的自动调控，远程设备开关保持当前状态。`;
    }
    if (command.reason === '开启智能托管') {
      return `已打开${labelsText}的托管自动调控，远程设备开关保持当前状态。`;
    }
    if (command.reason.endsWith('切换手动')) {
      const label = smartControlReasonLabel(command.reason, '切换手动');
      return `已关闭${label}托管自动调控，可手动设置控制值。`;
    }
    if (command.reason.endsWith('恢复自动')) {
      const label = smartControlReasonLabel(command.reason, '恢复自动');
      return `已打开${label}托管自动调控，将按环境变化自动更新。`;
    }
    if (command.reason.endsWith('手动值调整')) {
      const label = smartControlReasonLabel(command.reason, '手动值调整');
      return `已更新${label}手动控制值，设备开关状态保持不变。`;
    }
    return '已更新自动调控参数，远程设备开关保持当前状态。';
  }
  if (command.command === 'smart_control_stop') {
    return '已关闭全部托管自动调控，远程设备开关保持当前状态。';
  }
  return command.reason || (result.success ? '设备状态已更新。' : result.message);
}

function smartControlReasonLabel(reason: string, suffix: string): string {
  return reason.endsWith(suffix) ? reason.slice(0, -suffix.length) : '';
}

function commandActionText(command: DeviceCommand): string {
  if (command.command === 'smart_control_update') {
    if (command.reason === '一键自动托管') {
      return '一键自动托管已应用';
    }
    if (command.reason === '开启智能托管') {
      return '打开智能托管自动调控';
    }
    const manualLabel = smartControlReasonLabel(command.reason, '切换手动');
    if (manualLabel) {
      return `关闭${manualLabel}托管自动调控`;
    }
    const autoLabel = smartControlReasonLabel(command.reason, '恢复自动');
    if (autoLabel) {
      return `打开${autoLabel}托管自动调控`;
    }
    const adjustedLabel = smartControlReasonLabel(command.reason, '手动值调整');
    if (adjustedLabel) {
      return `调整${adjustedLabel}手动控制值`;
    }
    return '自动调控参数已更新';
  }
  if (command.command === 'smart_control_stop') {
    return '关闭全部托管自动调控';
  }
  const labels: Record<string, string> = {
    fan_on: '打开风机',
    fan_off: '关闭风机',
    pump_on: '打开水泵',
    pump_off: '关闭水泵',
    light_on: '打开补光灯',
    light_off: '关闭补光灯',
    curtain_open: '打开卷帘',
    curtain_close: '关闭卷帘',
    alarm_on: '打开报警器',
    alarm_off: '关闭报警器',
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

function actionPayloadText(action: AssistantAction, key: string, fallback = ''): string {
  const value = action.payload[key];
  return typeof value === 'string' && value.trim().length > 0 ? value.trim() : fallback;
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
  if (action.risk === 'high' && assistantConfirmActionId.value !== action.id) {
    return '确认操作';
  }
  if (action.risk === 'high') {
    return '再次确认';
  }
  return '确认执行';
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
  try {
    if (action.type === 'navigate_view') {
      const view = actionPayloadText(action, 'view');
      if (!isViewKey(view)) {
        throw new Error('未知页面');
      }
      activeView.value = view;
    } else if (action.type === 'open_panel') {
      const panel = actionPayloadText(action, 'panel');
      if (panel === 'smart_control') {
        activeView.value = 'control';
        smartControlPanelOpen.value = true;
      } else if (panel === 'knowledge') {
        activeView.value = 'knowledge';
      } else if (panel === 'disease_upload') {
        activeView.value = 'disease';
      } else {
        assistantOpen.value = true;
      }
    } else if (action.type === 'refresh_data') {
      await loadDashboard(true);
    } else if (action.type === 'device_command') {
      await applyCommand(
        actionPayloadText(action, 'command'),
        actionPayloadNumber(action, 'value', 1),
        actionPayloadText(action, 'reason', 'AI助手建议执行设备控制'),
      );
    } else if (action.type === 'smart_control') {
      const operation = actionPayloadText(action, 'operation');
      const keyText = actionPayloadText(action, 'key');
      if (operation === 'enable') {
        await setSmartControlEnabled(true);
      } else if (operation === 'disable') {
        await setSmartControlEnabled(false);
      } else if (operation === 'all_auto') {
        await setAllSmartParamsAuto();
      } else if (operation === 'open_panel') {
        activeView.value = 'control';
        smartControlPanelOpen.value = true;
      } else if (isSmartControlParamKey(keyText)) {
        if (operation === 'set_manual') {
          await setSmartParamManual(keyText);
        } else if (operation === 'update_manual') {
          if (smartControlParamStates.value[keyText].mode !== 'manual') {
            await setSmartParamManual(keyText);
          }
          await updateSmartParamManualValue(keyText, actionPayloadNumber(action, 'value', 0));
        } else if (operation === 'restore_auto') {
          await restoreSmartParamAuto(keyText);
        } else {
          throw new Error('未知托管操作');
        }
      } else {
        throw new Error('未知托管参数');
      }
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
    assistantConfirmActionId.value = null;
    setAssistantActionStatus(action, 'executed');
  } catch (error) {
    const message = error instanceof Error ? error.message : '执行失败';
    setAssistantActionStatus(action, 'failed', message);
  } finally {
    assistantExecutingActionId.value = null;
  }
}

async function confirmAssistantAction(action: AssistantAction): Promise<void> {
  if (action.status !== 'pending' && action.status !== 'failed' && action.status !== undefined) {
    return;
  }
  if (action.risk === 'high' && assistantConfirmActionId.value !== action.id) {
    assistantConfirmActionId.value = action.id;
    return;
  }
  await executeAssistantAction(action);
}

function cancelAssistantAction(action: AssistantAction): void {
  assistantConfirmActionId.value = assistantConfirmActionId.value === action.id ? null : assistantConfirmActionId.value;
  setAssistantActionStatus(action, 'canceled');
}

function errorText(error: unknown): string {
  return error instanceof Error ? error.message : '未知错误';
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
  currentDiseasePhotoId.value = photo.photoId;
  revokeCurrentDiseaseBlob();
  diseaseImageUrl.value = photo.url;
  diseaseResult.value = diseasePhotoAnalysis(photo);
  diseaseUploadError.value = diseaseResult.value ? '' : '这张图片还没有保存识别结果，可以重新上传或重新分析后保存。';
}

async function processDiseaseFile(file: File): Promise<void> {
  revokeCurrentDiseaseBlob();
  const previewUrl = URL.createObjectURL(file);
  diseaseImageUrl.value = previewUrl;
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

async function handleDiseaseUpload(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) {
    return;
  }
  try {
    await processDiseaseFile(file);
  } finally {
    input.value = '';
  }
}

function clearDiseaseImage(): void {
  revokeCurrentDiseaseBlob();
  diseaseImageUrl.value = '';
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

function handleChatImageUpload(event: Event): void {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) {
    return;
  }
  if (chatImageUrl.value.startsWith('blob:')) {
    URL.revokeObjectURL(chatImageUrl.value);
  }
  chatImageUrl.value = URL.createObjectURL(file);
  chatImageFileName.value = file.name;
  input.value = '';
}

function clearChatImage(): void {
  if (chatImageUrl.value.startsWith('blob:')) {
    URL.revokeObjectURL(chatImageUrl.value);
  }
  chatImageUrl.value = '';
  chatImageFileName.value = '';
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
    assistantConfirmActionId.value = null;
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
  assistantConfirmActionId.value = null;
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
  assistantConfirmActionId.value = null;
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

async function sendChat(): Promise<void> {
  if (!latest.value || chatSending.value) {
    return;
  }
  const question = chatInput.value.trim();
  if (question.length === 0 && chatImageUrl.value.length === 0) {
    return;
  }
  const pendingImageUrl = chatImageUrl.value;
  stopVoiceInputAfterSend();
  clearChatComposerInput();
  const userMessage: ChatMessage = {
    id: `user-${Date.now()}`,
    role: 'user',
    content: question || '请分析这张作物图片。',
    image_url: pendingImageUrl || undefined,
    created_at: Date.now(),
  };
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
    const response = await sendExpertChatMessage({
      question: userMessage.content,
      image_url: pendingImageUrl || undefined,
      latest: latest.value,
      disease: diseaseResult.value,
      knowledge_base_id: selectedKbId.value || undefined,
      current_view: activeView.value,
      knowledge_bases: knowledgeBases.value,
      knowledge_items: knowledgeItems.value,
      command_results: commandResults.value,
    });
    const shouldFollowResponse = assistantAtBottom.value;
    await revealAssistantMessage(response.message, thinkingMessage.id, shouldFollowResponse);
    clearChatImage();
  } catch (error) {
    const message = error instanceof Error ? error.message : '未知错误';
    const shouldFollowResponse = assistantAtBottom.value;
    await revealAssistantMessage(
      {
        id: `assistant-error-${Date.now()}`,
        role: 'assistant',
        content: `AI助手暂时没有连上后端服务。\n请确认 FastAPI 后端已启动，并且 http://localhost:8000/api/v1/health 可以访问。\n错误信息：${message}`,
        created_at: Date.now(),
      },
      thinkingMessage.id,
      shouldFollowResponse,
    );
  } finally {
    stopAssistantThinking();
    chatSending.value = false;
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
    input.focus();
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

function stopBrowserSpeechInput(): void {
  const recognition = activeBrowserSpeechRecognition;
  activeBrowserSpeechRecognition = null;
  if (!recognition) {
    return;
  }
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
  };
  recognition.onerror = () => {
    voiceRecognitionHadError = true;
    voiceMessage.value = '浏览器语音输入失败，请检查麦克风权限或输入设备。';
    listening.value = false;
    activeBrowserSpeechRecognition = null;
  };
  recognition.onend = () => {
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
    voiceMessage.value = '正在启动浏览器实时语音输入...';
    return true;
  } catch (error) {
    const message = error instanceof Error ? error.message : '未知错误';
    voiceMessage.value = `浏览器语音输入启动失败：${message}`;
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
  if (latest.value) {
    latest.value = mergePersistedDeviceStatus(latest.value);
    syncSmartControlValues();
  }
  await loadDashboard();
  void refreshKnowledge(selectedKbId.value);
  persistentStateReady = true;
  void stateLoad.then(() => {
    if (latest.value) {
      latest.value = mergePersistedDeviceStatus(latest.value);
      syncSmartControlValues();
    }
    void refreshKnowledge(selectedKbId.value);
  });
}

function persistDashboardBeforeUnload(): void {
  void savePersistentDashboardStateNow();
}

onMounted(() => {
  ensureAssistantThreadState();
  void initializeDashboard();
  window.addEventListener('resize', handleAssistantViewportResize);
  window.addEventListener('beforeunload', persistDashboardBeforeUnload);
  refreshTimer = window.setInterval(() => {
    void loadDashboard(true);
  }, 5000);
});

onBeforeUnmount(() => {
  if (persistentStateSaveTimer) {
    window.clearTimeout(persistentStateSaveTimer);
    persistentStateSaveTimer = undefined;
  }
  stopAssistantResize();
  window.removeEventListener('resize', handleAssistantViewportResize);
  window.removeEventListener('beforeunload', persistDashboardBeforeUnload);
  if (refreshTimer) {
    window.clearInterval(refreshTimer);
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
          <strong>ESP32-C5</strong>
          <span>智慧农业 Web</span>
        </div>
      </div>

      <nav class="nav-list" aria-label="页面导航">
        <button
          v-for="item in navItems"
          :key="item.key"
          class="nav-item"
          :class="{ 'nav-item--active': activeView === item.key }"
          type="button"
          @click="activeView = item.key"
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
          <StatusPill v-if="latest" :label="latest.device_id" state="neutral" />
          <StatusPill :label="`${activeAlarms} 条未处理报警`" :state="activeAlarms > 0 ? 'watch' : 'good'" />
          <button class="icon-button" type="button" title="刷新数据" @click="loadDashboard(true)">
            <RefreshCw :class="{ spinning: refreshing }" :size="19" />
          </button>
        </div>
      </header>

      <section v-if="loading" class="loading-panel">
        <Activity :size="34" />
        <span>正在读取设备遥测数据...</span>
      </section>

      <template v-else-if="latest">
        <section v-show="activeView === 'overview'" class="view-stack">
          <div class="hero-panel">
            <div class="hero-panel__copy">
              <p class="eyebrow">端云协同状态</p>
              <h2>设备正在上报温湿度、光照、CO2、土壤湿度和 EC 数据</h2>
              <p>最近采样 {{ formatDateTime(latest.timestamp) }}，系统持续跟踪环境变化、作物健康和设备运行状态。</p>
              <div class="hero-status-list">
                <StatusPill v-for="item in statusSummary" :key="item.label" :label="item.label" :state="item.state" />
              </div>
            </div>
            <div class="hero-panel__status">
              <article v-if="currentWeather" class="weather-card">
                <div>
                  <CloudSun :size="28" />
                  <span>{{ currentWeather.location }}</span>
                </div>
                <strong>{{ currentWeather.condition }} · {{ currentWeather.temperature }} 摄氏度</strong>
                <p>湿度 {{ currentWeather.humidity }}%，{{ currentWeather.wind_direction }} {{ currentWeather.wind_level }}</p>
                <time>更新 {{ formatDateTime(currentWeather.updated_at) }}</time>
              </article>
            </div>
          </div>

          <div class="metric-grid metric-grid--wide">
            <MetricCard
              v-for="metric in overviewMetricCards"
              :key="metric.title"
              :title="metric.title"
              :value="metric.value"
              :unit="metric.unit"
              :hint="metric.hint"
              :state="metric.state"
              :icon="metric.icon"
            />
          </div>

          <div class="two-column">
            <EChartPanel title="近 6 小时环境趋势" :option="overviewChartOption" :active="activeView === 'overview'" :min-width="multiMetricChartMinWidth">
              <template #toolbar>
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
              </template>
            </EChartPanel>
            <section class="panel">
              <div class="section-heading">
                <h2>AI 摘要</h2>
                <StatusPill
                  v-if="aiAnalysis"
                  :label="analysisStatusLabel(aiAnalysis)"
                  :state="analysisStatusState(aiAnalysis)"
                />
              </div>
              <p class="summary-text">{{ aiAnalysis?.summary }}</p>
              <ul class="suggestion-list">
                <li v-for="suggestion in aiAnalysis?.suggestions" :key="suggestion">{{ suggestion }}</li>
              </ul>
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
            </template>
          </EChartPanel>
          <section class="panel">
            <div class="section-heading">
              <h2>历史采样列表</h2>
            </div>
            <div class="data-table data-table--six">
              <div class="data-table__head">
                <span>时间</span>
                <span>温度</span>
                <span>湿度</span>
                <span>光照</span>
                <span>CO2</span>
                <span>土壤湿度</span>
                <span>EC</span>
              </div>
              <div v-for="point in historyPoints.slice(-8).reverse()" :key="point.timestamp" class="data-table__row">
                <span>{{ formatDateTime(point.timestamp) }}</span>
                <span>{{ point.temperature }} 摄氏度</span>
                <span>{{ point.humidity }} %RH</span>
                <span>{{ point.light }} lux</span>
                <span>{{ point.co2 }} ppm</span>
                <span>{{ point.soil_moisture }} %</span>
                <span>{{ point.soil_ec }} mS/cm</span>
              </div>
            </div>
          </section>
        </section>

        <section v-show="activeView === 'disease'" class="view-stack">
          <section class="panel">
            <div class="section-heading">
              <div class="section-heading__copy">
              <h2>病害识别</h2>
              <span>上传叶片图片后展示 YOLO 风格检测结果</span>
              </div>
              <button class="text-button" type="button" @click="openDiseasePhotoLibrary">
                <Image :size="18" /> 图片库
              </button>
            </div>
            <div class="disease-layout">
              <div class="image-uploader">
                <label class="upload-drop">
                  <Upload :size="28" />
                  <strong>{{ diseaseImageUrl ? '重新上传叶片图片' : '上传叶片图片' }}</strong>
                  <span>支持 jpg / png，上传后生成检测框和识别建议</span>
                  <input type="file" accept="image/*" @change="handleDiseaseUpload" />
                </label>
                <button v-if="diseaseImageUrl" class="text-button" type="button" @click="clearDiseaseImage">
                  <X :size="16" /> 清除图片
                </button>
                <p v-if="diseaseUploadError" class="form-error disease-error">{{ diseaseUploadError }}</p>
              </div>
              <div class="detection-stage" :class="{ 'detection-stage--empty': !diseaseImageUrl }">
                <img v-if="diseaseImageUrl" :src="diseaseImageUrl" alt="上传的叶片图片" />
                <div v-if="!diseaseImageUrl" class="empty-visual">
                  <Image :size="46" />
                  <span>等待上传图片</span>
                </div>
                <div
                  v-for="box in diseaseResult?.detections"
                  :key="box.id"
                  class="detect-box"
                  :style="{ left: `${box.bbox.x}%`, top: `${box.bbox.y}%`, width: `${box.bbox.width}%`, height: `${box.bbox.height}%` }"
                >
                  <span>{{ box.label }} {{ Math.round(box.confidence * 100) }}%</span>
                </div>
              </div>
            </div>
          </section>

          <section class="panel">
            <div class="section-heading">
              <h2>YOLO 结果展示</h2>
              <StatusPill v-if="diseaseResult" :label="diseaseResult.model" state="neutral" />
            </div>
            <p v-if="diseaseLoading" class="summary-text">正在分析图片...</p>
            <template v-else-if="diseaseResult">
              <p class="summary-text">{{ diseaseResult.summary }}</p>
              <div class="result-grid">
                <article v-for="det in diseaseResult.detections" :key="det.id">
                  <strong>{{ det.label }}</strong>
                  <span>类别：{{ det.class_name }}</span>
                  <span>置信度：{{ Math.round(det.confidence * 100) }}%</span>
                  <span>检测框：x{{ det.bbox.x }} y{{ det.bbox.y }} w{{ det.bbox.width }} h{{ det.bbox.height }}</span>
                </article>
              </div>
              <p class="callout-text">{{ diseaseResult.explanation }}</p>
              <ul class="suggestion-list">
                <li v-for="suggestion in diseaseResult.suggestions" :key="suggestion">{{ suggestion }}</li>
              </ul>
            </template>
            <p v-else class="empty-text">暂无识别结果，上传图片后会展示检测框、类别、置信度、解释和建议。</p>
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
                    <img :src="selectedDiseasePhoto.url" :alt="selectedDiseasePhoto.originalName || '病害识别图片详情'" />
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
                        <span>类别：{{ det.class_name }}</span>
                        <span>置信度：{{ Math.round(det.confidence * 100) }}%</span>
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
              <StatusPill
                v-if="aiAnalysis"
                :label="analysisStatusLabel(aiAnalysis)"
                :state="analysisStatusState(aiAnalysis)"
              />
            </div>
            <p class="summary-text">{{ aiAnalysis?.summary }}</p>
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
            <ul class="suggestion-list">
              <li v-for="command in aiAnalysis?.commands ?? []" :key="`${command.command}-${command.value}`">{{ aiCommandText(command) }}</li>
              <li v-if="(aiAnalysis?.commands ?? []).length === 0">暂无需要立即执行的设备操作。</li>
            </ul>
          </section>
        </section>

        <section v-show="activeView === 'control'" class="view-stack">
          <section class="panel smart-control-panel">
            <div class="section-heading">
              <div>
                <h2>智能托管</h2>
                <span>自动计算控制需求值，手动模式会固定用户设置</span>
              </div>
              <div class="smart-control-actions">
                <StatusPill :label="smartControlDecision?.status ?? '等待数据'" :state="smartControlStatusState" />
                <button class="primary-button" type="button" @click="setAllSmartParamsAuto">
                  <RefreshCw :size="18" />
                  &#19968;&#38190;&#33258;&#21160;
                </button>
                <button class="text-button" type="button" @click="smartControlPanelOpen = !smartControlPanelOpen">
                  <SlidersHorizontal :size="18" />
                  {{ smartControlPanelOpen ? '收起参数' : '打开参数' }}
                </button>
              </div>
            </div>
            <div class="smart-control-summary">
              <p>{{ smartControlDecision?.summary ?? '正在等待实时环境数据生成托管建议。' }}</p>
              <span>{{ smartControlDecision?.weatherSummary ?? '天气暂不可用，本地自治' }}</span>
              <span>上次下发：{{ smartControlLastPublishAt ? formatDateTime(smartControlLastPublishAt) : '尚未下发' }}</span>
            </div>
            <div class="smart-demand-grid">
              <button
                v-for="param in smartControlParams"
                :key="param.key"
                type="button"
                class="smart-demand-chip"
                :class="{ 'smart-demand-chip--manual': param.mode === 'manual' }"
                @click="toggleSmartParamMode(param.key)"
              >
                <div>
                  <strong>{{ param.label }}</strong>
                  <span>{{ param.mode === 'manual' ? '手动' : '自动' }}</span>
                </div>
                <b :style="{ color: param.mode === 'manual' ? '#C26A1B' : param.color }">{{ param.value }}%</b>
              </button>
            </div>
            <div v-if="smartControlPanelOpen" class="smart-param-panel">
              <article v-for="param in smartControlParams" :key="`${param.key}-panel`" class="smart-param-row" :class="{ 'smart-param-row--manual': param.mode === 'manual' }">
                <div class="smart-param-row__head">
                  <div>
                    <strong>{{ param.label }}</strong>
                    <span>当前 {{ param.value }}% · 自动 {{ param.autoValue }}%</span>
                  </div>
                  <StatusPill :label="param.mode === 'manual' ? '手动' : '自动'" :state="param.mode === 'manual' ? 'watch' : 'good'" />
                </div>
                <div class="smart-param-row__control">
                  <input
                    type="range"
                    min="0"
                    max="100"
                    step="1"
                    :value="param.value"
                    :disabled="param.mode !== 'manual'"
                    :style="{ accentColor: param.color }"
                    @change="handleSmartParamSliderChange(param.key, $event)"
                  />
                  <button class="text-button" type="button" @click="param.mode === 'manual' ? restoreSmartParamAuto(param.key) : setSmartParamManual(param.key)">
                    {{ param.mode === 'manual' ? '恢复自动' : '手动' }}
                  </button>
                </div>
              </article>
            </div>
          </section>

          <section class="panel">
            <div class="section-heading">
              <h2>远程设备控制</h2>
              <span>查看并切换现场设备运行状态</span>
            </div>
            <div class="control-grid">
              <article class="control-card">
                <Fan :size="28" />
                <strong>风机</strong>
                <span>{{ latest.status.fan ? '运行中' : '待机' }}</span>
                <button type="button" class="toggle-switch" :class="{ 'toggle-switch--on': latest.status.fan === 1 }" @click="toggleDevice(latest.status.fan === 1, 'fan_on', 'fan_off', '棚内湿度偏高，建议开启通风', '湿度恢复正常，关闭风机')">
                  <span>关闭</span><span>开启</span><i></i>
                </button>
              </article>
              <article class="control-card">
                <Droplets :size="28" />
                <strong>水泵</strong>
                <span>{{ latest.status.pump ? '运行中' : '待机' }}</span>
                <button type="button" class="toggle-switch" :class="{ 'toggle-switch--on': latest.status.pump === 1 }" @click="toggleDevice(latest.status.pump === 1, 'pump_on', 'pump_off', '土壤湿度偏低，启动短时补水', '补水完成，关闭水泵')">
                  <span>关闭</span><span>开启</span><i></i>
                </button>
              </article>
              <article class="control-card">
                <Lightbulb :size="28" />
                <strong>补光灯</strong>
                <span>{{ latest.status.light ? '已开启' : '已关闭' }}</span>
                <button type="button" class="toggle-switch" :class="{ 'toggle-switch--on': latest.status.light === 1 }" @click="toggleDevice(latest.status.light === 1, 'light_on', 'light_off', '光照不足，开启补光灯', '自然光恢复，关闭补光')">
                  <span>关闭</span><span>开启</span><i></i>
                </button>
              </article>
              <article class="control-card">
                <Sun :size="28" />
                <strong>卷帘</strong>
                <span>{{ latest.status.curtain ? '已打开' : '已关闭' }}</span>
                <button type="button" class="toggle-switch" :class="{ 'toggle-switch--on': latest.status.curtain === 1 }" @click="toggleDevice(latest.status.curtain === 1, 'curtain_open', 'curtain_close', '打开卷帘，提高自然光照', '关闭卷帘，降低强光或保温')">
                  <span>关闭</span><span>打开</span><i></i>
                </button>
              </article>
              <article class="control-card">
                <AlertTriangle :size="28" />
                <strong>报警器</strong>
                <span>{{ latest.status.alarm ? '报警中' : '关闭' }}</span>
                <button type="button" class="toggle-switch toggle-switch--danger" :class="{ 'toggle-switch--on': latest.status.alarm === 1 }" @click="toggleDevice(latest.status.alarm === 1, 'alarm_on', 'alarm_off', '触发现场声光报警', '报警解除，关闭报警器')">
                  <span>关闭</span><span>开启</span><i></i>
                </button>
              </article>
            </div>
          </section>

          <section class="panel">
            <div class="section-heading">
              <h2>执行回执</h2>
            </div>
            <div class="command-list">
              <article v-for="result in commandResults" :key="result.executed_at">
                <strong>{{ commandActionText(result.command) }}</strong>
                <span>{{ commandResultText(result) }}</span>
                <time>{{ formatDateTime(result.executed_at) }}</time>
              </article>
              <p v-if="commandResults.length === 0" class="empty-text">暂无控制记录，点击上方按钮后会显示执行结果。</p>
            </div>
          </section>
        </section>

        <section v-show="activeView === 'knowledge'" class="view-stack">
          <p v-if="knowledgeError" class="form-error">{{ knowledgeError }}</p>
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
              <span>展示 RAG 引用片段和管理建议</span>
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
              <span>来自传感器阈值、通信链路、YOLO 和 AI 风险判断</span>
            </div>
            <div class="alarm-list">
              <article v-for="alarm in alarms" :key="alarm.id" :class="`alarm-card alarm-card--${alarm.level}`">
                <div>
                  <strong>{{ alarm.title }}</strong>
                  <span>{{ alarm.source }} · {{ formatDateTime(alarm.timestamp) }}</span>
                </div>
                <p>{{ alarm.detail }}</p>
                <StatusPill :label="alarm.handled ? '已处理' : '待处理'" :state="alarm.handled ? 'good' : 'watch'" />
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
      <aside v-if="assistantOpen" class="assistant-panel">
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
            <button class="icon-button" type="button" title="关闭 AI 助手" @click="assistantOpen = false">
              <X :size="18" />
            </button>
          </div>
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
              <p>{{ message.content }}</p>
              <div v-if="message.references?.length" class="reference-list">
                <strong>引用知识</strong>
                <span v-for="refItem in message.references" :key="`${message.id}-${refItem.itemId}-${refItem.chunkId}`">
                  {{ refItem.title }}：{{ refItem.content }}
                </span>
              </div>
              <div v-if="message.suggested_actions?.length" class="assistant-actions">
                <strong>待确认操作</strong>
                <article
                  v-for="action in message.suggested_actions"
                  :key="action.id"
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
          <span>{{ chatImageFileName }}</span>
          <button class="icon-button" type="button" title="移除图片" @click="clearChatImage">
            <X :size="16" />
          </button>
        </div>
        <div class="chat-composer assistant-composer">
          <label class="icon-button" title="上传图片">
            <Image :size="18" />
            <input type="file" accept="image/*" @change="handleChatImageUpload" />
          </label>
          <button class="icon-button" type="button" :title="listening ? '停止语音输入' : '语音输入'" @click="startVoiceInput">
            <Mic :class="{ pulsing: listening }" :size="18" />
          </button>
          <textarea ref="chatInputRef" v-model="chatInput" placeholder="输入问题或操作需求，执行控制前我会先请你确认。" @keydown="handleChatKeydown"></textarea>
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
    </div>
  </div>
</template>
