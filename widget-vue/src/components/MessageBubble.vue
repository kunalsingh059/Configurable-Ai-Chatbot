<script setup>
import { computed, onMounted, onUnmounted, ref } from "vue";
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
const feedbackToast = ref(null);
const isFeedbackMenuOpen = ref(false);
const feedbackContainerRef = ref(null);

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

function toggleFeedbackMenu() {
  isFeedbackMenuOpen.value = !isFeedbackMenuOpen.value;
}

function selectRating(target) {
  if (props.rating === target) {
    // User clicked the active rating again -> toggle back to nothing (remove feedback)
    emit("rate", null);
    feedbackToast.value = "Feedback removed";
  } else {
    emit("rate", target);
    feedbackToast.value = target === "up" ? "Marked as helpful" : "Marked as unhelpful";
  }
  isFeedbackMenuOpen.value = false;
  setTimeout(() => {
    feedbackToast.value = null;
  }, 2200);
}

function handleDocumentClick(e) {
  if (!isFeedbackMenuOpen.value) return;
  if (feedbackContainerRef.value && feedbackContainerRef.value.contains(e.target)) {
    return;
  }
  isFeedbackMenuOpen.value = false;
}

onMounted(() => {
  document.addEventListener("click", handleDocumentClick);
});

onUnmounted(() => {
  document.removeEventListener("click", handleDocumentClick);
});
</script>

<template>
  <div
    class="flex items-start gap-2.5"
    :class="role === 'user' ? 'flex-row-reverse' : 'flex-row'"
  >
    <!-- Avatar -->
    <div
      class="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl text-xs font-semibold shadow-xs select-none"
      :class="
        role === 'user'
          ? 'bg-navy-950 text-white'
          : 'bg-amber-500 text-navy-950'
      "
    >
      {{ role === "user" ? "You" : initials }}
    </div>

    <!-- Bubble + Actions Column -->
    <div class="max-w-[82%] min-w-0">
      <div
        class="rounded-2xl px-4 py-2.5 text-[14px] leading-relaxed break-words"
        :class="
          role === 'user'
            ? 'rounded-tr-xs bg-navy-950 text-white'
            : 'rounded-tl-xs bg-white text-navy-900 shadow-sm ring-1 ring-black/5'
        "
      >
        <div v-if="role === 'assistant'" class="chat-markdown" v-html="renderedHtml" />
        <template v-else>{{ content }}</template>
      </div>

      <!-- ChatGPT-style Action bar (Copy + Combined Like/Dislike Button) -->
      <div
        v-if="role === 'assistant' && !isStreaming && content"
        class="relative mt-1 flex items-center gap-1 select-none pl-1 text-slate-400"
      >
        <!-- Copy Button (Icon only) -->
        <button
          type="button"
          class="flex h-7 w-7 items-center justify-center rounded-lg text-slate-400 transition hover:bg-slate-200/60 hover:text-slate-700 active:scale-90"
          :class="copied ? '!text-emerald-600 !bg-emerald-50' : ''"
          :title="copied ? 'Copied to clipboard' : 'Copy response'"
          aria-label="Copy response"
          @click="copyText"
        >
          <svg
            v-if="!copied"
            class="h-4 w-4"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <rect width="13" height="13" x="9" y="9" rx="2.5" ry="2.5" />
            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
          </svg>
          <svg
            v-else
            class="h-4 w-4 text-emerald-600"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2.5"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <path d="M20 6 9 17l-5-5" />
          </svg>
        </button>

        <!-- ChatGPT Dual-Thumb Feedback Button with Popover Menu -->
        <div ref="feedbackContainerRef" class="relative">
          <button
            type="button"
            class="flex h-7 w-7 items-center justify-center rounded-lg transition active:scale-90"
            :class="[
              rating === 'up'
                ? '!text-emerald-600 !bg-emerald-50'
                : rating === 'down'
                ? '!text-rose-600 !bg-rose-50'
                : isFeedbackMenuOpen
                ? 'bg-slate-200/70 text-slate-700'
                : 'text-slate-400 hover:bg-slate-200/60 hover:text-slate-700'
            ]"
            :title="rating ? 'Click to change or remove feedback' : 'Provide feedback'"
            aria-label="Feedback"
            @click="toggleFeedbackMenu"
          >
            <!-- Active Thumbs Up Icon -->
            <svg
              v-if="rating === 'up'"
              class="h-4 w-4 text-emerald-600 scale-105"
              viewBox="0 0 24 24"
              fill="currentColor"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
              stroke-linejoin="round"
            >
              <path d="M7 10v12" />
              <path d="M15 5.88 14 10h5.83a2 2 0 0 1 1.92 2.56l-2.33 8A2 2 0 0 1 17.5 22H4a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2h3" />
            </svg>

            <!-- Active Thumbs Down Icon -->
            <svg
              v-else-if="rating === 'down'"
              class="h-4 w-4 text-rose-600 scale-105"
              viewBox="0 0 24 24"
              fill="currentColor"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
              stroke-linejoin="round"
            >
              <path d="M17 14V2" />
              <path d="M9 18.12 10 14H4.17a2 2 0 0 1-1.92-2.56l2.33-8A2 2 0 0 1 6.5 2H20a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-3" />
            </svg>

            <!-- Neutral ChatGPT Combined Dual-Thumb Icon -->
            <svg
              v-else
              class="h-4 w-4"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
              stroke-linejoin="round"
            >
              <g transform="translate(-1, -1) scale(0.68)">
                <path d="M7 10v12" />
                <path d="M15 5.88 14 10h5.83a2 2 0 0 1 1.92 2.56l-2.33 8A2 2 0 0 1 17.5 22H4a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2h3" />
              </g>
              <g transform="translate(8, 7.5) scale(0.68)">
                <path d="M17 14V2" />
                <path d="M9 18.12 10 14H4.17a2 2 0 0 1-1.92-2.56l2.33-8A2 2 0 0 1 6.5 2H20a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-3" />
              </g>
            </svg>
          </button>

          <!-- ChatGPT Popover Menu -->
          <div
            v-if="isFeedbackMenuOpen"
            class="absolute bottom-full mb-1.5 left-0 z-40 min-w-[145px] rounded-xl bg-slate-900/95 p-1 text-white shadow-xl ring-1 ring-white/10 backdrop-blur-xs animate-in fade-in zoom-in-95"
          >
            <button
              type="button"
              class="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-xs font-medium transition hover:bg-white/10 active:scale-95"
              :class="rating === 'up' ? '!text-emerald-400 bg-white/5' : 'text-slate-200'"
              @click="selectRating('up')"
            >
              <svg
                class="h-4 w-4 shrink-0"
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
              <span>Good response</span>
              <span v-if="rating === 'up'" class="ml-auto text-[10px] text-emerald-400">✓</span>
            </button>

            <button
              type="button"
              class="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-xs font-medium transition hover:bg-white/10 active:scale-95"
              :class="rating === 'down' ? '!text-rose-400 bg-white/5' : 'text-slate-200'"
              @click="selectRating('down')"
            >
              <svg
                class="h-4 w-4 shrink-0"
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
              <span>Bad response</span>
              <span v-if="rating === 'down'" class="ml-auto text-[10px] text-rose-400">✓</span>
            </button>
          </div>
        </div>

        <!-- Feedback Confirmation Toast -->
        <span
          v-if="copied"
          class="ml-1 text-[11px] font-medium text-emerald-600 animate-in fade-in"
        >
          Copied
        </span>
        <span
          v-else-if="feedbackToast"
          class="ml-1 text-[11px] font-medium animate-in fade-in"
          :class="feedbackToast === 'Feedback removed' ? 'text-slate-500' : 'text-emerald-600'"
        >
          {{ feedbackToast }}
        </span>
      </div>
    </div>
  </div>
</template>