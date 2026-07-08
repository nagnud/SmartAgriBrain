<script setup lang="ts">
defineProps<{
  label: string;
  state: 'good' | 'watch' | 'danger' | 'neutral';
}>();
</script>

<template>
  <span class="status-pill" :class="`status-pill--${state}`">
    <span class="status-dot"></span>
    {{ label }}
  </span>
</template>
