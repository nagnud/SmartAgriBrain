export type ConnectionState = 'connected' | 'disconnected' | 'warning';

export interface SensorSnapshot {
  temperature: number;
  humidity: number;
  pressure: number;
  gas_resistance: number;
  acc_x: number;
  acc_y: number;
  acc_z: number;
  gyro_x: number;
  gyro_y: number;
  gyro_z: number;
  mag_x: number;
  mag_y: number;
  mag_z: number;
}

export interface DeviceRuntimeStatus {
  wifi: ConnectionState;
  mqtt: ConnectionState;
  fan: number;
  pump: number;
  light: number;
  alarm: number;
}

export interface TelemetryPayload {
  device_id: string;
  timestamp: number;
  sensors: SensorSnapshot;
  status: DeviceRuntimeStatus;
}

export interface HistoryPoint {
  timestamp: number;
  temperature: number;
  humidity: number;
  pressure: number;
  gas_resistance: number;
}

export interface AiCommand {
  command: string;
  value: number;
}

export interface AiAnalysisResponse {
  device_id: string;
  crop: string;
  risk_level: 'low' | 'medium' | 'high';
  summary: string;
  suggestions: string[];
  commands: AiCommand[];
  updated_at: number;
}

export interface DeviceCommand {
  device_id: string;
  command: string;
  value: number;
  reason: string;
}

export interface CommandResult {
  success: boolean;
  message: string;
  command: DeviceCommand;
  executed_at: number;
  status: DeviceRuntimeStatus;
}

export interface AlarmRecord {
  id: string;
  level: 'info' | 'warning' | 'danger';
  title: string;
  detail: string;
  source: string;
  timestamp: number;
  handled: boolean;
}
