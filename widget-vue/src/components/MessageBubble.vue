<script setup>
import { computed } from "vue";
import { marked } from "marked";
import DOMPurify from "dompurify";

const props = defineProps({
  role: { type: String, required: true }, // "user" | "assistant"
  content: { type: String, required: true },
  initials: { type: String, default: "AI" },
  messageId: { type: String, default: null },
  rating: { type: String, default: null }, // "up" | "down" | null
  isStreaming: { type: Boolean, default: false },
});

const emit = defineEmits(["rate"]);

const renderedHtml = computed(() => {
  if (props.role !== "assistant") return null;
  const raw = marked.parse(props.content, { breaks: true });
  return DOMPurify.sanitize(raw, {
    ALLOWED_TAGS: ["p", "strong", "em", "ul", "ol", "li", "a", "code", "pre", "br", "h1", "h2", "h3", "blockquote"],
    ALLOWED_ATTR: ["href", "target", "rel"],
  });
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
      {{ role === "user" ? "You" : initials }}
    </div>
    <div class="max-w-[78%] min-w-0">
      <div
        class="rounded-2xl px-4 py-2.5 text-[14px] leading-relaxed break-words"
        :class="
          role === 'user'
            ? 'rounded-br-sm bg-navy-950 text-white'
            : 'rounded-bl-sm bg-white text-navy-900 shadow-sm ring-1 ring-black/5'
        "
      >
        <div v-if="role === 'assistant'" class="chat-markdown" v-html="renderedHtml" />
        <template v-else>{{ content }}</template>
      </div>

      <!-- Feedback thumbs (assistant replies only, once finished) -->
      <div
        v-if="role === 'assistant' && !isStreaming && content"
        class="mt-1 flex items-center gap-1 pl-1"
      >
        <button
          type="button"
          class="rounded p-1 text-slate-400 transition hover:bg-slate-200/60 hover:text-slate-700"
          :class="rating === 'up' ? '!bg-emerald-50 !text-emerald-600 font-bold' : ''"
          :title="rating === 'up' ? 'Helpful' : 'Mark as helpful'"
          aria-label="Thumbs up"
          @click="emit('rate', 'up')"
        >
          <svg class="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M7 10v12" />
            <path d="M15 5.88 14 10h5.83a2 2 0 0 1 1.92 2.56l-2.33 8A2 2 0 0 1 17.5 22H4a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2h3" />
          </svg>
        </button>
        <button
          type="button"
          class="rounded p-1 text-slate-400 transition hover:bg-slate-200/60 hover:text-slate-700"
          :class="rating === 'down' ? '!bg-rose-50 !text-rose-600 font-bold' : ''"
          :title="rating === 'down' ? 'Not helpful' : 'Mark as not helpful'"
          aria-label="Thumbs down"
          @click="emit('rate', 'down')"
        >
          <svg class="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M17 14V2" />
            <path d="M9 18.12 10 14H4.17a2 2 0 0 1-1.92-2.56l2.33-8A2 2 0 0 1 6.5 2H20a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-3" />
          </svg>
        </button>
      </div>
    </div>
  </div>
</template>