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
          :class="copied ? '!text-slate-800 !bg-light-50' : ''"
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
            class="h-4 w-4 text-slate-800"
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
              rating
                ? 'bg-slate-200 text-slate-800'
                : isFeedbackMenuOpen
                ? 'bg-slate-200/80 text-slate-700'
                : 'text-slate-400 hover:bg-slate-200/60 hover:text-slate-700'
            ]"
            :title="rating ? 'Click to change or remove feedback' : 'Provide feedback'"
            aria-label="Feedback"
            @click="toggleFeedbackMenu"
          >
            <!-- Active Liked Icon (Solid filled thumb up) -->
            <svg
              v-if="rating === 'up'"
              class="h-3.5 w-3.5"
              viewBox="0 0 24 24"
              fill="currentColor"
            >
              <path d="M13 3a3 3 0 0 1 2.995 2.824l.005 .176v4h2a3 3 0 0 1 2.98 2.65l.015 .174l.005 .176l-.02 .196l-1.006 5.032c-.381 1.626 -1.502 2.796 -2.81 2.78l-.164 -.008h-8a1 1 0 0 1 -.993 -.883l-.007 -.117l.001 -9.536a1 1 0 0 1 .5 -.865a2.998 2.998 0 0 0 1.492 -2.397l.007 -.202v-1a3 3 0 0 1 3 -3z" />
              <path d="M5 10a1 1 0 0 1 .993 .883l.007 .117v9a1 1 0 0 1 -.883 .993l-.117 .007h-1a2 2 0 0 1 -1.995 -1.85l-.005 -.15v-7a2 2 0 0 1 1.85 -1.995l.15 -.005h1z" />
            </svg>

            <!-- Active Disliked Icon (Solid filled thumb down) -->
            <svg
              v-else-if="rating === 'down'"
              class="h-3.5 w-3.5"
              viewBox="0 0 24 24"
              fill="currentColor"
            >
              <path d="M13 21.008a3 3 0 0 0 2.995 -2.823l.005 -.177v-4h2a3 3 0 0 0 2.98 -2.65l.015 -.173l.005 -.177l-.02 -.196l-1.006 -5.032c-.381 -1.625 -1.502 -2.796 -2.81 -2.78l-.164 .008h-8a1 1 0 0 0 -.993 .884l-.007 .116l.001 9.536a1 1 0 0 0 .5 .866a2.998 2.998 0 0 1 1.492 2.396l.007 .202v1a3 3 0 0 0 3 3z" />
              <path d="M5 14.008a1 1 0 0 0 .993 -.883l.007 -.117v-9a1 1 0 0 0 -.883 -.993l-.117 -.007h-1a2 2 0 0 0 -1.995 1.852l-.005 .15v7a2 2 0 0 0 1.85 1.994l.15 .005h1z" />
            </svg>

            <!-- Neutral Dual-Thumb Icon (Crisp side-by-side up & down) -->
            <svg
              v-else
              class="h-4 w-4"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="1.9"
              stroke-linecap="round"
              stroke-linejoin="round"
            >
              <g transform="translate(0.5, 0.5) scale(0.6)">
                <path d="M7 11v8a1 1 0 0 1 -1 1h-2a1 1 0 0 1 -1 -1v-7a1 1 0 0 1 1 -1h3a4 4 0 0 0 4 -4v-1a2 2 0 0 1 4 0v5h3a2 2 0 0 1 2 2l-1 5a2 3 0 0 1 -2 2h-7a3 3 0 0 1 -3 -3" />
              </g>
              <g transform="translate(23.5, 23.5) rotate(180) scale(0.6)">
                <path d="M7 11v8a1 1 0 0 1 -1 1h-2a1 1 0 0 1 -1 -1v-7a1 1 0 0 1 1 -1h3a4 4 0 0 0 4 -4v-1a2 2 0 0 1 4 0v5h3a2 2 0 0 1 2 2l-1 5a2 3 0 0 1 -2 2h-7a3 3 0 0 1 -3 -3" />
              </g>
            </svg>
          </button>

          <!-- ChatGPT Popover Menu -->
          <div
            v-if="isFeedbackMenuOpen"
            class="absolute bottom-full mb-1.5 left-0 z-40 min-w-[150px] rounded-2xl bg-[#212121] p-1.5 text-white shadow-2xl ring-1 ring-white/10 backdrop-blur-xs animate-in fade-in zoom-in-95"
          >
            <button
              type="button"
              class="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-[13px] font-normal text-slate-200 transition hover:bg-white/10 hover:text-white active:scale-98"
              :class="rating === 'up' ? '!font-medium !text-white bg-white/10' : ''"
              @click="selectRating('up')"
            >
              <svg
                class="h-4 w-4 shrink-0"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="1.8"
                stroke-linecap="round"
                stroke-linejoin="round"
              >
                <path d="M7 11v8a1 1 0 0 1 -1 1h-2a1 1 0 0 1 -1 -1v-7a1 1 0 0 1 1 -1h3a4 4 0 0 0 4 -4v-1a2 2 0 0 1 4 0v5h3a2 2 0 0 1 2 2l-1 5a2 3 0 0 1 -2 2h-7a3 3 0 0 1 -3 -3" />
              </svg>
              <span>Good response</span>
            </button>

            <button
              type="button"
              class="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-[13px] font-normal text-slate-200 transition hover:bg-white/10 hover:text-white active:scale-98"
              :class="rating === 'down' ? '!font-medium !text-white bg-white/10' : ''"
              @click="selectRating('down')"
            >
              <svg
                class="h-4 w-4 shrink-0"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="1.8"
                stroke-linecap="round"
                stroke-linejoin="round"
              >
                <path d="M7 13v-8a1 1 0 0 0 -1 -1h-2a1 1 0 0 0 -1 1v7a1 1 0 0 0 1 1h3a4 4 0 0 1 4 4v1a2 2 0 0 0 4 0v-5h3a2 2 0 0 0 2 -2l-1 -5a2 3 0 0 0 -2 -2h-7a3 3 0 0 0 -3 3" />
              </svg>
              <span>Bad response</span>
            </button>
          </div>
        </div>

        <!-- Feedback Confirmation Toast -->
        <span
          v-if="copied"
          class="ml-1 text-[11px] font-medium text-slate-500 animate-in fade-in"
        >
          Copied
        </span>
        <span
          v-else-if="feedbackToast"
          class="ml-1 text-[11px] font-medium text-slate-500 animate-in fade-in"
        >
          {{ feedbackToast }}
        </span>
      </div>
    </div>
  </div>
</template>