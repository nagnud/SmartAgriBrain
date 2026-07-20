import type {
  AlarmRecord,
  CommandResult,
  DeviceCommand,
  DeviceRuntimeStatus,
  ExpertChatRequest,
  ExpertChatResponse,
  HistoryPoint,
  HistoryMetricKey,
  KnowledgeAnalyzeResult,
  KnowledgeBaseInfo,
  KnowledgeItemInfo,
  KnowledgeReference,
  KnowledgeTextAddResult,
  MetricTargetRange,
  TelemetryPayload,
  WeatherBundle,
  WeatherPayload,
} from '../types';

const deviceId = 'sensairshuttle_001';

let runtimeStatus: DeviceRuntimeStatus = {
  wifi: 'connected',
  mqtt: 'connected',
  fan: 0,
  pump: 0,
  light: 0,
  alarm: 0,
  curtain: 0,
};

let tick = 0;
let nextKnowledgeBaseId = 4;
let nextKnowledgeItemId = 9;

const mockHistoryPointCount = 360;
const mockHistoryStepMs = 60 * 1000;
const mockHistoryCompletedCount = mockHistoryPointCount - 1;

type MockAlarmDirection = 'low' | 'high';

type MockAlarmRuleState = {
  direction: MockAlarmDirection | null;
  abnormalCount: number;
  normalCount: number;
  currentAlarmId: string | null;
};

type MockMetricDefinition = {
  label: string;
  unit: string;
  advice: Record<MockAlarmDirection, string>;
};

const mockMetricKeys: HistoryMetricKey[] = [
  'temperature',
  'humidity',
  'light',
  'co2',
  'soil_moisture',
  'soil_ec',
  'gas_resistance',
];

const mockMetricDefinitions: Record<HistoryMetricKey, MockMetricDefinition> = {
  temperature: { label: '棚内温度', unit: '摄氏度', advice: { low: '建议检查保温和加热设备。', high: '建议检查通风和遮阳设备。' } },
  humidity: { label: '棚内湿度', unit: '%RH', advice: { low: '建议检查灌溉和加湿安排。', high: '建议加强通风并检查叶面结露。' } },
  light: { label: '光照强度', unit: 'lux', advice: { low: '建议检查补光灯和卷帘状态。', high: '建议检查遮阳和卷帘状态。' } },
  co2: { label: '二氧化碳浓度', unit: 'ppm', advice: { low: '建议检查通风时段和二氧化碳补充安排。', high: '建议加强通风并检查气体来源。' } },
  soil_moisture: { label: '空气湿度', unit: '%', advice: { low: '建议检查灌溉和水泵状态。', high: '建议减少灌溉并检查排水情况。' } },
  soil_ec: { label: '土壤肥力', unit: 'mS/cm', advice: { low: '建议检查养分供应和施肥计划。', high: '建议检查施肥浓度并评估是否需要冲洗基质。' } },
  gas_resistance: { label: '空气质量', unit: 'Ω', advice: { low: '建议加强通风并排查异常气味来源。', high: '建议继续观察空气质量变化。' } },
};

let mockAlarmRanges: Record<HistoryMetricKey, MetricTargetRange> = {
  temperature: { min: 24, max: 30 },
  humidity: { min: 55, max: 72 },
  light: { min: 14000, max: 24000 },
  co2: { min: 520, max: 900 },
  soil_moisture: { min: 48, max: 66 },
  soil_ec: { min: 1.2, max: 2.6 },
  gas_resistance: { min: 12000, max: 22000 },
};

const mockAlarmRuleStates = Object.fromEntries(
  mockMetricKeys.map((key) => [key, {
    direction: null,
    abnormalCount: 0,
    normalCount: 0,
    currentAlarmId: null,
  }]),
) as Record<HistoryMetricKey, MockAlarmRuleState>;

export const mockAlarms: AlarmRecord[] = [];
let lastMockTelemetry: TelemetryPayload | null = null;
let nextMockAlarmId = 1;

const nowText = () => new Intl.DateTimeFormat('zh-CN', {
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
}).format(new Date());

function rounded(value: number, digits = 1): number {
  const base = 10 ** digits;
  return Math.round(value * base) / base;
}

function mockHistoryPoint(timestamp: number): HistoryPoint {
  const elapsedMinutes = timestamp / 60_000;
  const phase = elapsedMinutes * 0.55;
  const slowPhase = elapsedMinutes * 0.17;
  return {
    timestamp,
    temperature: rounded(27.2 + Math.sin(phase) * 1.7 + Math.sin(slowPhase) * 0.45),
    humidity: rounded(63.5 + Math.cos(phase * 0.82) * 5.4 + Math.sin(slowPhase * 0.7) * 1.2),
    gas_resistance: Math.round(16_400 + Math.cos(phase * 0.58) * 2_200 + Math.sin(slowPhase) * 650),
    light: Math.round(17_200 + Math.sin(phase * 0.64) * 4_800 + Math.sin(slowPhase * 1.3) * 900),
    co2: Math.round(640 + Math.cos(phase * 0.72) * 105 + Math.sin(slowPhase * 0.9) * 28),
    soil_moisture: rounded(58.5 + Math.sin(phase * 0.42) * 5.8 + Math.cos(slowPhase * 0.8) * 1.1),
    soil_ec: rounded(1.82 + Math.cos(phase * 0.31) * 0.24 + Math.sin(slowPhase * 0.6) * 0.06, 2),
  };
}

let mockHistoryCompletedThrough = Math.floor(Date.now() / mockHistoryStepMs) * mockHistoryStepMs - mockHistoryStepMs;
const mockHistoryCompletedPoints: HistoryPoint[] = Array.from(
  { length: mockHistoryCompletedCount },
  (_, index) => mockHistoryPoint(
    mockHistoryCompletedThrough - (mockHistoryCompletedCount - 1 - index) * mockHistoryStepMs,
  ),
);

function advanceMockHistory(now: number): void {
  const latestCompletedTimestamp = Math.floor(now / mockHistoryStepMs) * mockHistoryStepMs - mockHistoryStepMs;
  while (mockHistoryCompletedThrough < latestCompletedTimestamp) {
    mockHistoryCompletedThrough += mockHistoryStepMs;
    mockHistoryCompletedPoints.push(mockHistoryPoint(mockHistoryCompletedThrough));
  }
  if (mockHistoryCompletedPoints.length > mockHistoryCompletedCount) {
    mockHistoryCompletedPoints.splice(0, mockHistoryCompletedPoints.length - mockHistoryCompletedCount);
  }
}

function mockAlarmDirection(value: number, range: MetricTargetRange): MockAlarmDirection | null {
  if (value < range.min) {
    return 'low';
  }
  if (value > range.max) {
    return 'high';
  }
  return null;
}

function mockAlarmById(alarmId: string | null): AlarmRecord | undefined {
  return alarmId ? mockAlarms.find((alarm) => alarm.id === alarmId && alarm.state !== 'resolved') : undefined;
}

function mockAlarmText(
  key: HistoryMetricKey,
  direction: MockAlarmDirection,
  value: number,
  range: MetricTargetRange,
): Pick<AlarmRecord, 'title' | 'detail'> {
  const definition = mockMetricDefinitions[key];
  const directionText = direction === 'high' ? '高于' : '低于';
  const countText = direction === 'high' ? '偏高' : '偏低';
  return {
    title: `${definition.label}${directionText}目标范围`,
    detail: `当前 ${value} ${definition.unit}，目标范围为 ${range.min} 至 ${range.max} ${definition.unit}，已连续 3 次${countText}。${definition.advice[direction]}`,
  };
}

function evaluateMockAlarmMetric(key: HistoryMetricKey, value: number, timestamp: number): void {
  const range = mockAlarmRanges[key];
  const direction = mockAlarmDirection(value, range);
  const ruleState = mockAlarmRuleStates[key];
  let alarm = mockAlarmById(ruleState.currentAlarmId);

  if (direction === null) {
    ruleState.direction = null;
    ruleState.abnormalCount = 0;
    ruleState.normalCount += 1;
    if (alarm && ruleState.normalCount >= 3) {
      alarm.state = 'resolved';
      alarm.resolved_at = timestamp;
      alarm.detail = `${alarm.detail} 该指标已连续 3 次回到目标范围。`;
      ruleState.currentAlarmId = null;
      ruleState.normalCount = 0;
    }
    return;
  }

  ruleState.normalCount = 0;
  if (ruleState.direction !== direction) {
    if (alarm) {
      alarm.state = 'resolved';
      alarm.resolved_at = timestamp;
      alarm.detail = `${alarm.detail} 指标越界方向已经改变。`;
      ruleState.currentAlarmId = null;
      alarm = undefined;
    }
    ruleState.direction = direction;
    ruleState.abnormalCount = 1;
  } else {
    ruleState.abnormalCount += 1;
  }

  if (ruleState.abnormalCount < 3) {
    return;
  }

  const text = mockAlarmText(key, direction, value, range);
  if (alarm) {
    alarm.title = text.title;
    alarm.detail = text.detail;
    alarm.timestamp = timestamp;
    return;
  }

  const created: AlarmRecord = {
    id: `ALM-MOCK-${String(nextMockAlarmId).padStart(4, '0')}`,
    device_id: deviceId,
    level: 'warning',
    title: text.title,
    detail: text.detail,
    source: '大棚环境监测',
    timestamp,
    handled: false,
    state: 'open',
    handled_at: null,
    resolved_at: null,
  };
  nextMockAlarmId += 1;
  mockAlarms.unshift(created);
  ruleState.currentAlarmId = created.id;
}

function evaluateMockTelemetry(telemetry: TelemetryPayload): void {
  const timestamp = telemetry.timestamp;
  mockMetricKeys.forEach((key) => evaluateMockAlarmMetric(key, telemetry.sensors[key], timestamp));
}

export function updateMockAlarmRanges(ranges: Record<HistoryMetricKey, MetricTargetRange>): void {
  mockAlarmRanges = Object.fromEntries(
    mockMetricKeys.map((key) => [key, { ...ranges[key] }]),
  ) as Record<HistoryMetricKey, MetricTargetRange>;

  if (!lastMockTelemetry) {
    return;
  }
  mockMetricKeys.forEach((key) => {
    const ruleState = mockAlarmRuleStates[key];
    const alarm = mockAlarmById(ruleState.currentAlarmId);
    const direction = mockAlarmDirection(lastMockTelemetry!.sensors[key], mockAlarmRanges[key]);
    ruleState.direction = direction;
    ruleState.abnormalCount = 0;
    ruleState.normalCount = 0;
    if (alarm && direction === null) {
      alarm.state = 'resolved';
      alarm.resolved_at = Date.now();
      alarm.detail = `${alarm.detail} 目标范围调整后，该指标已处于正常范围。`;
      ruleState.currentAlarmId = null;
    }
  });
}

export function buildMockLatest(): TelemetryPayload {
  tick += 1;
  const timestamp = Date.now();
  const current = mockHistoryPoint(timestamp);
  const telemetry: TelemetryPayload = {
    device_id: deviceId,
    timestamp,
    sensors: {
      temperature: current.temperature ?? Number.NaN,
      humidity: current.humidity ?? Number.NaN,
      pressure: rounded(101.1 + Math.sin(timestamp / 180_000) * 0.5),
      gas_resistance: current.gas_resistance ?? Number.NaN,
      light: current.light ?? Number.NaN,
      co2: current.co2 ?? Number.NaN,
      soil_moisture: current.soil_moisture ?? Number.NaN,
      soil_ec: current.soil_ec ?? Number.NaN,
    },
    status: { ...runtimeStatus },
  };
  lastMockTelemetry = telemetry;
  evaluateMockTelemetry(telemetry);
  return telemetry;
}

export function buildMockHistory(): HistoryPoint[] {
  const now = Date.now();
  advanceMockHistory(now);
  return [
    ...mockHistoryCompletedPoints.map((point) => ({ ...point })),
    mockHistoryPoint(now),
  ];
}

export function buildMockWeather(): WeatherPayload {
  const phase = tick / 5;
  return {
    location: '智慧大棚基地',
    condition: Math.sin(phase) > 0 ? '多云' : '晴间多云',
    temperature: rounded(28.6 + Math.sin(phase / 1.8) * 2.1),
    humidity: Math.round(64 + Math.cos(phase / 2) * 8),
    wind_direction: '东南风',
    wind_level: '2 级',
    updated_at: Date.now(),
  };
}

export function buildMockWeatherBundle(city = 'wuxi'): WeatherBundle {
  const current = buildMockWeather();
  const now = Date.now();
  return {
    city,
    updated_at: now,
    current: {
      available: true,
      name: '实况天气',
      data: {
        ...current,
        city,
        feels_like: current.temperature + 1,
        wind_speed: 9,
        wind_scale: 2,
        pressure: 1008,
        visibility: 12,
      },
      updated_at: now,
    },
    daily: {
      available: true,
      name: '逐日预报',
      data: Array.from({ length: 5 }, (_, index) => ({
        date: new Date(now + index * 24 * 60 * 60 * 1000).toISOString().slice(0, 10),
        condition_day: index % 2 === 0 ? '多云' : '阵雨',
        condition_night: '多云',
        high: 31 - index,
        low: 24 - Math.floor(index / 2),
        rainfall: index === 1 ? 4.2 : 0,
        precip: index === 1 ? 65 : 20,
        humidity: 68 + index,
        wind_direction: '东南风',
        wind_speed: 8 + index,
        wind_scale: 2,
      })),
      updated_at: now,
    },
    hourly: {
      available: true,
      name: '逐小时预报',
      data: Array.from({ length: 8 }, (_, index) => ({
        time: new Date(now + index * 60 * 60 * 1000).toISOString(),
        condition: index % 3 === 0 ? '阵雨' : '多云',
        temperature: 28 + Math.round(Math.sin(index / 2) * 2),
        humidity: 66 + index,
        rainfall: index % 3 === 0 ? 0.8 : 0,
        precip: index % 3 === 0 ? 50 : 15,
        wind_direction: '东南风',
        wind_speed: 7 + index,
        wind_scale: 2,
      })),
      updated_at: now,
    },
    air: {
      available: true,
      name: '空气质量',
      data: { aqi: 46, quality: '优', pm25: 18, pm10: 36, o3: 82, no2: 22, so2: 8, co: 0.5 },
      updated_at: now,
    },
    life: {
      available: true,
      name: '生活指数',
      data: {
        dressing: { brief: '热', details: '温度偏高，棚内巡检注意补水。' },
        sport: { brief: '较适宜', details: '室外风力较小，适合短时巡棚。' },
        uv: { brief: '中等', details: '午间光照强，注意遮阳和补水。' },
      },
      updated_at: now,
    },
    alarms: {
      available: true,
      name: '天气预警',
      data: [],
      updated_at: now,
    },
    registered_capabilities: [
      { key: 'agriculture', name: '农业气象', available: false, reason: '模拟环境未开通。' },
      { key: 'grid', name: '网格天气', available: false, reason: '模拟环境未开通。' },
      { key: 'map_layer', name: '气象图层', available: false, reason: '模拟环境未开通。' },
      { key: 'marine', name: '海洋天气', available: false, reason: '模拟环境未开通。' },
    ],
  };
}

export function executeMockCommand(command: DeviceCommand): CommandResult {
  const status = { ...runtimeStatus };
  if (command.command.startsWith('fan_')) {
    status.fan = command.value;
  }
  if (command.command.startsWith('pump_')) {
    status.pump = command.value;
  }
  if (command.command.startsWith('light_')) {
    status.light = command.value;
  }
  if (command.command.startsWith('alarm_')) {
    status.alarm = command.value;
  }
  if (command.command.startsWith('curtain_')) {
    status.curtain = command.value;
  }
  runtimeStatus = status;
  return {
    success: true,
    message: '操作已发送，正在等待设备返回结果',
    command,
    executed_at: Date.now(),
    status: { ...runtimeStatus },
  };
}

export const mockKnowledgeBases: KnowledgeBaseInfo[] = [
  { kbId: 1, name: '番茄管理知识库', description: '温室番茄水肥、光照、二氧化碳和病害管理经验', enabled: true, updatedAt: nowText() },
  { kbId: 2, name: '病虫害防治库', description: '叶斑病、霜霉病、白粉病等识别与处理建议', enabled: true, updatedAt: nowText() },
  { kbId: 3, name: '设备控制规则库', description: '风机、水泵、补光灯、卷帘联动规则', enabled: true, updatedAt: nowText() },
];

export const mockKnowledgeItems: KnowledgeItemInfo[] = [
  {
    itemId: 1,
    kbId: 1,
    title: '番茄高湿管理原则',
    content: '番茄结果期应避免空气湿度长期高于 85%，高湿会增加灰霉病、霜霉病和叶斑病风险，应加强通风并减少叶面结露。',
    updatedAt: nowText(),
  },
  {
    itemId: 2,
    kbId: 1,
    title: '土壤肥力管理',
    content: '番茄土壤肥力指标建议维持在 1.5 到 2.4 mS/cm，过高会造成盐害，过低会影响养分供应。',
    updatedAt: nowText(),
  },
  {
    itemId: 3,
    kbId: 2,
    title: '叶斑病早期处理',
    content: '叶片出现黄褐色不规则斑点时，应降低湿度、清除病叶并观察 24 小时扩展情况，必要时进行人工确认。',
    updatedAt: nowText(),
  },
  {
    itemId: 4,
    kbId: 2,
    title: '霜霉病风险条件',
    content: '霜霉病常在高湿、通风不足、昼夜温差大时发生，早期可见黄斑，潮湿时叶背可能出现霉层。',
    updatedAt: nowText(),
  },
  {
    itemId: 5,
    kbId: 3,
    title: '卷帘与补光联动',
    content: '当自然光照不足时优先打开卷帘并观察光照变化，若仍低于目标区间再开启补光灯。',
    updatedAt: nowText(),
  },
  {
    itemId: 6,
    kbId: 3,
    title: '通风安全规则',
    content: '风机单次建议运行 5 到 10 分钟，执行后需要回传状态，避免长时间通风造成温度快速下降。',
    updatedAt: nowText(),
  },
];

function selectedReferences(question: string, kbId?: number): KnowledgeReference[] {
  const normalizedQuestion = question.toLowerCase().trim();
  const terms = new Set<string>();
  for (const word of normalizedQuestion.match(/[a-z0-9_]{2,}/g) ?? []) {
    terms.add(word);
  }
  for (const sequence of normalizedQuestion.match(/[\u4e00-\u9fff]{2,}/g) ?? []) {
    terms.add(sequence);
    for (let index = 0; index < sequence.length - 1; index += 1) {
      terms.add(sequence.slice(index, index + 2));
    }
  }
  const items = mockKnowledgeItems
    .filter((item) => !kbId || item.kbId === kbId)
    .map((item) => {
      const title = item.title.toLowerCase();
      const content = item.content.toLowerCase();
      let score = 0;
      for (const term of terms) {
        if (title.includes(term)) score += 2.5;
        if (content.includes(term)) score += 1;
      }
      return { item, score };
    })
    .filter((entry) => entry.score > 0)
    .sort((left, right) => right.score - left.score)
    .slice(0, 3);

  return items.map(({ item, score }, index) => ({
    itemId: item.itemId,
    chunkId: index + 1,
    title: item.title,
    content: item.content,
    score: rounded(Math.min(0.99, 0.55 + score / 10), 2),
    referenceId: `mock-local:${item.itemId}:1`,
    sourceType: 'local',
    sourceName: '本地知识库',
  }));
}

export function buildMockExpertChat(request: ExpertChatRequest): ExpertChatResponse {
  const sensors = request.latest.sensors;
  const diseaseText = request.disease?.summary ?? '当前没有新的病害图片检测结果。';
  const suggestFan = sensors.humidity > 68;
  const references = selectedReferences(request.question, request.knowledge_base_id);
  const referenceText = references.length > 0
    ? `\n\n**本地资料依据**\n${references.map((reference) => `- ${reference.title}：${reference.content}`).join('\n')}`
    : '';
  return {
    message: {
      id: `assistant-${Date.now()}`,
      role: 'assistant',
      created_at: Date.now(),
      content: [
        `结合当前数据，棚内温度 ${sensors.temperature} 摄氏度、湿度 ${sensors.humidity}%RH、光照 ${sensors.light} lux、二氧化碳 ${sensors.co2} ppm。`,
        diseaseText,
        sensors.humidity > 68
          ? '建议先开启风机通风降湿，再观察叶片病斑是否扩散。'
          : '建议保持当前策略，继续每 30 分钟观察环境趋势。',
      ].join('\n') + referenceText,
      references,
      suggested_commands: suggestFan ? [{ command: 'fan_on', value: 1 }] : [],
      suggested_actions: suggestFan ? [
        {
          id: `mock-action-${Date.now()}`,
          type: 'device_command',
          title: '打开风机',
          description: '棚内湿度偏高，建议先通风降湿，执行前需要确认。',
          risk: 'high',
          payload: { command: 'fan_on', value: 1, reason: 'AI助手建议通风降湿' },
          status: 'pending',
        },
      ] : [],
    },
  };
}

export function createMockKnowledgeBase(name: string, description: string): KnowledgeBaseInfo {
  const item = { kbId: nextKnowledgeBaseId++, name, description, enabled: true, updatedAt: nowText() };
  mockKnowledgeBases.unshift(item);
  return item;
}

export function updateMockKnowledgeBase(kbId: number, name: string, description: string): KnowledgeBaseInfo {
  const item = mockKnowledgeBases.find((base) => base.kbId === kbId);
  if (!item) {
    throw new Error('知识库不存在');
  }
  item.name = name;
  item.description = description;
  item.updatedAt = nowText();
  return item;
}

export function deleteMockKnowledgeBase(kbId: number): void {
  const index = mockKnowledgeBases.findIndex((base) => base.kbId === kbId);
  if (index >= 0) {
    mockKnowledgeBases.splice(index, 1);
  }
  for (let i = mockKnowledgeItems.length - 1; i >= 0; i -= 1) {
    if (mockKnowledgeItems[i].kbId === kbId) {
      mockKnowledgeItems.splice(i, 1);
    }
  }
}

export function addMockKnowledgeItem(kbId: number, title: string, content: string): KnowledgeTextAddResult {
  const item = { itemId: nextKnowledgeItemId++, kbId, title, content, updatedAt: nowText() };
  mockKnowledgeItems.unshift(item);
  return { itemId: item.itemId, chunkCount: Math.max(1, Math.ceil(content.length / 80)), updatedAt: item.updatedAt };
}

export function updateMockKnowledgeItem(kbId: number, itemId: number, title: string, content: string): KnowledgeTextAddResult {
  const item = mockKnowledgeItems.find((entry) => entry.kbId === kbId && entry.itemId === itemId);
  if (!item) {
    throw new Error('知识条目不存在');
  }
  item.title = title;
  item.content = content;
  item.updatedAt = nowText();
  return { itemId, chunkCount: Math.max(1, Math.ceil(content.length / 80)), updatedAt: item.updatedAt };
}

export function deleteMockKnowledgeItem(kbId: number, itemId: number): void {
  const index = mockKnowledgeItems.findIndex((entry) => entry.kbId === kbId && entry.itemId === itemId);
  if (index >= 0) {
    mockKnowledgeItems.splice(index, 1);
  }
}

export function analyzeMockKnowledge(kbId: number, question: string): KnowledgeAnalyzeResult {
  const references = selectedReferences(question, kbId);
  const referenceAdvice = references.length > 0
    ? `建议参考匹配到的知识条目：${references.map((reference) => reference.title).join('、')}。`
    : '当前知识库没有找到与问题直接匹配的资料，建议补充关键词或新增知识条目后重试。';
  return {
    answer: `问题：${question}\n${referenceAdvice}`,
    references,
    updatedAt: nowText(),
  };
}
