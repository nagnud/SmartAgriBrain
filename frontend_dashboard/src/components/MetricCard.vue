<script setup lang="ts">
import type { Component } from 'vue';

defineProps<{
  title: string;
  value: string;
  unit: string;
  hint: string;
  state: 'good' | 'watch' | 'danger';
  icon: Component;
}>();
</script>

<template>
  <article class="metric-card" :class="`metric-card--${state}`">
    <div class="metric-card__top">
      <component :is="icon" :size="22" stroke-width="2" />
      <span>{{ title }}</span>
    </div>
    <div class="metric-card__value">
      <strong>{{ value }}</strong>
      <span>{{ unit }}</span>
    </div>
    <p>{{ hint }}</p>
  </article>
</template>
