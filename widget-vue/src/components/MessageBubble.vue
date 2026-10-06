<script setup>
import { computed, ref } from "vue";
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

const copied = ref(false);
const showFeedbackThanks = ref(false);

const renderedHtml = computed(() => {
  if (props.role !== "assistant") return null;
  const raw = marked.parse(props.content, { breaks: true });
  return DOMPurify.sanitize(raw, {
    ALLOWED_TAGS: ["p", "strong", "em", "ul", "ol", "li", "a", "code", "pre", "br", "h1", "h2", "h3", "blockquote"],
    ALLOWED_ATTR: ["href", "target", "rel"],
  });
});

async function copyText() {
  try {
    if (navigator?.clipboard?.writeText) {
      await navigator.clipboard.writeText(props.content);
    } else {
      const textarea = document.createElement("textarea");
      textarea.value = props.content;
      textarea.style.position = "fixed";
      textarea.style.opacity = "0";
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand("copy");
      document.body.removeChild(textarea);
    }
    copied.value = true;
    setTimeout(() => {
      copied.value = false;
    }, 2000);
  } catch {
    // Ignore clipboard error
  }
}

function handleRate(newRating) {
  emit("rate", newRating);
  showFeedbackThanks.value = true;
  setTimeout(() => {
    showFeedbackThanks.value = false;
  }, 2200);
}
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

      <!-- Action bar (Copy + Thumbs Up / Down) for assistant replies -->
      <div
        v-if="role === 'assistant' && !isStreaming && content"
        class="mt-1.5 flex flex-wrap items-center gap-1.5 select-none pl-0.5"
      >
        <div class="inline-flex items-center gap-0.5 rounded-lg border border-slate-200/90 bg-white px-1 py-0.5 shadow-2xs">
          <!-- Copy Button -->
          <button
            type="button"
            class="inline-flex items-center gap-1 rounded-md px-1.5 py-1 text-[11px] font-medium text-slate-500 transition hover:bg-slate-100 hover:text-navy-950 active:scale-95"
            :title="copied ? 'Copied to clipboard' : 'Copy response'"
            :aria-label="copied ? 'Copied' : 'Copy response'"
            @click="copyText"
          >
            <svg v-if="!copied" class="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <rect width="14" height="14" x="8" y="8" rx="2" ry="2"/>
              <path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/>
            </svg>
            <svg v-else class="h-3.5 w-3.5 text-emerald-600" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
              <path d="M20 6 9 17l-5-5"/>
            </svg>
            <span>{{ copied ? "Copied" : "Copy" }}</span>
          </button>

          <span class="h-3 w-px bg-slate-200" />

          <!-- Thumbs Up -->
          <button
            type="button"
            class="rounded-md p-1 transition hover:bg-slate-100 active:scale-90"
            :class="rating === 'up' ? '!bg-emerald-50 text-emerald-600 ring-1 ring-emerald-200' : 'text-slate-400 hover:text-slate-700'"
            :title="rating === 'up' ? 'Helpful' : 'Mark as helpful'"
            aria-label="Thumbs up"
            @click="handleRate('up')"
          >
            <svg
              class="h-3.5 w-3.5 transition-transform"
              :class="rating === 'up' ? 'scale-105' : ''"
              viewBox="0 0 24 24"
              :fill="rating === 'up' ? 'currentColor' : 'none'"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
              stroke-linejoin="round"
            >
              <path d="M7 10v12" />
              <path d="M15 5.88 14 10h5.83a2 2 0 0 1 1.92 2.56l-2.33 8A2 2 0 0 1 17.5 22H4a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2h3" />
            </svg>
          </button>

          <!-- Thumbs Down -->
          <button
            type="button"
            class="rounded-md p-1 transition hover:bg-slate-100 active:scale-90"
            :class="rating === 'down' ? '!bg-rose-50 text-rose-600 ring-1 ring-rose-200' : 'text-slate-400 hover:text-slate-700'"
            :title="rating === 'down' ? 'Not helpful' : 'Mark as not helpful'"
            aria-label="Thumbs down"
            @click="handleRate('down')"
          >
            <svg
              class="h-3.5 w-3.5 transition-transform"
              :class="rating === 'down' ? 'scale-105' : ''"
              viewBox="0 0 24 24"
              :fill="rating === 'down' ? 'currentColor' : 'none'"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
              stroke-linejoin="round"
            >
              <path d="M17 14V2" />
              <path d="M9 18.12 10 14H4.17a2 2 0 0 1-1.92-2.56l2.33-8A2 2 0 0 1 6.5 2H20a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-3" />
            </svg>
          </button>
        </div>

        <!-- Feedback Confirmation -->
        <span
          v-if="showFeedbackThanks"
          class="inline-flex items-center rounded-md bg-emerald-50 px-2 py-0.5 text-[11px] font-medium text-emerald-700 ring-1 ring-emerald-200 transition-opacity"
        >
          Feedback recorded
        </span>
      </div>
    </div>
  </div>
</template>