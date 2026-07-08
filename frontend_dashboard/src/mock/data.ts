import type {
  AiAnalysisResponse,
  AlarmRecord,
  CommandResult,
  DeviceCommand,
  DeviceRuntimeStatus,
  HistoryPoint,
  TelemetryPayload,
} from '../types';

const deviceId = 'sensairshuttle_001';

let runtimeStatus: DeviceRuntimeStatus = {
  wifi: 'connected',
  mqtt: 'connected',
  fan: 0,
  pump: 0,
  light: 0,
  alarm: 0,
};

let tick = 0;

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
      temperature: rounded(27.2 + Math.sin(phase) * 1.7),
      humidity: rounded(61.5 + Math.cos(phase / 1.3) * 4.1),
      pressure: rounded(101.2 + Math.sin(phase / 2) * 0.5),
      gas_resistance: Math.round(16600 + Math.cos(phase / 1.6) * 2200),
      acc_x: rounded(0.01 + Math.sin(phase) * 0.03, 2),
      acc_y: rounded(-0.02 + Math.cos(phase) * 0.03, 2),
      acc_z: rounded(0.98 + Math.sin(phase / 2) * 0.02, 2),
      gyro_x: rounded(0.1 + Math.sin(phase / 3) * 0.07, 2),
      gyro_y: rounded(Math.cos(phase / 2) * 0.05, 2),
      gyro_z: rounded(-0.1 + Math.sin(phase / 2.4) * 0.05, 2),
      mag_x: rounded(12.3 + Math.sin(phase / 2) * 1.2),
      mag_y: rounded(8.6 + Math.cos(phase / 2.4) * 1.1),
      mag_z: rounded(-35.1 + Math.sin(phase / 2.8) * 1.5),
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
      pressure: rounded(101.1 + Math.sin(phase / 2) * 0.7),
      gas_resistance: Math.round(15800 + Math.cos(phase / 1.5) * 2600),
    };
  });
}

export function buildMockAiAnalysis(latest: TelemetryPayload): AiAnalysisResponse {
  const tempHigh = latest.sensors.temperature >= 28;
  const airWatch = latest.sensors.gas_resistance < 15000;
  return {
    device_id: latest.device_id,
    crop: 'tomato',
    risk_level: tempHigh || airWatch ? 'medium' : 'low',
    summary: tempHigh
      ? '当前棚内温度偏高，建议优先开启通风并观察湿度变化。'
      : '当前环境整体稳定，ESP32-C5 采集链路与执行设备状态正常。',
    suggestions: [
      tempHigh ? '开启风机 10 分钟，降低棚内热量积累。' : '保持当前通风策略，继续观察温湿度趋势。',
      latest.sensors.humidity < 58 ? '湿度略低，可短时启动水泵补水。' : '湿度处在适宜区间，避免过量灌溉。',
      airWatch ? '气体阻值下降，建议加强空气流通。' : '空气质量稳定，可维持当前管理节奏。',
    ],
    commands: tempHigh ? [{ command: 'fan_on', value: 1 }] : [],
    updated_at: Date.now(),
  };
}

export const mockAlarms: AlarmRecord[] = [
  {
    id: 'ALM-20260707-001',
    level: 'warning',
    title: '棚内温度接近上限',
    detail: 'BME690 监测温度连续 3 次高于 28 摄氏度，建议开启风机。',
    source: 'ESP32-C5 / BME690',
    timestamp: Date.now() - 18 * 60 * 1000,
    handled: false,
  },
  {
    id: 'ALM-20260707-002',
    level: 'info',
    title: 'MQTT 链路恢复',
    detail: '设备重新连接云端 Broker，遥测数据恢复上传。',
    source: 'Wi-Fi / MQTT',
    timestamp: Date.now() - 54 * 60 * 1000,
    handled: true,
  },
  {
    id: 'ALM-20260707-003',
    level: 'danger',
    title: '空气质量短时波动',
    detail: '气体阻值低于演示阈值，已生成通风建议。',
    source: 'ESP32-C5 / BME690',
    timestamp: Date.now() - 112 * 60 * 1000,
    handled: false,
  },
];

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
  runtimeStatus = status;
  return {
    success: true,
    message: '模拟执行成功，等待 ESP32-C5 返回真实执行结果',
    command,
    executed_at: Date.now(),
    status: { ...runtimeStatus },
  };
}
