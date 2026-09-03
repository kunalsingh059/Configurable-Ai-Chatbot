<script setup>
import { computed } from "vue";
import { marked } from "marked";
import DOMPurify from "dompurify";

const props = defineProps({
  role: { type: String, required: true }, // "user" | "assistant"
  content: { type: String, required: true },
});

// Groq/Claude often reply with markdown (lists, **bold**, etc - the system
// prompt asks for it). User messages stay plain text (no reason to parse
// markdown someone types, and it avoids interpreting their own input as
// HTML). marked converts to HTML, DOMPurify strips anything unsafe before
// it's rendered with v-html - tool results or model output could in theory
// contain injected HTML, so this isn't just for user input.
const renderedHtml = computed(() => {
  if (props.role !== "assistant") return null;
  const raw = marked.parse(props.content, { breaks: true });
  return DOMPurify.sanitize(raw, { ALLOWED_TAGS: ["p", "strong", "em", "ul", "ol", "li", "a", "code", "pre", "br", "h1", "h2", "h3", "blockquote"], ALLOWED_ATTR: ["href", "target", "rel"] });
});
</script>

<template>
  <div
    class="flex items-end gap-2"
    :class="role === 'user' ? 'flex-row-reverse' : 'flex-row'"
  >
    <div
      class="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-xs font-semibold"
      :class="
        role === 'user'
          ? 'bg-navy-950 text-white'
          : 'bg-amber-500 text-navy-950'
      "
    >
      {{ role === "user" ? "You" : "SA" }}
    </div>
    <div
      class="max-w-[75%] rounded-2xl px-4 py-2.5 text-[14px] leading-relaxed"
      :class="
        role === 'user'
          ? 'rounded-br-sm bg-navy-950 text-white'
          : 'rounded-bl-sm bg-white text-navy-900 shadow-sm ring-1 ring-black/5'
      "
    >
      <div v-if="role === 'assistant'" class="chat-markdown" v-html="renderedHtml" />
      <template v-else>{{ content }}</template>
    </div>
  </div>
</template>