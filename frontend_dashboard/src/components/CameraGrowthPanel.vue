<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { Camera, Expand, Minimize2, Power, RefreshCw, ShieldAlert, Sparkles, X } from '@lucide/vue';
import StatusPill from './StatusPill.vue';
import { analyzeGrowthFrame } from '../services/api';
import type { DiseaseDetectionResult, RetrievalStatus } from '../types';
import { confidenceText, formatDateTime, userErrorText } from '../utils/format';

type CameraMode = 'live' | 'analysis';
type GrowthSeverity = 'healthy' | 'low' | 'medium' | 'high';

const props = withDefaults(defineProps<{
  active?: boolean;
}>(), {
  active: true,
});

const emit = defineEmits<{
  (event: 'analysis-updated', result: DiseaseDetectionResult | null): void;
}>();

const captureIntervalMs = 120000;
const autoAnalysisStorageKey = 'smartagribrain-camera-auto-analysis';

const videoRef = ref<HTMLVideoElement | null>(null);
const canvasRef = ref<HTMLCanvasElement | null>(null);
const stream = ref<MediaStream | null>(null);
const cameraReady = ref(false);
const cameraError = ref('');
const analyzing = ref(false);
const analysisError = ref('');
const growthAnalysis = ref<DiseaseDetectionResult | null>(null);
const lastCaptureAt = ref<number | null>(null);
const lastCaptureImageUrl = ref('');
const cameraMode = ref<CameraMode>('live');
const fullscreenOpen = ref(false);
const analysisOpen = ref(false);
const autoAnalysisEnabled = ref(readStoredAutoAnalysisEnabled());
let captureTimer: number | undefined;
let analysisCompletedAt: number | null = null;

const analysisDetections = computed(() => (
  growthAnalysis.value?.detections.filter((item) => item.bbox.width > 0 && item.bbox.height > 0) ?? []
));

const analysisStatusText = computed(() => {
  if (analyzing.value) {
    return 'AI 正在分析最新截图';
  }
  if (growthAnalysis.value) {
    return '已完成生长状态分析';
  }
  if (lastCaptureImageUrl.value) {
    return '等待 AI 分析结果';
  }
  if (!autoAnalysisEnabled.value && cameraReady.value) {
    return '自动状态分析已关闭';
  }
  if (cameraReady.value) {
    return '等待自动截图分析';
  }
  return '等待摄像头画面';
});

const analysisTimeText = computed(() => (
  lastCaptureAt.value ? formatDateTime(lastCaptureAt.value) : '尚未分析'
));

const strongestSeverity = computed<GrowthSeverity>(() => {
  if (analysisDetections.value.some((item) => item.severity === 'high')) {
    return 'high';
  }
  if (analysisDetections.value.some((item) => item.severity === 'medium')) {
    return 'medium';
  }
  if (analysisDetections.value.some((item) => item.severity === 'low')) {
    return 'low';
  }
  return 'healthy';
});

const growthStatusLabel = computed(() => {
  if (!growthAnalysis.value) {
    return lastCaptureImageUrl.value ? '等待 AI 分析' : '等待首次截图分析';
  }
  if (strongestSeverity.value === 'high') {
    return '高风险';
  }
  if (strongestSeverity.value === 'medium') {
    return '中等风险';
  }
  if (strongestSeverity.value === 'low') {
    return '轻度风险';
  }
  return '生长稳定';
});

const autoAnalysisHint = computed(() => (
  autoAnalysisEnabled.value
    ? '仅在总览页可见时每 2 分钟自动检查一次；离开页面后会暂停。'
    : '自动状态分析已关闭；需要时可点击刷新按钮手动分析。'
));

function detectionSeverityClass(severity: GrowthSeverity): string {
  return `analysis-detect-box--${severity}`;
}

function retrievalStatusLabel(status?: RetrievalStatus): string {
  if (status === 'success') return '已查询 EPPO';
  if (status === 'partial') return 'EPPO 部分可用';
  if (status === 'unavailable') return 'EPPO 资料暂不可用';
  return '未使用在线资料';
}

function retrievalStatusState(status?: RetrievalStatus): 'good' | 'watch' | 'neutral' {
  if (status === 'success') return 'good';
  if (status === 'partial') return 'watch';
  return 'neutral';
}

function readStoredAutoAnalysisEnabled(): boolean {
  if (typeof window === 'undefined') {
    return true;
  }
  const stored = window.localStorage.getItem(autoAnalysisStorageKey);
  return stored === null ? true : stored === 'true';
}

function saveAutoAnalysisEnabled(enabled: boolean): void {
  if (typeof window === 'undefined') {
    return;
  }
  window.localStorage.setItem(autoAnalysisStorageKey, String(enabled));
}

function clearCaptureTimer(): void {
  if (captureTimer) {
    window.clearInterval(captureTimer);
    captureTimer = undefined;
  }
}

function scheduleNextCapture(): void {
  clearCaptureTimer();
  if (!props.active || !autoAnalysisEnabled.value || !cameraReady.value || analyzing.value) {
    return;
  }

  const elapsed = analysisCompletedAt === null
    ? captureIntervalMs
    : Date.now() - analysisCompletedAt;
  const delay = Math.max(0, captureIntervalMs - elapsed);
  if (delay === 0) {
    void captureAndAnalyze();
    return;
  }

  captureTimer = window.setTimeout(() => {
    captureTimer = undefined;
    void captureAndAnalyze();
  }, delay);
}

function setAutoAnalysisEnabled(enabled: boolean): void {
  autoAnalysisEnabled.value = enabled;
  saveAutoAnalysisEnabled(enabled);
  if (!enabled) {
    clearCaptureTimer();
    return;
  }
  scheduleNextCapture();
}

function toggleAutoAnalysis(): void {
  setAutoAnalysisEnabled(!autoAnalysisEnabled.value);
}

function revokeLastCaptureUrl(): void {
  if (lastCaptureImageUrl.value) {
    URL.revokeObjectURL(lastCaptureImageUrl.value);
    lastCaptureImageUrl.value = '';
  }
}

function stopCamera(): void {
  clearCaptureTimer();
  stream.value?.getTracks().forEach((track) => track.stop());
  stream.value = null;
  cameraReady.value = false;
}

function cameraErrorText(error: unknown): string {
  if (error instanceof DOMException) {
    if (error.name === 'NotAllowedError') {
      return '浏览器没有获得摄像头权限，请允许后刷新页面。';
    }
    if (error.name === 'NotFoundError') {
      return '没有找到可用摄像头，请检查本地摄像头连接。';
    }
  }
  console.warn('Camera unavailable.', error);
  return '摄像头暂时不可用。';
}

async function attachStream(nextStream: MediaStream): Promise<void> {
  await nextTick();
  const video = videoRef.value;
  if (!video) {
    return;
  }
  video.srcObject = nextStream;
  await video.play();
  cameraReady.value = true;
}

async function startCamera(): Promise<void> {
  if (!navigator.mediaDevices?.getUserMedia) {
    cameraError.value = '当前浏览器不支持本地摄像头访问。';
    return;
  }

  stopCamera();
  cameraError.value = '';
  analysisError.value = '';
  try {
    const nextStream = await navigator.mediaDevices.getUserMedia({
      video: {
        width: { ideal: 1280 },
        height: { ideal: 720 },
        facingMode: 'environment',
      },
      audio: false,
    });
    if (!props.active) {
      nextStream.getTracks().forEach((track) => track.stop());
      return;
    }
    stream.value = nextStream;
    await attachStream(nextStream);
    scheduleNextCapture();
  } catch (error) {
    stopCamera();
    cameraError.value = cameraErrorText(error);
  }
}

function buildCaptureFile(canvas: HTMLCanvasElement): Promise<File | null> {
  return new Promise((resolve) => {
    canvas.toBlob((blob) => {
      if (!blob) {
        resolve(null);
        return;
      }
      resolve(new File([blob], `growth-frame-${Date.now()}.jpg`, { type: 'image/jpeg' }));
    }, 'image/jpeg', 0.88);
  });
}

async function captureAndAnalyze(): Promise<void> {
  const video = videoRef.value;
  const canvas = canvasRef.value;
  if (!video || !canvas || !cameraReady.value || analyzing.value) {
    return;
  }

  clearCaptureTimer();

  const width = video.videoWidth;
  const height = video.videoHeight;
  if (width <= 0 || height <= 0) {
    return;
  }

  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext('2d');
  if (!context) {
    analysisError.value = '无法读取摄像头画面。';
    return;
  }
  context.drawImage(video, 0, 0, width, height);
  const file = await buildCaptureFile(canvas);
  if (!file) {
    analysisError.value = '截图生成失败，请稍后重试。';
    return;
  }

  revokeLastCaptureUrl();
  const captureUrl = URL.createObjectURL(file);
  lastCaptureImageUrl.value = captureUrl;
  lastCaptureAt.value = Date.now();
  growthAnalysis.value = null;
  emit('analysis-updated', null);
  analyzing.value = true;
  analysisError.value = '';
  try {
    growthAnalysis.value = {
      ...await analyzeGrowthFrame(file, captureUrl),
      image_url: captureUrl,
    };
    emit('analysis-updated', growthAnalysis.value);
  } catch (error) {
    console.warn('Growth image analysis failed.', error);
    analysisError.value = userErrorText(error, '生长状态分析没有完成，请稍后重试。');
  } finally {
    if (!growthAnalysis.value) {
      emit('analysis-updated', null);
    }
    analyzing.value = false;
    analysisCompletedAt = Date.now();
    scheduleNextCapture();
  }
}

async function captureAndAnalyzeFromRefresh(): Promise<void> {
  if (!autoAnalysisEnabled.value) {
    return;
  }
  await captureAndAnalyze();
}

defineExpose({
  captureAndAnalyze: captureAndAnalyzeFromRefresh,
});

function openFullscreen(): void {
  if (!cameraReady.value && !lastCaptureImageUrl.value) {
    return;
  }
  analysisOpen.value = false;
  cameraMode.value = 'live';
  fullscreenOpen.value = true;
}

function closeFullscreen(): void {
  fullscreenOpen.value = false;
  analysisOpen.value = false;
}

function handleKeydown(event: KeyboardEvent): void {
  if (event.key === 'Escape') {
    closeFullscreen();
  }
}

onMounted(() => {
  if (props.active) {
    void startCamera();
  }
  window.addEventListener('keydown', handleKeydown);
});

watch(() => props.active, (active) => {
  if (active) {
    void startCamera();
    return;
  }
  closeFullscreen();
  stopCamera();
});

onBeforeUnmount(() => {
  stopCamera();
  revokeLastCaptureUrl();
  window.removeEventListener('keydown', handleKeydown);
});
</script>

<template>
  <section class="camera-growth-panel" :class="{ 'camera-growth-panel--fullscreen': fullscreenOpen }">
    <div class="camera-growth-panel__header">
      <div>
        <span>本地摄像头</span>
        <h2>{{ cameraMode === 'live' ? '作物生长画面' : '状态分析画面' }}</h2>
      </div>
      <div class="camera-growth-panel__actions">
        <div class="camera-mode-switch" aria-label="摄像头显示模式">
          <button type="button" :class="{ selected: cameraMode === 'live' }" @click.stop="cameraMode = 'live'">
            实时画面
          </button>
          <button type="button" :class="{ selected: cameraMode === 'analysis' }" @click.stop="cameraMode = 'analysis'">
            状态分析
          </button>
        </div>
        <button
          class="camera-auto-toggle"
          :class="{ 'camera-auto-toggle--on': autoAnalysisEnabled }"
          type="button"
          :title="autoAnalysisEnabled ? '关闭自动状态分析' : '开启自动状态分析'"
          @click.stop="toggleAutoAnalysis"
        >
          <Power :size="16" />
          <span>{{ autoAnalysisEnabled ? '自动分析开' : '自动分析关' }}</span>
        </button>
        <button class="icon-button" type="button" title="截图并分析" :disabled="!cameraReady || analyzing" @click.stop="captureAndAnalyze">
          <RefreshCw :class="{ spinning: analyzing }" :size="18" />
        </button>
        <button
          v-if="fullscreenOpen"
          class="text-button camera-growth-panel__detail-button"
          type="button"
          @click.stop="analysisOpen = !analysisOpen"
        >
          <Sparkles :size="16" />
          {{ analysisOpen ? '收起详情' : '生长详情' }}
        </button>
        <button
          class="icon-button"
          type="button"
          :title="fullscreenOpen ? '退出宽屏' : '宽屏查看'"
          :disabled="!cameraReady && !lastCaptureImageUrl"
          @click.stop="fullscreenOpen ? closeFullscreen() : openFullscreen()"
        >
          <Minimize2 v-if="fullscreenOpen" :size="18" />
          <Expand v-else :size="18" />
        </button>
        <button v-if="fullscreenOpen" class="icon-button" type="button" title="关闭宽屏" @click.stop="closeFullscreen">
          <X :size="18" />
        </button>
      </div>
    </div>

    <div
      class="camera-stage"
      :class="{ 'camera-stage--analysis': cameraMode === 'analysis' }"
      role="button"
      tabindex="0"
      :aria-disabled="!cameraReady && !lastCaptureImageUrl"
      @click="openFullscreen"
      @keydown.enter.prevent="openFullscreen"
      @keydown.space.prevent="openFullscreen"
    >
      <video v-show="cameraMode === 'live'" ref="videoRef" autoplay muted playsinline></video>

      <template v-if="cameraMode === 'live' && !cameraReady">
        <div class="camera-stage__placeholder">
          <ShieldAlert v-if="cameraError" :size="36" />
          <Camera v-else :size="36" />
          <strong>{{ cameraError || '正在连接本地摄像头...' }}</strong>
          <button v-if="cameraError" class="text-button" type="button" @click.stop="startCamera">重新连接</button>
        </div>
      </template>

      <template v-if="cameraMode === 'analysis'">
        <img v-if="lastCaptureImageUrl" class="camera-analysis-frame" :src="lastCaptureImageUrl" alt="最近一次生长状态分析截图" />
        <div v-else class="camera-stage__placeholder">
          <Sparkles :size="36" />
          <strong>等待首次截图分析</strong>
          <span>点击刷新按钮会立即截取当前画面并生成状态分析。</span>
        </div>

        <template v-if="lastCaptureImageUrl">
          <div class="growth-status-badge" :class="`growth-status-badge--${strongestSeverity}`">
            {{ growthStatusLabel }}
          </div>
          <div
            v-for="box in analysisDetections"
            :key="box.id"
            class="analysis-detect-box"
            :class="detectionSeverityClass(box.severity)"
            :style="{ left: `${box.bbox.x}%`, top: `${box.bbox.y}%`, width: `${box.bbox.width}%`, height: `${box.bbox.height}%` }"
          >
            <span>{{ box.label }} · {{ confidenceText(box.confidence) }}</span>
          </div>
        </template>
      </template>
    </div>

    <canvas ref="canvasRef" class="camera-growth-panel__canvas" aria-hidden="true"></canvas>

    <div
      v-show="!fullscreenOpen || analysisOpen"
      class="growth-analysis-box"
      :class="{ 'growth-analysis-box--overlay': fullscreenOpen && analysisOpen }"
    >
      <div class="growth-analysis-box__status">
        <span><Sparkles :size="16" /> {{ analysisStatusText }}</span>
        <time>更新 {{ analysisTimeText }}</time>
      </div>
      <p v-if="analysisError" class="form-error">{{ analysisError }}</p>
      <template v-if="growthAnalysis">
        <StatusPill
          v-if="growthAnalysis.retrievalStatus"
          :label="retrievalStatusLabel(growthAnalysis.retrievalStatus)"
          :state="retrievalStatusState(growthAnalysis.retrievalStatus)"
        />
        <strong>{{ growthAnalysis.summary }}</strong>
        <p>{{ growthAnalysis.explanation }}</p>
        <ul>
          <li v-for="suggestion in growthAnalysis.suggestions" :key="suggestion">{{ suggestion }}</li>
        </ul>
        <div v-if="growthAnalysis.references?.length" class="reference-list">
          <strong>EPPO 参考资料</strong>
          <a
            v-for="reference in growthAnalysis.references"
            :key="reference.referenceId || reference.title"
            :href="reference.url || undefined"
            target="_blank"
            rel="noopener noreferrer"
          >{{ reference.title }}</a>
        </div>
      </template>
      <p v-else-if="!analysisError" class="summary-text">{{ autoAnalysisHint }}</p>
    </div>
  </section>
</template>
