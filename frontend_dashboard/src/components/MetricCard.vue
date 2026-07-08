<script setup lang="ts">
import type { Component } from 'vue';

defineProps<{
  title: string;
  value: string;
  unit: string;
  hint: string;
  state: 'good' | 'watch' | 'danger' | 'low';
  icon: Component;
  statusLabel?: string;
  targetText?: string;
  active?: boolean;
  clickable?: boolean;
}>();

defineEmits<{
  click: [];
}>();
</script>

<template>
  <article
    class="metric-card"
    :class="[
      `metric-card--${state}`,
      { 'metric-card--clickable': clickable, 'metric-card--active': active },
    ]"
    @click="$emit('click')"
  >
    <div class="metric-card__top">
      <component :is="icon" :size="22" stroke-width="2" />
      <span>{{ title }}</span>
    </div>
    <div class="metric-card__value">
      <strong>{{ value }}</strong>
      <span>{{ unit }}</span>
    </div>
    <div v-if="statusLabel || targetText" class="metric-card__meta">
      <strong v-if="statusLabel">{{ statusLabel }}</strong>
      <span v-if="targetText">{{ targetText }}</span>
    </div>
    <p>{{ hint }}</p>
  </article>
</template>
