export type ConnectionState = 'connected' | 'disconnected' | 'warning';
export type StatusLevel = 'good' | 'watch' | 'danger' | 'neutral';

export interface SensorSnapshot {
  temperature: number;
  humidity: number;
  pressure: number;
  gas_resistance: number;
  light: number;
  co2: number;
  soil_moisture: number;
  soil_ec: number;
}

export interface DeviceRuntimeStatus {
  wifi: ConnectionState;
  mqtt: ConnectionState;
  fan: number;
  pump: number;
  light: number;
  alarm: number;
  curtain: number;
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
  gas_resistance: number;
  light: number;
  co2: number;
  soil_moisture: number;
  soil_ec: number;
}

export interface WeatherPayload {
  location: string;
  condition: string;
  temperature: number;
  humidity: number;
  wind_direction: string;
  wind_level: string;
  updated_at: number;
}

export interface MetricTargetRange {
  min: number;
  max: number;
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
  basis: string[];
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

export interface DetectionBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface DiseaseDetection {
  id: string;
  label: string;
  class_name: string;
  confidence: number;
  bbox: DetectionBox;
  severity: 'healthy' | 'low' | 'medium' | 'high';
}

export interface DiseaseDetectionResult {
  image_url: string;
  crop: string;
  model: string;
  detections: DiseaseDetection[];
  summary: string;
  explanation: string;
  suggestions: string[];
  processed_at: number;
}

export interface KnowledgeReference {
  itemId: number;
  chunkId: number;
  title: string;
  content: string;
  score: number;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  image_url?: string;
  created_at: number;
  references?: KnowledgeReference[];
  suggested_commands?: AiCommand[];
}

export interface ExpertChatRequest {
  question: string;
  image_url?: string;
  latest: TelemetryPayload;
  disease?: DiseaseDetectionResult | null;
  knowledge_base_id?: number;
}

export interface ExpertChatResponse {
  message: ChatMessage;
}

export interface KnowledgeBaseInfo {
  kbId: number;
  name: string;
  description: string;
  enabled: boolean;
  updatedAt: string;
}

export interface KnowledgeItemInfo {
  itemId: number;
  kbId: number;
  title: string;
  content: string;
  updatedAt: string;
}

export interface KnowledgeTextAddResult {
  itemId: number;
  chunkCount: number;
  updatedAt: string;
}

export interface KnowledgeAnalyzeResult {
  answer: string;
  references: KnowledgeReference[];
  updatedAt: string;
}
