<script setup lang="ts">
import * as echarts from 'echarts';
import type { EChartsOption } from 'echarts';
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';

const props = defineProps<{
  title: string;
  option: EChartsOption;
  active?: boolean;
}>();

const chartEl = ref<HTMLDivElement | null>(null);
let chart: echarts.ECharts | null = null;
let resizeObserver: ResizeObserver | null = null;
let frameId = 0;

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
  chart.setOption(props.option, true);
}

function resizeChart(): void {
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
  if (frameId) {
    window.cancelAnimationFrame(frameId);
  }
  frameId = window.requestAnimationFrame(() => {
    frameId = window.requestAnimationFrame(() => {
      renderChart();
    });
  });
}

watch(
  () => props.option,
  () => scheduleRender(),
  { deep: true },
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
      scheduleRender();
    });
    resizeObserver.observe(chartEl.value);
  }
  window.addEventListener('resize', resizeChart);
});

onBeforeUnmount(() => {
  if (frameId) {
    window.cancelAnimationFrame(frameId);
  }
  resizeObserver?.disconnect();
  resizeObserver = null;
  window.removeEventListener('resize', resizeChart);
  chart?.dispose();
  chart = null;
});
</script>

<template>
  <section class="chart-panel">
    <div class="section-heading">
      <h2>{{ title }}</h2>
    </div>
    <div ref="chartEl" class="chart-panel__canvas"></div>
  </section>
</template>
