<script setup lang="ts">
import { computed } from 'vue';
import DOMPurify from 'dompurify';
import { marked } from 'marked';

const props = defineProps<{
  content: string;
}>();

const renderedHtml = computed(() => {
  const html = marked.parse(props.content, {
    async: false,
    breaks: true,
    gfm: true,
  });

  return DOMPurify.sanitize(html, {
    USE_PROFILES: { html: true },
  });
});
</script>

<template>
  <div class="chat-markdown" v-html="renderedHtml"></div>
</template>
