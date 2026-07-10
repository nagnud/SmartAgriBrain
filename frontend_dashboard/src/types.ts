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

export interface PersistedDashboardState {
  version: number;
  activeView?: string;
  selectedHistoryMetricKeys?: string[];
  metricTargetRanges?: Record<string, MetricTargetRange>;
  deviceStatus?: DeviceRuntimeStatus;
  commandResults?: CommandResult[];
  smartControlEnabled?: boolean;
  smartControlParamStates?: Record<string, SmartControlParamState>;
  smartControlLastPublishAt?: number | null;
  smartControlPanelOpen?: boolean;
  selectedKbId?: number;
  knowledgeQuestion?: string;
  knowledgeAnswer?: KnowledgeAnalyzeResult | null;
  assistantOpen?: boolean;
  assistantWidth?: number;
  chatInput?: string;
  chatMessages?: ChatMessage[];
}

export interface MetricTargetRange {
  min: number;
  max: number;
}

export interface AiCommand {
  command: string;
  value: number;
}

export interface AiRiskFactor {
  key: string;
  label: string;
  detail: string;
  state: StatusLevel;
}

export type AssistantActionType =
  | 'navigate_view'
  | 'open_panel'
  | 'device_command'
  | 'smart_control'
  | 'knowledge_base'
  | 'knowledge_item'
  | 'run_knowledge_analysis'
  | 'refresh_data';

export type AssistantActionRisk = 'normal' | 'medium' | 'high';
export type AssistantActionStatus = 'pending' | 'executed' | 'canceled' | 'failed';

export interface AssistantAction {
  id: string;
  type: AssistantActionType;
  title: string;
  description: string;
  risk: AssistantActionRisk;
  payload: Record<string, unknown>;
  status?: AssistantActionStatus;
  error?: string;
}

export interface AiAnalysisResponse {
  device_id: string;
  crop: string;
  ai_connected?: boolean;
  risk_level: 'low' | 'medium' | 'high';
  risk_score?: number;
  risk_status?: string;
  risk_factors?: AiRiskFactor[];
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
  action?: string;
  fieldId?: string;
  fieldName?: string;
  source?: string;
  demands?: SmartControlDemands;
  waterDemand?: number;
  lightDemand?: number;
  heatDemand?: number;
  coolDemand?: number;
  ventDemand?: number;
  co2Demand?: number;
  tempDemand?: number;
  airDemand?: number;
  mistDemand?: number;
  timestamp?: number;
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
  typing?: boolean;
  references?: KnowledgeReference[];
  suggested_commands?: AiCommand[];
  suggested_actions?: AssistantAction[];
}

export interface ExpertChatRequest {
  question: string;
  image_url?: string;
  latest: TelemetryPayload;
  disease?: DiseaseDetectionResult | null;
  knowledge_base_id?: number;
  current_view?: string;
  knowledge_bases?: KnowledgeBaseInfo[];
  knowledge_items?: KnowledgeItemInfo[];
  command_results?: CommandResult[];
}

export interface ExpertChatResponse {
  message: ChatMessage;
  references?: KnowledgeReference[];
  actions?: AssistantAction[];
}

export interface VoiceTranscriptionResponse {
  ok: boolean;
  text: string;
  partial: boolean;
  final: boolean;
  message: string;
}

export interface VoiceTranscriptionStatus {
  ok: boolean;
  configured: boolean;
  provider: string;
  model: string;
  message: string;
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

export type SmartControlParamKey = 'water' | 'light' | 'heat' | 'cool' | 'vent' | 'co2';
export type SmartControlParamMode = 'auto' | 'manual';

export interface SmartControlDemands {
  water: number;
  light: number;
  heat: number;
  cool: number;
  vent: number;
  co2: number;
}

export interface SmartControlParamState {
  key: SmartControlParamKey;
  mode: SmartControlParamMode;
  value: number;
  lastManualValue: number;
}

export interface SmartControlDecision {
  demands: SmartControlDemands;
  summary: string;
  status: string;
  confidence: number;
  riskLevel: 'normal' | 'watch' | 'urgent';
  weatherSummary: string;
}
