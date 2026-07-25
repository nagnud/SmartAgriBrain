<script setup lang="ts">
import * as echarts from 'echarts';
import type { EChartsOption } from 'echarts';
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';

const props = defineProps<{
  title: string;
  option: EChartsOption;
  active?: boolean;
  minWidth?: number;
}>();

const chartEl = ref<HTMLDivElement | null>(null);
const chartStyle = computed(() => ({
  minWidth: props.minWidth ? `${props.minWidth}px` : undefined,
}));
let chart: echarts.ECharts | null = null;
let resizeObserver: ResizeObserver | null = null;
let renderFrameId = 0;
let resizeFrameId = 0;

function renderChart(): void {
  if (!chartEl.value) {
    return;
  }
  const width = chartEl.value.clientWidth;
  const height = chartEl.value.clientHeight;
  if (width <= 0 || height <= 0 || props.active === false) {
    return;
  }
  if (!chart) {
    chart = echarts.init(chartEl.value);
  }
  chart.resize({ width, height });
  chart.setOption(props.option, { notMerge: true, lazyUpdate: true });
}

function applyChartResize(): void {
  if (!chartEl.value || props.active === false) {
    return;
  }
  const width = chartEl.value.clientWidth;
  const height = chartEl.value.clientHeight;
  if (width <= 0 || height <= 0) {
    return;
  }
  chart?.resize({ width, height });
}

function scheduleRender(): void {
  if (renderFrameId) {
    window.cancelAnimationFrame(renderFrameId);
  }
  renderFrameId = window.requestAnimationFrame(() => {
    renderFrameId = window.requestAnimationFrame(() => {
      renderFrameId = 0;
      renderChart();
    });
  });
}

function scheduleResize(): void {
  if (resizeFrameId) {
    return;
  }
  resizeFrameId = window.requestAnimationFrame(() => {
    resizeFrameId = 0;
    applyChartResize();
  });
}

watch(
  () => props.option,
  () => scheduleRender(),
);

watch(
  () => props.minWidth,
  () => scheduleRender(),
);

watch(
  () => props.active,
  async () => {
    await nextTick();
    scheduleRender();
  },
);

onMounted(async () => {
  await nextTick();
  scheduleRender();
  if (chartEl.value) {
    resizeObserver = new ResizeObserver(() => {
      scheduleResize();
    });
    resizeObserver.observe(chartEl.value);
  }
  window.addEventListener('resize', scheduleResize);
});

onBeforeUnmount(() => {
  if (renderFrameId) {
    window.cancelAnimationFrame(renderFrameId);
  }
  if (resizeFrameId) {
    window.cancelAnimationFrame(resizeFrameId);
  }
  resizeObserver?.disconnect();
  resizeObserver = null;
  window.removeEventListener('resize', scheduleResize);
  chart?.dispose();
  chart = null;
});
</script>

<template>
  <section class="chart-panel">
    <div class="section-heading">
      <h2>{{ title }}</h2>
      <slot name="toolbar"></slot>
    </div>
    <div class="chart-panel__viewport">
      <div ref="chartEl" class="chart-panel__canvas" :style="chartStyle"></div>
    </div>
  </section>
</template>
