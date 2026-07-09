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
  Home,
  Image,
  Leaf,
  Lightbulb,
  Mic,
  MessageSquare,
  Pencil,
  Plus,
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
  deleteKnowledgeBase,
  deleteKnowledgeItem,
  getAlarmRecords,
  getDeviceHistory,
  getCurrentWeather,
  getKnowledgeBases,
  getKnowledgeItems,
  getLatestTelemetry,
  getVoiceTranscriptionStatus,
  sendDeviceCommand,
  sendExpertChatMessage,
  transcribeVoiceChunk,
  updateKnowledgeBase,
  updateKnowledgeItem,
} from './services/api';
import type {
  AiAnalysisResponse,
  AlarmRecord,
  AssistantAction,
  ChatMessage,
  CommandResult,
  DeviceCommand,
  DiseaseDetectionResult,
  HistoryPoint,
  KnowledgeAnalyzeResult,
  KnowledgeBaseInfo,
  KnowledgeItemInfo,
  MetricTargetRange,
  SmartControlDecision,
  SmartControlDemands,
  SmartControlParamKey,
  SmartControlParamState,
  StatusLevel,
  TelemetryPayload,
  WeatherPayload,
} from './types';
import { airQualityFromGasResistance, formatDateTime, formatTime, numberText } from './utils/format';
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

interface MetricEditorRect {
  left: number;
  top: number;
  width: number;
  height: number;
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
const chatMessages = ref<ChatMessage[]>([]);
const chatInput = ref('番茄叶片有黄斑，结合当前环境应该怎么处理？');
const chatInputRef = ref<HTMLTextAreaElement | null>(null);
const chatImageUrl = ref('');
const chatImageFileName = ref('');
const chatSending = ref(false);
const assistantOpen = ref(false);
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
const knowledgeQuestion = ref('结合当前农情，给出水泵、补光灯、风机和卷帘的管理建议。');
const knowledgeAnswer = ref<KnowledgeAnalyzeResult | null>(null);
const knowledgeLoading = ref(false);
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
let activeVoiceRecorder: MediaRecorder | null = null;
let activeVoiceStream: MediaStream | null = null;
let activeBrowserSpeechRecognition: SpeechRecognitionLike | null = null;
let assistantThinkingTimer: number | undefined;
let assistantTypeRunId = 0;
let voiceInputPrefix = '';
let voiceInputSuffix = '';
let voiceCurrentTranscript = '';
let voiceSessionId = '';
let voiceSequence = 0;
let voiceMimeType = 'audio/webm';
let voiceStopping = false;
let voiceUploadQueue: Promise<void> = Promise.resolve();
let metricEditorLastSourceRect: MetricEditorRect | null = null;
const metricEditorSourceRects = new Map<HistoryMetricKey, MetricEditorRect>();

const metricTargetInputSteps: Record<HistoryMetricKey, number> = {
  temperature: 0.01,
  humidity: 0.1,
  light: 10,
  co2: 1,
  soil_moisture: 0.1,
  soil_ec: 0.01,
  gas_resistance: 10,
};

const currentAirQuality = computed(() => {
  if (!latest.value) {
    return { label: '等待数据', level: 'watch' as const };
  }
  return airQualityFromGasResistance(latest.value.sensors.gas_resistance);
});

const selectedKnowledgeBase = computed(() => knowledgeBases.value.find((item) => item.kbId === selectedKbId.value) ?? null);
const activeAlarms = computed(() => alarms.value.filter((item) => !item.handled).length);

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

const overviewMetricCards = computed(() => metricCards.value.map((metric) => ({
  ...metric,
  hint: `${metric.statusLabel} · ${metric.hint}`,
})));

const realtimeMetricCards = computed(() => metricCards.value);

const selectedMetricDefinition = computed(() => historyMetricDefinitions.find((metric) => metric.key === selectedMetricKey.value) ?? null);
const selectedMetricInputStep = computed(() => selectedMetricKey.value ? metricTargetInputSteps[selectedMetricKey.value] : 0.01);

const contentLayoutClass = computed(() => ({
  'content-layout--assistant-open': assistantOpen.value,
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

const smartControlAutoCount = computed(() => smartControlParams.value.filter((item) => item.mode === 'auto').length);
const smartControlManualCount = computed(() => smartControlParams.value.length - smartControlAutoCount.value);
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

const historyChartOption = computed<EChartsOption>(() => {
  const labels = historyPoints.value.map((point) => formatTime(point.timestamp));
  const selectedDefinitions = historyMetricDefinitions.filter((item) => selectedHistoryMetricKeys.value.includes(item.key));
  const selectedCount = selectedDefinitions.length;
  const leftAxisCount = selectedDefinitions.filter((_, index) => index % 2 === 0).length;
  const rightAxisCount = selectedDefinitions.length - leftAxisCount;
  const axisSpacing = selectedCount >= 7 ? 76 : selectedCount >= 5 ? 68 : 60;
  return {
    tooltip: { trigger: 'axis' },
    legend: { show: false },
    grid: {
      left: Math.max(86, 86 + Math.max(0, leftAxisCount - 1) * axisSpacing),
      right: Math.max(86, 86 + Math.max(0, rightAxisCount - 1) * axisSpacing),
      top: selectedCount >= 5 ? 82 : 66,
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
        offset: Math.floor(index / 2) * axisSpacing,
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
      yAxisIndex: index,
      data: historyPoints.value.map(definition.value),
      color: definition.color,
      lineStyle: { width: 3, color: definition.color },
      itemStyle: { color: definition.color },
      emphasis: { focus: 'series' },
    })),
  };
});

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

function isHistoryMetricSelected(key: HistoryMetricKey): boolean {
  return selectedHistoryMetricKeys.value.includes(key);
}

function toggleHistoryMetric(key: HistoryMetricKey): void {
  if (isHistoryMetricSelected(key)) {
    if (selectedHistoryMetricKeys.value.length === 1) {
      return;
    }
    selectedHistoryMetricKeys.value = selectedHistoryMetricKeys.value.filter((item) => item !== key);
    return;
  }
  selectedHistoryMetricKeys.value = [...selectedHistoryMetricKeys.value, key];
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
      metricEditorSourceRects.set(key, elementRect(element));
    }
  });
}

function metricCardRect(key: HistoryMetricKey, element?: Element | null): MetricEditorRect {
  const sourceElement = element ?? document.querySelector<HTMLElement>(`[data-metric-key="${key}"]`);
  if (sourceElement) {
    const rect = elementRect(sourceElement);
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
  const target = metricEditorTargetRect();
  return {
    left: target.left + target.width / 2 - 120,
    top: target.top + target.height / 2 - 80,
    width: 240,
    height: 160,
  };
}

function updateMetricEditorMotion(key: HistoryMetricKey, element?: Element | null): void {
  const target = metricEditorTargetRect();
  const source = metricCardRect(key, element);
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

function hydrateMetricTargetDraft(key: HistoryMetricKey): void {
  selectedMetricKey.value = key;
  const range = metricTargetRanges.value[key];
  targetMinDraft.value = String(range.min);
  targetMaxDraft.value = String(range.max);
  targetRangeError.value = '';
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
  updateMetricEditorMotion(selectedMetricKey.value);
  metricEditorTransition.value = 'closing';
  metricEditorChartActive.value = false;
  clearMetricEditorChartTimer();
  targetRangeError.value = '';
  if (metricEditorTimer) {
    window.clearTimeout(metricEditorTimer);
  }
  metricEditorTimer = window.setTimeout(() => {
    selectedMetricKey.value = null;
    metricEditorTransition.value = '';
  }, 360);
}

function saveMetricTargetRange(): void {
  if (!selectedMetricKey.value) {
    return;
  }
  const min = Number(targetMinDraft.value);
  const max = Number(targetMaxDraft.value);
  if (!Number.isFinite(min) || !Number.isFinite(max)) {
    targetRangeError.value = '请输入有效数字';
    return;
  }
  if (min > max) {
    targetRangeError.value = '目标下限不能高于上限';
    return;
  }
  metricTargetRanges.value = {
    ...metricTargetRanges.value,
    [selectedMetricKey.value]: { min, max },
  };
  targetRangeError.value = '';
  syncSmartControlValues();
}

watch(activeView, (view) => {
  if (view !== 'realtime') {
    closeMetricEditor();
  }
});

watch(assistantOpen, (open) => {
  if (open) {
    void scrollAssistantToBottom();
    void nextTick(resizeChatInput);
  } else {
    assistantShowScrollButton.value = false;
  }
});

watch(chatInput, () => {
  void nextTick(resizeChatInput);
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

async function refreshKnowledge(preferredKbId = selectedKbId.value): Promise<void> {
  const bases = await getKnowledgeBases();
  knowledgeBases.value = [...bases];
  if (bases.length === 0) {
    selectedKbId.value = 0;
    knowledgeItems.value = [];
    return;
  }
  const selected = bases.find((item) => item.kbId === preferredKbId) ?? bases[0];
  selectedKbId.value = selected.kbId;
  knowledgeItems.value = await getKnowledgeItems(selected.kbId);
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
    const [nextHistory, nextAi, nextAlarms, nextWeather] = await Promise.all([
      getDeviceHistory(),
      analyzeFarm(nextLatest),
      getAlarmRecords(),
      getCurrentWeather(),
    ]);
    historyPoints.value = nextHistory;
    aiAnalysis.value = nextAi;
    alarms.value = nextAlarms;
    currentWeather.value = nextWeather;
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
  commandResults.value = [result, ...commandResults.value].slice(0, 10);
  latest.value = {
    ...latest.value,
    timestamp: result.executed_at,
    status: result.status,
  };
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
  commandResults.value = [result, ...commandResults.value].slice(0, 10);
  smartControlLastPublishAt.value = result.executed_at;
  latest.value = {
    ...latest.value,
    timestamp: result.executed_at,
  };
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

async function handleDiseaseUpload(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) {
    return;
  }
  if (diseaseImageUrl.value.startsWith('blob:')) {
    URL.revokeObjectURL(diseaseImageUrl.value);
  }
  const nextUrl = URL.createObjectURL(file);
  diseaseImageUrl.value = nextUrl;
  diseaseLoading.value = true;
  try {
    diseaseResult.value = await analyzeDiseaseImage(file, nextUrl);
  } finally {
    diseaseLoading.value = false;
    input.value = '';
  }
}

function clearDiseaseImage(): void {
  if (diseaseImageUrl.value.startsWith('blob:')) {
    URL.revokeObjectURL(diseaseImageUrl.value);
  }
  diseaseImageUrl.value = '';
  diseaseResult.value = null;
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
  if (shouldFollow && assistantAtBottom.value) {
    await scrollAssistantToBottom();
  } else {
    await nextTick();
    updateAssistantScrollState();
  }
}

function handleChatKeydown(event: KeyboardEvent): void {
  if (event.key !== 'Enter' || event.shiftKey || event.isComposing) {
    return;
  }
  event.preventDefault();
  void sendChat();
}

async function sendChat(): Promise<void> {
  if (!latest.value || chatSending.value) {
    return;
  }
  const question = chatInput.value.trim();
  if (question.length === 0 && chatImageUrl.value.length === 0) {
    return;
  }
  const userMessage: ChatMessage = {
    id: `user-${Date.now()}`,
    role: 'user',
    content: question || '请分析这张作物图片。',
    image_url: chatImageUrl.value || undefined,
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
  chatInput.value = '';
  await scrollAssistantToBottom();
  startAssistantThinking(thinkingMessage.id);
  chatSending.value = true;
  try {
    const response = await sendExpertChatMessage({
      question: userMessage.content,
      image_url: chatImageUrl.value || undefined,
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

function isVoiceCaptureSecureOrigin(): boolean {
  const host = window.location.hostname;
  return window.location.protocol === 'https:' || host === 'localhost' || host === '127.0.0.1' || host === '::1';
}

function pickVoiceMimeType(): string {
  const candidates = [
    'audio/webm;codecs=opus',
    'audio/webm',
    'audio/ogg;codecs=opus',
    'audio/mp4',
  ];
  return candidates.find((mimeType) => MediaRecorder.isTypeSupported(mimeType)) ?? '';
}

function stopActiveVoiceStream(): void {
  activeVoiceStream?.getTracks().forEach((track) => track.stop());
  activeVoiceStream = null;
}

function getBrowserSpeechRecognition(): SpeechRecognitionConstructor | null {
  const speechWindow = window as Window & {
    SpeechRecognition?: SpeechRecognitionConstructor;
    webkitSpeechRecognition?: SpeechRecognitionConstructor;
  };
  return speechWindow.SpeechRecognition ?? speechWindow.webkitSpeechRecognition ?? null;
}

function shouldFallbackToBrowserSpeech(message: string): boolean {
  return /SPEECH_TRANSCRIBE_API_KEY|OPENAI_API_KEY|API Key/i.test(message);
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

function startBrowserSpeechFallback(): boolean {
  const Recognition = getBrowserSpeechRecognition();
  if (!Recognition) {
    voiceMessage.value = '后端未配置语音识别 API Key，且当前浏览器不支持内置语音识别。请配置 SPEECH_TRANSCRIBE_API_KEY 或手动输入。';
    listening.value = false;
    return false;
  }

  const recognition = new Recognition();
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
      voiceMessage.value = '正在使用浏览器语音识别，文字已同步到输入框';
    }
  };
  recognition.onerror = () => {
    voiceMessage.value = '浏览器语音识别失败，请检查麦克风权限，或配置后端 SPEECH_TRANSCRIBE_API_KEY。';
    listening.value = false;
    activeBrowserSpeechRecognition = null;
  };
  recognition.onend = () => {
    listening.value = false;
    activeBrowserSpeechRecognition = null;
    voiceMessage.value = voiceCurrentTranscript.trim().length > 0
      ? '语音已写入输入框'
      : '浏览器语音识别已结束，没有识别到有效文字';
  };

  try {
    recognition.start();
    listening.value = true;
    voiceMessage.value = '后端未配置语音识别 API Key，已切换为浏览器语音识别';
    return true;
  } catch (error) {
    const message = error instanceof Error ? error.message : '未知错误';
    voiceMessage.value = `浏览器语音识别启动失败：${message}`;
    activeBrowserSpeechRecognition = null;
    listening.value = false;
    return false;
  }
}

async function uploadVoiceChunk(chunk: Blob, sequence: number, isFinal: boolean): Promise<void> {
  try {
    const result = await transcribeVoiceChunk({
      audio: chunk,
      sessionId: voiceSessionId,
      sequence,
      isFinal,
      mimeType: voiceMimeType || chunk.type || 'audio/webm',
      language: 'zh-CN',
    });
    if (result.text.trim().length > 0) {
      voiceCurrentTranscript = result.text.trim();
      setChatInputFromVoice(voiceCurrentTranscript);
      voiceMessage.value = result.final ? '语音已写入输入框' : '后端实时识别中，文字已同步到输入框';
      return;
    }
    if (shouldFallbackToBrowserSpeech(result.message || '')) {
      if (activeVoiceRecorder && activeVoiceRecorder.state !== 'inactive') {
        activeVoiceRecorder.ondataavailable = null;
        activeVoiceRecorder.stop();
      }
      activeVoiceRecorder = null;
      stopActiveVoiceStream();
      void startBrowserSpeechFallback();
      return;
    }
    voiceMessage.value = result.message || (result.final ? '没有识别到有效文字' : '正在录音，等待识别结果...');
  } catch (error) {
    const message = error instanceof Error ? error.message : '未知错误';
    console.warn('Voice chunk transcription failed', message);
    voiceMessage.value = `后端语音识别连接失败：${message}`;
  }
}

function queueVoiceChunkUpload(chunk: Blob, isFinal: boolean): void {
  const sequence = voiceSequence;
  voiceSequence += 1;
  voiceUploadQueue = voiceUploadQueue
    .then(() => uploadVoiceChunk(chunk, sequence, isFinal))
    .catch((error) => {
      const message = error instanceof Error ? error.message : '未知错误';
      voiceMessage.value = `后端语音识别失败：${message}`;
    });
}

function stopVoiceInput(): void {
  if (activeBrowserSpeechRecognition) {
    stopBrowserSpeechInput();
    listening.value = false;
    voiceMessage.value = voiceCurrentTranscript.trim().length > 0 ? '语音已写入输入框' : '语音输入已停止';
    return;
  }
  voiceStopping = true;
  voiceMessage.value = '正在整理语音输入...';
  if (activeVoiceRecorder && activeVoiceRecorder.state !== 'inactive') {
    activeVoiceRecorder.stop();
    return;
  }
  stopActiveVoiceStream();
  listening.value = false;
}

function prepareVoiceInputSession(): void {
  const input = chatInputRef.value;
  const selectionStart = input?.selectionStart ?? chatInput.value.length;
  const selectionEnd = input?.selectionEnd ?? chatInput.value.length;
  voiceInputPrefix = chatInput.value.slice(0, selectionStart);
  voiceInputSuffix = chatInput.value.slice(selectionEnd);
  voiceCurrentTranscript = '';
  voiceSessionId = `voice-${Date.now()}-${Math.random().toString(36).slice(2)}`;
  voiceSequence = 0;
  voiceStopping = false;
  voiceUploadQueue = Promise.resolve();
}

async function startVoiceInput(): Promise<void> {
  if (listening.value) {
    stopVoiceInput();
    return;
  }
  if (activeBrowserSpeechRecognition) {
    stopBrowserSpeechInput();
  }
  prepareVoiceInputSession();
  if (!navigator.mediaDevices?.getUserMedia) {
    startBrowserSpeechFallback();
    return;
  }
  if (!isVoiceCaptureSecureOrigin()) {
    voiceMessage.value = '录音需要 HTTPS 或 localhost，请用 localhost 地址打开。';
    return;
  }

  const input = chatInputRef.value;
  const selectionStart = input?.selectionStart ?? chatInput.value.length;
  const selectionEnd = input?.selectionEnd ?? chatInput.value.length;
  voiceInputPrefix = chatInput.value.slice(0, selectionStart);
  voiceInputSuffix = chatInput.value.slice(selectionEnd);
  voiceCurrentTranscript = '';
  voiceSessionId = `voice-${Date.now()}-${Math.random().toString(36).slice(2)}`;
  voiceSequence = 0;
  voiceStopping = false;
  voiceUploadQueue = Promise.resolve();

  voiceMessage.value = '正在检查语音识别后端...';
  const voiceStatus = await getVoiceTranscriptionStatus();
  if (voiceStatus.configured === false) {
    voiceMessage.value = voiceStatus.message || '后端未配置语音识别 API Key，正在切换浏览器语音识别';
    startBrowserSpeechFallback();
    return;
  }

  try {
    activeVoiceStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });
    voiceMimeType = pickVoiceMimeType();
    activeVoiceRecorder = new MediaRecorder(
      activeVoiceStream,
      voiceMimeType ? { mimeType: voiceMimeType } : undefined,
    );
    activeVoiceRecorder.ondataavailable = (event) => {
      if (event.data.size <= 0) {
        return;
      }
      queueVoiceChunkUpload(event.data, voiceStopping);
    };
    activeVoiceRecorder.onerror = () => {
      voiceMessage.value = '录音失败，请检查麦克风权限或输入设备。';
      stopVoiceInput();
    };
    activeVoiceRecorder.onstop = () => {
      const wasStopping = voiceStopping;
      activeVoiceRecorder = null;
      stopActiveVoiceStream();
      voiceUploadQueue.finally(() => {
        listening.value = false;
        if (voiceCurrentTranscript.trim().length > 0) {
          voiceMessage.value = '语音已写入输入框';
        } else if (wasStopping) {
          voiceMessage.value = '没有识别到有效文字';
        }
      });
    };
    listening.value = true;
    voiceMessage.value = '正在录音，后端会实时识别并写入输入框';
    activeVoiceRecorder.start(1200);
  } catch (error) {
    listening.value = false;
    activeVoiceRecorder = null;
    stopActiveVoiceStream();
    const message = error instanceof Error ? error.message : '未知错误';
    voiceMessage.value = `录音启动失败：${message}`;
  }
}

async function selectKnowledgeBase(kbId: number): Promise<void> {
  selectedKbId.value = kbId;
  knowledgeItems.value = await getKnowledgeItems(kbId);
  knowledgeAnswer.value = null;
}

function beginEditKnowledgeBase(item: KnowledgeBaseInfo): void {
  editingKbId.value = item.kbId;
  kbNameDraft.value = item.name;
  kbDescriptionDraft.value = item.description;
}

function beginEditKnowledgeItem(item: KnowledgeItemInfo): void {
  editingItemId.value = item.itemId;
  itemTitleDraft.value = item.title;
  itemContentDraft.value = item.content;
}

async function saveKnowledgeBase(): Promise<void> {
  const name = kbNameDraft.value.trim();
  if (name.length === 0) {
    return;
  }
  const description = kbDescriptionDraft.value.trim();
  const saved = editingKbId.value > 0
    ? await updateKnowledgeBase(editingKbId.value, name, description)
    : await createKnowledgeBase(name, description);
  editingKbId.value = 0;
  kbNameDraft.value = '番茄结果期管理';
  kbDescriptionDraft.value = '结果期水肥、光照、病害管理经验';
  await refreshKnowledge(saved.kbId);
}

async function removeKnowledgeBase(kbId: number): Promise<void> {
  await deleteKnowledgeBase(kbId);
  if (editingKbId.value === kbId) {
    editingKbId.value = 0;
  }
  await refreshKnowledge();
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
  if (editingItemId.value > 0) {
    await updateKnowledgeItem(selectedKbId.value, editingItemId.value, title, content);
  } else {
    await addKnowledgeItem(selectedKbId.value, title, content);
  }
  editingItemId.value = 0;
  itemTitleDraft.value = '番茄高湿病害风险';
  itemContentDraft.value = '番茄在高湿、通风不足时容易出现叶斑病和霜霉病，应先通风降湿并减少叶面结露。';
  knowledgeItems.value = await getKnowledgeItems(selectedKbId.value);
}

async function removeKnowledgeItem(itemId: number): Promise<void> {
  if (selectedKbId.value <= 0) {
    return;
  }
  await deleteKnowledgeItem(selectedKbId.value, itemId);
  if (editingItemId.value === itemId) {
    editingItemId.value = 0;
  }
  knowledgeItems.value = await getKnowledgeItems(selectedKbId.value);
}

async function runKnowledgeAnalysis(): Promise<void> {
  if (selectedKbId.value <= 0 || knowledgeLoading.value) {
    return;
  }
  knowledgeLoading.value = true;
  try {
    knowledgeAnswer.value = await analyzeKnowledge(selectedKbId.value, latest.value?.device_id ?? 'field_001', knowledgeQuestion.value.trim());
  } finally {
    knowledgeLoading.value = false;
  }
}

onMounted(() => {
  void loadDashboard();
  void refreshKnowledge();
  chatMessages.value = [
    {
      id: 'assistant-welcome',
      role: 'assistant',
      content: '我是智慧农业专家助手。你可以输入文字、上传叶片图片，或用语音提问。',
      created_at: Date.now(),
    },
  ];
  refreshTimer = window.setInterval(() => {
    void loadDashboard(true);
  }, 5000);
});

onBeforeUnmount(() => {
  if (refreshTimer) {
    window.clearInterval(refreshTimer);
  }
  if (metricEditorTimer) {
    window.clearTimeout(metricEditorTimer);
  }
  if (metricEditorChartTimer) {
    window.clearTimeout(metricEditorChartTimer);
  }
  stopAssistantThinking();
  assistantTypeRunId += 1;
  if (diseaseImageUrl.value.startsWith('blob:')) {
    URL.revokeObjectURL(diseaseImageUrl.value);
  }
  if (chatImageUrl.value.startsWith('blob:')) {
    URL.revokeObjectURL(chatImageUrl.value);
  }
  if (activeVoiceRecorder && activeVoiceRecorder.state !== 'inactive') {
    activeVoiceRecorder.stop();
  }
  activeVoiceRecorder = null;
  stopBrowserSpeechInput();
  stopActiveVoiceStream();
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

    <div class="content-layout" :class="contentLayoutClass">
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
            <EChartPanel title="近 6 小时环境趋势" :option="historyChartOption" :active="activeView === 'overview'">
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
                  :label="riskLabel(aiAnalysis.risk_level)"
                  :state="aiAnalysis.risk_level === 'low' ? 'good' : aiAnalysis.risk_level === 'medium' ? 'watch' : 'danger'"
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

            <section class="panel ai-trend-panel">
              <div class="section-heading">
                <h2>AI 分析曲线</h2>
                <span>智能判断</span>
              </div>
              <div class="ai-trend-mock">
                <i v-for="metric in realtimeMetricCards.slice(0, 7)" :key="metric.key" :style="{ height: `${36 + Math.abs(metric.currentValue % 54)}px`, background: metric.color }"></i>
              </div>
              <p class="summary-text">结合当前环境指标展示异常概率、调控建议强度和病害风险趋势参考。</p>
            </section>
            <section class="panel sensor-table">
              <div class="section-heading">
                <h2>传感器原始值</h2>
                <span>查看设备最新采样明细</span>
              </div>
              <dl>
                <div><dt>温度 / 湿度</dt><dd>{{ latest.sensors.temperature }} 摄氏度 / {{ latest.sensors.humidity }} %RH</dd></div>
                <div><dt>光照 / CO2</dt><dd>{{ latest.sensors.light }} lux / {{ latest.sensors.co2 }} ppm</dd></div>
                <div><dt>土壤湿度 / 土壤 EC</dt><dd>{{ latest.sensors.soil_moisture }} % / {{ latest.sensors.soil_ec }} mS/cm</dd></div>
                <div><dt>气压 / 空气质量</dt><dd>{{ latest.sensors.pressure }} kPa / {{ latest.sensors.gas_resistance }} Ω</dd></div>
              </dl>
            </section>
          </template>

          <section
            v-else
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
                <button class="primary-button" type="button" @click="saveMetricTargetRange">
                  <Save :size="18" />
                  &#20445;&#23384;&#30446;&#26631;
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
          <EChartPanel title="历史曲线" :option="historyChartOption" :active="activeView === 'history'">
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
              <h2>病害识别</h2>
              <span>上传叶片图片后展示 YOLO 风格检测结果</span>
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

        <section v-show="activeView === 'ai'" class="view-stack">
          <section class="panel ai-panel">
            <div class="section-heading">
              <h2>AI 农事建议</h2>
              <StatusPill
                v-if="aiAnalysis"
                :label="riskLabel(aiAnalysis.risk_level)"
                :state="aiAnalysis.risk_level === 'low' ? 'good' : aiAnalysis.risk_level === 'medium' ? 'watch' : 'danger'"
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
          <div class="knowledge-layout">
            <section class="panel">
              <div class="section-heading">
                <h2>知识库管理</h2>
                <span>参考 smartfarm7pack 的 RAG 知识维护流程</span>
              </div>
              <div class="form-stack">
                <input v-model="kbNameDraft" placeholder="知识库名称" />
                <textarea v-model="kbDescriptionDraft" placeholder="知识库描述"></textarea>
                <button class="primary-button" type="button" @click="saveKnowledgeBase">
                  <Save :size="18" /> {{ editingKbId ? '保存知识库' : '新建知识库' }}
                </button>
              </div>
              <div class="knowledge-list">
                <article v-for="base in knowledgeBases" :key="base.kbId" :class="{ selected: selectedKbId === base.kbId }" @click="selectKnowledgeBase(base.kbId)">
                  <div>
                    <strong>{{ base.name }}</strong>
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
              </div>
            </section>

            <section class="panel">
              <div class="section-heading">
                <h2>知识条目</h2>
                <span>{{ selectedKnowledgeBase?.name ?? '请选择知识库' }}</span>
              </div>
              <div class="form-stack">
                <input v-model="itemTitleDraft" placeholder="知识标题" />
                <textarea v-model="itemContentDraft" placeholder="知识正文"></textarea>
                <button class="primary-button" type="button" :disabled="selectedKbId <= 0" @click="saveKnowledgeItem">
                  <Plus :size="18" /> {{ editingItemId ? '保存知识' : '新增知识' }}
                </button>
              </div>
              <div class="knowledge-list">
                <article v-for="item in knowledgeItems" :key="item.itemId">
                  <div>
                    <strong>{{ item.title }}</strong>
                    <span>{{ item.content }}</span>
                  </div>
                  <div class="row-actions">
                    <button class="icon-button" type="button" title="编辑" @click="beginEditKnowledgeItem(item)">
                      <Pencil :size="16" />
                    </button>
                    <button class="icon-button" type="button" title="删除" @click="removeKnowledgeItem(item.itemId)">
                      <Trash2 :size="16" />
                    </button>
                  </div>
                </article>
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


      <aside v-if="assistantOpen" class="assistant-panel">
        <div class="assistant-panel__header">
          <div>
            <span>全局对话</span>
            <h2>AI 助手</h2>
          </div>
          <button class="icon-button" type="button" title="关闭 AI 助手" @click="assistantOpen = false">
            <X :size="18" />
          </button>
        </div>
        <StatusPill :label="voiceMessage" :state="listening ? 'watch' : 'neutral'" />
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
    </div>
  </div>
</template>
