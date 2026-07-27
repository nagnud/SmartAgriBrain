export type ConnectionState = 'connected' | 'disconnected' | 'warning';
export type StatusLevel = 'good' | 'watch' | 'danger' | 'neutral';
export type HistoryMetricKey = 'temperature' | 'humidity' | 'light' | 'co2' | 'soil_moisture' | 'soil_ec' | 'gas_resistance';

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
}

export interface TelemetryPayload {
  device_id: string;
  timestamp: number;
  sensors: SensorSnapshot;
  status: DeviceRuntimeStatus;
}

export interface EdgeDeviceState {
  device_id: string;
  role: 'sensor_actuator' | 'voice_display';
  online: boolean;
  last_seen_at: number;
  status: Record<string, unknown>;
}

export interface SiteState {
  schema_version: string;
  site_id: string;
  updated_at: number;
  sensors: Record<string, number | null>;
  quality: Record<string, string>;
  actuators: Record<string, unknown>;
  devices: Record<string, EdgeDeviceState>;
}

export interface SharedAssistantAction {
  id: string;
  type: string;
  risk: string;
  state: string;
  payload: Record<string, unknown>;
  expires_at: number;
}

export interface SharedAssistantMessage {
  id: string;
  session_id: string;
  site_id: string;
  role: 'user' | 'assistant';
  channel: string;
  content: string;
  created_at: number;
  actions: SharedAssistantAction[];
}

export interface SharedAssistantConversation {
  session_id: string;
  messages: SharedAssistantMessage[];
}

export interface HistoryPoint {
  timestamp: number;
  temperature: number | null;
  light: number | null;
  co2: number | null;
  soil_moisture: number | null;
  // Reserved for sensors that are not currently rendered in the Web UI.
  humidity: number | null;
  gas_resistance: number | null;
  soil_ec: number | null;
}

export interface WeatherPayload {
  location: string;
  condition: string;
  temperature: number;
  humidity: number | null;
  wind_direction: string;
  wind_level: string;
  updated_at: number;
}

export interface WeatherModule<T = unknown> {
  available: boolean;
  name?: string;
  data?: T;
  reason?: string;
  updated_at?: number;
}

export interface WeatherCurrentDetail extends WeatherPayload {
  city?: string;
  feels_like?: number | null;
  wind_speed?: number | null;
  wind_scale?: number | null;
  pressure?: number | null;
  visibility?: number | null;
  clouds?: number | null;
  dew_point?: number | null;
  last_update?: string;
}

export interface WeatherDailyItem {
  date?: string;
  condition_day?: string | null;
  condition_night?: string | null;
  high?: number | null;
  low?: number | null;
  rainfall?: number | null;
  precip?: number | null;
  humidity?: number | null;
  wind_direction?: string | null;
  wind_speed?: number | null;
  wind_scale?: number | null;
}

export interface WeatherHourlyItem {
  time?: string;
  condition?: string | null;
  temperature?: number | null;
  humidity?: number | null;
  rainfall?: number | null;
  precip?: number | null;
  wind_direction?: string | null;
  wind_speed?: number | null;
  wind_scale?: number | null;
}

export interface AirQualityData {
  aqi?: number | null;
  quality?: string | null;
  pm25?: number | null;
  pm10?: number | null;
  o3?: number | null;
  no2?: number | null;
  so2?: number | null;
  co?: number | null;
}

export type LifeIndexData = Record<string, { brief?: string | null; details?: string | null }>;

export interface WeatherAlarmItem {
  title?: string | null;
  type?: string | null;
  level?: string | null;
  status?: string | null;
  description?: string | null;
  pub_date?: string | null;
}

export interface WeatherCapability {
  key: string;
  name: string;
  available: boolean;
  reason?: string;
}

export interface WeatherBundle {
  city: string;
  updated_at: number;
  current: WeatherModule<WeatherCurrentDetail>;
  daily: WeatherModule<WeatherDailyItem[]>;
  hourly: WeatherModule<WeatherHourlyItem[]>;
  air: WeatherModule<AirQualityData>;
  life: WeatherModule<LifeIndexData>;
  alarms: WeatherModule<WeatherAlarmItem[]>;
  registered_capabilities: WeatherCapability[];
}

export interface WeatherCityOption {
  id?: string;
  name?: string;
  path?: string;
  country?: string;
  timezone?: string;
  timezone_offset?: string;
  level?: 'province' | 'city';
  province?: string;
  direct?: boolean;
  cities?: WeatherCityOption[];
}

export interface PersistedDashboardState {
  version: number;
  activeView?: string;
  selectedHistoryMetricKeys?: string[];
  historyWindowDurationMs?: number;
  metricTargetRanges?: Record<string, MetricTargetRange>;
  selectedKbId?: number;
  knowledgeQuestion?: string;
  knowledgeAnswer?: KnowledgeAnalyzeResult | null;
  assistantOpen?: boolean;
  assistantWidth?: number;
  chatInput?: string;
  chatMessages?: ChatMessage[];
  assistantThreads?: AssistantThread[];
  activeAssistantThreadId?: string;
  weatherCity?: string;
  weatherPanelOpen?: boolean;
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
  | 'reply_choice'
  | 'navigate_view'
  | 'open_panel'
  | 'device_command'
  | 'smart_control'
  | 'knowledge_base'
  | 'knowledge_item'
  | 'run_knowledge_analysis'
  | 'refresh_data'
  | 'send_position'
  | 'water_gun_target';

export type AssistantActionRisk = 'normal' | 'medium' | 'high';
export type AssistantActionStatus = 'pending' | 'confirmed' | 'executed' | 'canceled' | 'failed';

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
  references?: KnowledgeReference[];
  retrievalStatus?: RetrievalStatus;
  updated_at: number;
}

export interface AlarmRecord {
  id: string;
  device_id?: string;
  level: 'info' | 'warning' | 'danger';
  title: string;
  detail: string;
  source: string;
  timestamp: number;
  handled: boolean;
  state: 'open' | 'acknowledged' | 'resolved';
  handled_at?: number | null;
  resolved_at?: number | null;
}

export interface DeviceHealth {
  device_id: string;
  device_name: string;
  online: boolean;
  transport: 'http' | 'mqtt';
  last_seen_at: number;
  last_telemetry_at: number;
  offline_after_seconds: number;
}

export interface AlarmSettingsResponse {
  device_id: string;
  configured: boolean;
  ranges: Record<HistoryMetricKey, MetricTargetRange>;
  updated_at?: string | null;
}

export interface DetectionBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface CameraPositionConfig {
  image_width: number;
  image_height: number;
  fx: number;
  fy: number;
  cx: number;
  cy: number;
  distortion: number[];
  camera_height_mm: number;
  pitch_down_deg: number;
  yaw_deg: number;
  roll_deg: number;
}

export interface BackendCameraConfig {
  device_index: number;
  width: number;
  height: number;
  fps: number;
}

export interface PositionCandidate {
  id: string;
  label: string;
  confidence: number;
  bbox: DetectionBox;
  camera_range_mm: number;
  ground_range_mm: number;
  bearing_deg: number;
  description?: string;
  attributes?: Record<string, string>;
  anchor: { x: number; y: number };
  anchor_type: 'visual_center' | 'surface_center' | 'footprint_center' | 'custom';
  estimated_height_mm: number;
  effective_height_mm: number;
  height_confidence: number;
  height_fallback: boolean;
  anchor_reason: string;
}

export interface PositionLocateResult {
  status: 'located' | 'multiple' | 'not_found' | 'calibration_missing' | 'invalid_geometry';
  result_id?: string;
  message: string;
  captured_at: number;
  candidates: PositionCandidate[];
  selected?: PositionCandidate;
  annotated_image_url?: string;
  image_width: number;
  image_height: number;
}

export interface CropPositionInfo {
  id: string;
  label: string;
  crop_name: string;
  confidence: number;
  bbox: DetectionBox;
  anchor: { x: number; y: number };
  clear_enough: boolean;
  growth_status: string;
  pest_disease_status: string;
  severity: 'healthy' | 'low' | 'medium' | 'high';
  summary: string;
  ground_range_mm: number | null;
  bearing_deg: number | null;
  coordinate_status: 'located' | 'calibration_missing' | 'invalid_geometry';
}

export interface CurrentCropPositionsResult {
  status: 'ok' | 'calibration_missing';
  message: string;
  captured_at: number;
  crops: CropPositionInfo[];
}

export type WaterGunMode = 'static' | 'dynamic';
export type WaterGunTargetSource = 'manual' | 'vision';
export type WaterGunSpraySchedule = 'continuous' | 'timed';
export type WaterGunStopReason = 'idle' | 'manual' | 'timed_complete' | 'target_changed' | 'mode_changed' | 'dynamic_timeout';

export interface WaterGunState {
  site_id: string;
  device_id: string;
  mode: WaterGunMode;
  ground_range_mm: number;
  bearing_deg: number;
  spray_enabled: boolean;
  source: WaterGunTargetSource;
  target_label: string;
  session_id: string | null;
  sequence: number;
  updated_at: number;
  last_command_id: number | null;
  timed_out: boolean;
  pump_control_percent: number;
  spray_schedule: WaterGunSpraySchedule;
  spray_duration_seconds: number | null;
  spray_ends_at: number | null;
  remaining_seconds: number | null;
  stop_reason: WaterGunStopReason;
}

export interface WaterGunTargetInput {
  ground_range_mm: number;
  bearing_deg: number;
  device_id?: string;
  source?: WaterGunTargetSource;
  target_label?: string;
  spray_enabled?: boolean;
  spray_schedule?: WaterGunSpraySchedule;
  spray_duration_seconds?: number | null;
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
  references?: KnowledgeReference[];
  retrievalStatus?: RetrievalStatus;
  processed_at: number;
}

export interface DiseasePhotoInfo {
  photoId: number;
  url: string;
  originalName: string;
  mimeType: string;
  size: number;
  createdAt: string;
  analysisResult?: DiseaseDetectionResult | null;
}

export interface KnowledgeReference {
  itemId?: number;
  chunkId?: number;
  title: string;
  content: string;
  score: number;
  referenceId?: string;
  sourceType?: 'local' | 'online';
  sourceName?: string;
  url?: string | null;
  publishedAt?: string | null;
  retrievedAt?: string | null;
}

export type RetrievalMode = 'auto' | 'force' | 'off';
export type RetrievalStatus = 'not_used' | 'success' | 'partial' | 'unavailable';

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  image_url?: string;
  created_at: number;
  typing?: boolean;
  references?: KnowledgeReference[];
  referencesVerified?: boolean;
  retrievalStatus?: RetrievalStatus;
  suggested_commands?: AiCommand[];
  suggested_actions?: AssistantAction[];
  position_result?: PositionLocateResult;
  context?: Record<string, unknown>;
}

export interface AssistantSeedMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  created_at: number;
}

export interface AssistantTurnRequest {
  session_id?: string;
  site_id?: string;
  channel: 'web' | 'edge_text';
  message_id: string;
  text: string;
  seed_history?: AssistantSeedMessage[];
}

export interface AssistantTurnAccepted {
  turn_id: string;
  session_id: string;
  state: 'queued';
}

export interface AssistantPreferenceItem {
  key: string;
  value: string;
  updated_at: number;
}

export type AssistantTurnEvent =
  | { event: 'progress'; data: { turn_id: string; text: string } }
  | { event: 'completed'; data: { turn_id: string; session_id: string; response: ExpertChatResponse } }
  | { event: 'failed'; data: { turn_id?: string; session_id?: string; message: string } };

export interface AssistantThread {
  id: string;
  title: string;
  pinned: boolean;
  created_at: number;
  updated_at: number;
  messages: ChatMessage[];
}

export interface ExpertChatRequest {
  question: string;
  image_url?: string;
  latest: TelemetryPayload;
  disease?: DiseaseDetectionResult | null;
  weather?: WeatherPayload | null;
  weather_bundle?: WeatherBundle | null;
  ai_analysis?: AiAnalysisResponse | null;
  camera_analysis?: DiseaseDetectionResult | null;
  knowledge_base_id?: number;
  current_view?: string;
  knowledge_bases?: KnowledgeBaseInfo[];
  knowledge_items?: KnowledgeItemInfo[];
  retrieval_mode?: RetrievalMode;
}

export interface ExpertChatResponse {
  message: ChatMessage;
  references?: KnowledgeReference[];
  actions?: AssistantAction[];
  retrievalStatus?: RetrievalStatus;
}

export interface AgriSourceInfo {
  sourceId: 'agrovoc' | 'eppo' | 'natesc';
  name: string;
  description: string;
  sourceType: 'api' | 'website';
  enabled: boolean;
  configured: boolean;
  status: 'unknown' | 'available' | 'unavailable' | 'needs_configuration' | 'disabled';
  lastCheckedAt?: string | null;
  lastError?: string;
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
