import {
  buildMockAiAnalysis,
  buildMockHistory,
  buildMockLatest,
  executeMockCommand,
  mockAlarms,
} from '../mock/data';
import type {
  AiAnalysisResponse,
  AlarmRecord,
  CommandResult,
  DeviceCommand,
  HistoryPoint,
  TelemetryPayload,
} from '../types';

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
const useMock = import.meta.env.VITE_USE_MOCK !== 'false';

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
