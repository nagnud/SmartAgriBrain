<script setup lang="ts">
import type { Component } from 'vue';
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
import type { EChartsOption } from 'echarts';
import {
  Activity,
  AlertTriangle,
  BarChart3,
  Bell,
  Bot,
  Cpu,
  Droplets,
  Fan,
  Gauge,
  History,
  Home,
  Lightbulb,
  Magnet,
  RadioTower,
  RefreshCw,
  ShieldCheck,
  Thermometer,
  ToggleLeft,
  Wifi,
  Wind,
  Zap,
} from '@lucide/vue';
import EChartPanel from './components/EChartPanel.vue';
import MetricCard from './components/MetricCard.vue';
import StatusPill from './components/StatusPill.vue';
import {
  analyzeFarm,
  getAlarmRecords,
  getDeviceHistory,
  getLatestTelemetry,
  sendDeviceCommand,
} from './services/api';
import type {
  AiAnalysisResponse,
  AlarmRecord,
  CommandResult,
  DeviceCommand,
  HistoryPoint,
  TelemetryPayload,
} from './types';
import { airQualityFromGasResistance, formatDateTime, formatTime, numberText } from './utils/format';

type ViewKey = 'overview' | 'realtime' | 'history' | 'ai' | 'control' | 'alarms';

interface NavItem {
  key: ViewKey;
  label: string;
  icon: Component;
}

const navItems: NavItem[] = [
  { key: 'overview', label: '首页总览', icon: Home },
  { key: 'realtime', label: '实时监测', icon: Activity },
  { key: 'history', label: '历史曲线', icon: BarChart3 },
  { key: 'ai', label: 'AI 农事建议', icon: Bot },
  { key: 'control', label: '设备控制', icon: ToggleLeft },
  { key: 'alarms', label: '报警记录', icon: Bell },
];

const activeView = ref<ViewKey>('overview');
const latest = ref<TelemetryPayload | null>(null);
const historyPoints = ref<HistoryPoint[]>([]);
const aiAnalysis = ref<AiAnalysisResponse | null>(null);
const alarms = ref<AlarmRecord[]>([]);
const commandResults = ref<CommandResult[]>([]);
const loading = ref(true);
const refreshing = ref(false);
let refreshTimer: number | undefined;

const currentAirQuality = computed(() => {
  if (!latest.value) {
    return { label: '等待数据', level: 'watch' as const };
  }
  return airQualityFromGasResistance(latest.value.sensors.gas_resistance);
});

const metricCards = computed(() => {
  if (!latest.value) {
    return [];
  }
  const sensors = latest.value.sensors;
  const tempState = sensors.temperature > 30 ? 'danger' : sensors.temperature > 28 ? 'watch' : 'good';
  const humidityState = sensors.humidity < 55 || sensors.humidity > 72 ? 'watch' : 'good';
  const pressureState = sensors.pressure < 99 || sensors.pressure > 103 ? 'watch' : 'good';
  const gasState = currentAirQuality.value.level === 'danger' ? 'danger' : currentAirQuality.value.level === 'watch' ? 'watch' : 'good';
  return [
    {
      title: '棚内温度',
      value: numberText(sensors.temperature),
      unit: '摄氏度',
      hint: tempState === 'good' ? 'BME690 温度正常' : '温度偏高，建议通风',
      state: tempState,
      icon: Thermometer,
    },
    {
      title: '环境湿度',
      value: numberText(sensors.humidity),
      unit: '%RH',
      hint: humidityState === 'good' ? '湿度处在适宜区间' : '湿度接近阈值',
      state: humidityState,
      icon: Droplets,
    },
    {
      title: '大气压',
      value: numberText(sensors.pressure),
      unit: 'kPa',
      hint: pressureState === 'good' ? '气压波动稳定' : '气压出现波动',
      state: pressureState,
      icon: Gauge,
    },
    {
      title: '气体阻值',
      value: String(Math.round(sensors.gas_resistance)),
      unit: 'Ω',
      hint: currentAirQuality.value.label,
      state: gasState,
      icon: Wind,
    },
  ] as const;
});

const historyChartOption = computed<EChartsOption>(() => {
  const labels = historyPoints.value.map((point) => formatTime(point.timestamp));
  return {
    tooltip: { trigger: 'axis' },
    legend: { top: 0, data: ['温度', '湿度', '气压', '气体阻值'] },
    grid: { left: 42, right: 54, top: 48, bottom: 34 },
    xAxis: { type: 'category', boundaryGap: false, data: labels },
    yAxis: [
      { type: 'value', name: '环境', min: 0, max: 110 },
      { type: 'value', name: '气体阻值', min: 9000, max: 21000 },
    ],
    series: [
      { name: '温度', type: 'line', smooth: true, data: historyPoints.value.map((p) => p.temperature), color: '#D68C1F' },
      { name: '湿度', type: 'line', smooth: true, data: historyPoints.value.map((p) => p.humidity), color: '#2C7DA0' },
      { name: '气压', type: 'line', smooth: true, data: historyPoints.value.map((p) => p.pressure), color: '#7FB069' },
      {
        name: '气体阻值',
        type: 'line',
        smooth: true,
        yAxisIndex: 1,
        data: historyPoints.value.map((p) => p.gas_resistance),
        color: '#8A6A47',
      },
    ],
  };
});

const motionChartOption = computed<EChartsOption>(() => {
  const sensors = latest.value?.sensors;
  return {
    tooltip: { trigger: 'axis' },
    legend: { top: 0, data: ['加速度', '陀螺仪', '磁力计'] },
    grid: { left: 42, right: 28, top: 48, bottom: 34 },
    xAxis: { type: 'category', data: ['X', 'Y', 'Z'] },
    yAxis: { type: 'value' },
    series: [
      {
        name: '加速度',
        type: 'bar',
        data: sensors ? [sensors.acc_x, sensors.acc_y, sensors.acc_z] : [],
        color: '#2F8F4E',
      },
      {
        name: '陀螺仪',
        type: 'bar',
        data: sensors ? [sensors.gyro_x, sensors.gyro_y, sensors.gyro_z] : [],
        color: '#2C7DA0',
      },
      {
        name: '磁力计',
        type: 'bar',
        data: sensors ? [sensors.mag_x, sensors.mag_y, sensors.mag_z] : [],
        color: '#D68C1F',
      },
    ],
  };
});

const statusSummary = computed(() => {
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
    { label: status.alarm ? '报警器开启' : '报警器关闭', state: status.alarm ? 'danger' : 'neutral' },
  ] as const;
});

const activeAlarms = computed(() => alarms.value.filter((item) => !item.handled).length);

async function loadDashboard(isBackground = false): Promise<void> {
  if (isBackground) {
    refreshing.value = true;
  } else {
    loading.value = true;
  }
  try {
    const nextLatest = await getLatestTelemetry();
    latest.value = nextLatest;
    const [nextHistory, nextAi, nextAlarms] = await Promise.all([
      getDeviceHistory(),
      analyzeFarm(nextLatest),
      getAlarmRecords(),
    ]);
    historyPoints.value = nextHistory;
    aiAnalysis.value = nextAi;
    alarms.value = nextAlarms;
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
  commandResults.value = [result, ...commandResults.value].slice(0, 8);
  latest.value = {
    ...latest.value,
    timestamp: result.executed_at,
    status: result.status,
  };
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

function riskLabel(level: AiAnalysisResponse['risk_level']): string {
  if (level === 'high') {
    return '高风险';
  }
  if (level === 'medium') {
    return '中等风险';
  }
  return '低风险';
}

onMounted(() => {
  void loadDashboard();
  refreshTimer = window.setInterval(() => {
    void loadDashboard(true);
  }, 5000);
});

onBeforeUnmount(() => {
  if (refreshTimer) {
    window.clearInterval(refreshTimer);
  }
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

      <div class="sidebar-card">
        <span>比赛重点</span>
        <strong>端侧采集 + 联网 + 远程执行</strong>
        <p>Web 作为电脑端展示平台，突出 ESP32-C5 数据链路和控制闭环。</p>
      </div>
    </aside>

    <main class="workspace">
      <header class="topbar">
        <div>
          <p class="eyebrow">Espressif Track / SensairShuttle</p>
          <h1>智慧大棚远程监控与控制平台</h1>
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
        <RadioTower :size="34" />
        <span>正在读取 ESP32-C5 模拟遥测数据...</span>
      </section>

      <template v-else-if="latest">
        <section v-show="activeView === 'overview'" class="view-stack">
          <div class="hero-panel">
            <div>
              <p class="eyebrow">端云协同状态</p>
              <h2>ESP32-C5 正在通过 Wi-Fi / MQTT 上报环境与姿态数据</h2>
              <p>
                最近采样 {{ formatDateTime(latest.timestamp) }}，BME690、BMI270、BMM350 数据已进入 Web 展示层，
                控制命令可按统一 JSON 格式下发给端侧执行。
              </p>
            </div>
            <div class="hero-panel__status">
              <StatusPill v-for="item in statusSummary" :key="item.label" :label="item.label" :state="item.state" />
            </div>
          </div>

          <div class="metric-grid">
            <MetricCard
              v-for="metric in metricCards"
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
            <EChartPanel title="近 6 小时环境趋势" :option="historyChartOption" :active="activeView === 'overview'" />
            <section class="panel">
              <div class="section-heading">
                <h2>AI 摘要</h2>
                <StatusPill
                  v-if="aiAnalysis"
                  :label="riskLabel(aiAnalysis.risk_level)"
                  :state="aiAnalysis.risk_level === 'low' ? 'good' : 'watch'"
                />
              </div>
              <p class="summary-text">{{ aiAnalysis?.summary }}</p>
              <ul class="suggestion-list">
                <li v-for="suggestion in aiAnalysis?.suggestions" :key="suggestion">{{ suggestion }}</li>
              </ul>
            </section>
          </div>
        </section>

        <section v-show="activeView === 'realtime'" class="view-stack">
          <div class="section-heading">
            <h2>实时监测</h2>
            <span>5 秒自动刷新，模拟后续替换真实接口后的实时看板效果</span>
          </div>
          <div class="metric-grid">
            <MetricCard
              v-for="metric in metricCards"
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
            <EChartPanel title="BMI270 / BMM350 三轴数据" :option="motionChartOption" :active="activeView === 'realtime'" />
            <section class="panel sensor-table">
              <div class="section-heading">
                <h2>传感器原始值</h2>
              </div>
              <dl>
                <div><dt>acc_x / acc_y / acc_z</dt><dd>{{ latest.sensors.acc_x }} / {{ latest.sensors.acc_y }} / {{ latest.sensors.acc_z }}</dd></div>
                <div><dt>gyro_x / gyro_y / gyro_z</dt><dd>{{ latest.sensors.gyro_x }} / {{ latest.sensors.gyro_y }} / {{ latest.sensors.gyro_z }}</dd></div>
                <div><dt>mag_x / mag_y / mag_z</dt><dd>{{ latest.sensors.mag_x }} / {{ latest.sensors.mag_y }} / {{ latest.sensors.mag_z }}</dd></div>
                <div><dt>气体阻值</dt><dd>{{ latest.sensors.gas_resistance }} Ω</dd></div>
              </dl>
            </section>
          </div>
        </section>

        <section v-show="activeView === 'history'" class="view-stack">
          <EChartPanel title="历史曲线" :option="historyChartOption" :active="activeView === 'history'" />
          <section class="panel">
            <div class="section-heading">
              <h2>历史采样列表</h2>
            </div>
            <div class="data-table">
              <div class="data-table__head">
                <span>时间</span>
                <span>温度</span>
                <span>湿度</span>
                <span>气压</span>
                <span>气体阻值</span>
              </div>
              <div v-for="point in historyPoints.slice(-8).reverse()" :key="point.timestamp" class="data-table__row">
                <span>{{ formatDateTime(point.timestamp) }}</span>
                <span>{{ point.temperature }} 摄氏度</span>
                <span>{{ point.humidity }} %RH</span>
                <span>{{ point.pressure }} kPa</span>
                <span>{{ point.gas_resistance }} Ω</span>
              </div>
            </div>
          </section>
        </section>

        <section v-show="activeView === 'ai'" class="view-stack">
          <section class="panel ai-panel">
            <div class="section-heading">
              <h2>AI 农事建议</h2>
              <StatusPill
                v-if="aiAnalysis"
                :label="riskLabel(aiAnalysis.risk_level)"
                :state="aiAnalysis.risk_level === 'low' ? 'good' : 'watch'"
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
              <h2>AI 建议命令</h2>
              <span>格式与后端约定保持一致</span>
            </div>
            <pre class="json-preview">{{ JSON.stringify(aiAnalysis?.commands ?? [], null, 2) }}</pre>
          </section>
        </section>

        <section v-show="activeView === 'control'" class="view-stack">
          <section class="panel">
            <div class="section-heading">
              <h2>远程设备控制</h2>
              <span>按钮会生成统一命令 JSON 并更新端侧执行状态</span>
            </div>
            <div class="control-grid">
              <article class="control-card">
                <Fan :size="28" />
                <strong>风机</strong>
                <span>{{ latest.status.fan ? '运行中' : '待机' }}</span>
                <button
                  type="button"
                  class="toggle-switch"
                  :class="{ 'toggle-switch--on': latest.status.fan === 1 }"
                  :aria-pressed="latest.status.fan === 1"
                  @click="toggleDevice(latest.status.fan === 1, 'fan_on', 'fan_off', '棚内温度偏高，建议开启通风', '温度恢复正常，关闭风机')"
                >
                  <span>关闭</span>
                  <span>开启</span>
                  <i></i>
                </button>
              </article>
              <article class="control-card">
                <Droplets :size="28" />
                <strong>水泵</strong>
                <span>{{ latest.status.pump ? '运行中' : '待机' }}</span>
                <button
                  type="button"
                  class="toggle-switch"
                  :class="{ 'toggle-switch--on': latest.status.pump === 1 }"
                  :aria-pressed="latest.status.pump === 1"
                  @click="toggleDevice(latest.status.pump === 1, 'pump_on', 'pump_off', '湿度偏低，启动短时补水', '补水完成，关闭水泵')"
                >
                  <span>关闭</span>
                  <span>开启</span>
                  <i></i>
                </button>
              </article>
              <article class="control-card">
                <Lightbulb :size="28" />
                <strong>补光灯</strong>
                <span>{{ latest.status.light ? '已开启' : '已关闭' }}</span>
                <button
                  type="button"
                  class="toggle-switch"
                  :class="{ 'toggle-switch--on': latest.status.light === 1 }"
                  :aria-pressed="latest.status.light === 1"
                  @click="toggleDevice(latest.status.light === 1, 'light_on', 'light_off', '光照不足，开启补光灯', '自然光恢复，关闭补光')"
                >
                  <span>关闭</span>
                  <span>开启</span>
                  <i></i>
                </button>
              </article>
              <article class="control-card">
                <AlertTriangle :size="28" />
                <strong>报警器</strong>
                <span>{{ latest.status.alarm ? '报警中' : '关闭' }}</span>
                <button
                  type="button"
                  class="toggle-switch toggle-switch--danger"
                  :class="{ 'toggle-switch--on': latest.status.alarm === 1 }"
                  :aria-pressed="latest.status.alarm === 1"
                  @click="toggleDevice(latest.status.alarm === 1, 'alarm_on', 'alarm_off', '触发现场声光报警', '报警解除，关闭报警器')"
                >
                  <span>关闭</span>
                  <span>开启</span>
                  <i></i>
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
                <code>{{ result.command.command }}</code>
                <span>{{ result.command.reason }}</span>
                <time>{{ formatDateTime(result.executed_at) }}</time>
              </article>
              <p v-if="commandResults.length === 0" class="empty-text">暂无控制记录，点击上方按钮后会显示执行结果。</p>
            </div>
          </section>
        </section>

        <section v-show="activeView === 'alarms'" class="view-stack">
          <section class="panel">
            <div class="section-heading">
              <h2>报警记录</h2>
              <span>来自传感器阈值、通信链路和 AI 风险判断</span>
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
  </div>
</template>
