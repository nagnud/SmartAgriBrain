import type {
  AiAnalysisResponse,
  ChatMessage,
  CommandResult,
  DeviceCommand,
  DeviceRuntimeStatus,
  DiseaseDetectionResult,
  ExpertChatRequest,
  ExpertChatResponse,
  HistoryPoint,
  KnowledgeAnalyzeResult,
  KnowledgeBaseInfo,
  KnowledgeItemInfo,
  KnowledgeReference,
  KnowledgeTextAddResult,
  TelemetryPayload,
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
let lastSmartControlDemands = {
  water: 0,
  light: 0,
  heat: 0,
  cool: 0,
  vent: 0,
  co2: 0,
};
let nextKnowledgeBaseId = 4;
let nextKnowledgeItemId = 9;
let lastDiseaseResult: DiseaseDetectionResult | null = null;

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

export function buildMockLatest(): TelemetryPayload {
  tick += 1;
  const phase = tick / 4;
  return {
    device_id: deviceId,
    timestamp: Date.now(),
    sensors: {
      temperature: rounded(27.4 + Math.sin(phase) * 1.9),
      humidity: rounded(63.5 + Math.cos(phase / 1.3) * 5.2),
      pressure: rounded(101.1 + Math.sin(phase / 2) * 0.5),
      gas_resistance: Math.round(16600 + Math.cos(phase / 1.6) * 2200),
      light: Math.round(16800 + Math.sin(phase / 1.8) * 4200),
      co2: Math.round(610 + Math.cos(phase / 1.7) * 95),
      soil_moisture: rounded(58.6 + Math.sin(phase / 1.5) * 6.4),
      soil_ec: rounded(1.82 + Math.cos(phase / 2.1) * 0.28, 2),
    },
    status: { ...runtimeStatus },
  };
}

export function buildMockHistory(): HistoryPoint[] {
  const now = Date.now();
  return Array.from({ length: 36 }, (_, index) => {
    const step = 35 - index;
    const phase = index / 4;
    return {
      timestamp: now - step * 10 * 60 * 1000,
      temperature: rounded(25.8 + Math.sin(phase) * 2.4),
      humidity: rounded(62 + Math.cos(phase / 1.2) * 5.8),
      gas_resistance: Math.round(15800 + Math.cos(phase / 1.5) * 2600),
      light: Math.round(14500 + Math.sin(phase / 1.6) * 5200),
      co2: Math.round(620 + Math.cos(phase / 1.8) * 130),
      soil_moisture: rounded(59 + Math.sin(phase / 1.7) * 7.1),
      soil_ec: rounded(1.75 + Math.cos(phase / 2) * 0.35, 2),
    };
  });
}

export function buildMockAiAnalysis(latest: TelemetryPayload): AiAnalysisResponse {
  const tempHigh = latest.sensors.temperature >= 28.5;
  const humidityHigh = latest.sensors.humidity >= 68;
  const lightLow = latest.sensors.light < 15000;
  const co2Low = latest.sensors.co2 < 560;
  const soilWet = latest.sensors.soil_moisture > 64;
  const risk = humidityHigh || soilWet ? 'medium' : tempHigh || lightLow || co2Low ? 'medium' : 'low';
  return {
    device_id: latest.device_id,
    crop: 'tomato',
    risk_level: risk,
    summary: humidityHigh
      ? '当前湿度偏高，番茄叶面结露和霜霉病风险上升，建议优先通风降湿。'
      : '当前大棚环境整体稳定，可继续保持自动巡检和轻量通风策略。',
    basis: [
      `空气湿度 ${latest.sensors.humidity}%RH，土壤湿度 ${latest.sensors.soil_moisture}%`,
      `光照 ${latest.sensors.light} lux，CO2 ${latest.sensors.co2} ppm`,
      '知识库规则：高湿与通风不足会提高番茄病害发生概率',
    ],
    suggestions: [
      humidityHigh ? '开启风机 10 分钟，降低棚内湿度并减少叶面结露。' : '保持当前通风节奏，继续观察湿度曲线。',
      lightLow ? '光照不足，可开启补光灯并保持卷帘打开。' : '光照处于可用区间，避免长时间强补光。',
      soilWet ? '土壤湿度偏高，暂停水泵并观察 2 小时。' : '土壤湿度适中，维持小水量精准灌溉。',
      co2Low ? 'CO2 偏低，可在通风后短时补充气肥。' : 'CO2 浓度稳定，暂不需要额外干预。',
    ],
    commands: [
      ...(humidityHigh ? [{ command: 'fan_on', value: 1 }] : []),
      ...(lightLow ? [{ command: 'light_on', value: 1 }, { command: 'curtain_open', value: 1 }] : []),
      ...(soilWet ? [{ command: 'pump_off', value: 0 }] : []),
    ],
    updated_at: Date.now(),
  };
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

export const mockAlarms = [
  {
    id: 'ALM-20260707-001',
    level: 'warning' as const,
    title: '棚内湿度接近上限',
    detail: '湿度连续 3 次高于 68%RH，建议开启风机并检查叶面结露。',
    source: 'ESP32-C5 / 环境传感器',
    timestamp: Date.now() - 18 * 60 * 1000,
    handled: false,
  },
  {
    id: 'ALM-20260707-002',
    level: 'info' as const,
    title: 'MQTT 链路恢复',
    detail: '设备重新连接云端 Broker，遥测数据恢复上传。',
    source: 'Wi-Fi / MQTT',
    timestamp: Date.now() - 54 * 60 * 1000,
    handled: true,
  },
  {
    id: 'ALM-20260707-003',
    level: 'danger' as const,
    title: '疑似病害风险',
    detail: '图像检测到疑似叶斑区域，叠加高湿环境后生成中等风险建议。',
    source: 'YOLO / RAG',
    timestamp: Date.now() - 112 * 60 * 1000,
    handled: false,
  },
];

export function executeMockCommand(command: DeviceCommand): CommandResult {
  const status = { ...runtimeStatus };
  if (command.command === 'smart_control_update' && command.demands) {
    lastSmartControlDemands = { ...command.demands };
  }
  if (command.command === 'smart_control_stop') {
    lastSmartControlDemands = {
      water: 0,
      light: 0,
      heat: 0,
      cool: 0,
      vent: 0,
      co2: 0,
    };
  }
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
    message: '模拟执行成功，等待 ESP32-C5 返回真实执行结果',
    command,
    executed_at: Date.now(),
    status: { ...runtimeStatus },
  };
}

export function buildMockDiseaseDetection(imageUrl: string): DiseaseDetectionResult {
  lastDiseaseResult = {
    image_url: imageUrl,
    crop: 'tomato',
    model: 'YOLO11n-demo',
    detections: [
      {
        id: 'det-1',
        label: '疑似叶斑病',
        class_name: 'leaf_spot',
        confidence: 0.88,
        bbox: { x: 31, y: 24, width: 30, height: 28 },
        severity: 'medium',
      },
      {
        id: 'det-2',
        label: '早期霜霉风险',
        class_name: 'downy_mildew',
        confidence: 0.74,
        bbox: { x: 58, y: 48, width: 22, height: 20 },
        severity: 'low',
      },
    ],
    summary: '检测到 2 处疑似病斑，整体为中等风险，建议结合湿度趋势复核。',
    explanation: '图像中存在不规则黄褐色斑块，叠加近期湿度偏高，符合番茄叶斑病或霜霉病早期风险特征。',
    suggestions: [
      '立即检查叶背是否有霉层，并拍摄更清晰的近景图片复核。',
      '优先通风降湿，避免叶面长时间结露。',
      '隔离明显病叶，必要时请人工确认后再用药。',
    ],
    processed_at: Date.now(),
  };
  return lastDiseaseResult;
}

export const mockKnowledgeBases: KnowledgeBaseInfo[] = [
  { kbId: 1, name: '番茄管理知识库', description: '温室番茄水肥、光照、CO2 和病害管理经验', enabled: true, updatedAt: nowText() },
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
    title: '土壤 EC 管理',
    content: '番茄基质 EC 建议维持在 1.5 到 2.4 mS/cm，过高会造成盐害，过低会影响养分供应。',
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

function selectedReferences(kbId?: number): KnowledgeReference[] {
  const items = mockKnowledgeItems.filter((item) => !kbId || item.kbId === kbId).slice(0, 3);
  return items.map((item, index) => ({
    itemId: item.itemId,
    chunkId: index + 1,
    title: item.title,
    content: item.content,
    score: rounded(0.92 - index * 0.08, 2),
  }));
}

export function buildMockExpertChat(request: ExpertChatRequest): ExpertChatResponse {
  const sensors = request.latest.sensors;
  const diseaseText = request.disease?.summary ?? lastDiseaseResult?.summary ?? '当前没有新的病害图片检测结果。';
  const suggestFan = sensors.humidity > 68;
  return {
    message: {
      id: `assistant-${Date.now()}`,
      role: 'assistant',
      created_at: Date.now(),
      content: [
        `结合当前数据，棚内温度 ${sensors.temperature} 摄氏度、湿度 ${sensors.humidity}%RH、光照 ${sensors.light} lux、CO2 ${sensors.co2} ppm。`,
        diseaseText,
        sensors.humidity > 68
          ? '建议先开启风机通风降湿，再观察叶片病斑是否扩散。'
          : '建议保持当前策略，继续每 30 分钟观察环境趋势。',
      ].join('\n'),
      references: selectedReferences(request.knowledge_base_id),
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
  const references = selectedReferences(kbId);
  return {
    answer: `问题：${question}\n建议优先参考当前知识库中的高湿管理和设备联动规则，先稳定环境，再复查作物叶片状态。`,
    references,
    updatedAt: nowText(),
  };
}
