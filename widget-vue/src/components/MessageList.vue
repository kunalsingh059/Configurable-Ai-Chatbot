<script setup>
import { nextTick, ref, watch } from "vue";
import MessageBubble from "./MessageBubble.vue";

const props = defineProps({
  messages: { type: Array, required: true },
  error: { type: String, default: null },
  isSending: { type: Boolean, default: false },
  initials: { type: String, default: "AI" },
});
const emit = defineEmits(["quick-action"]);

const scrollEl = ref(null);

watch(
  () => [props.messages.length, props.isSending],
  async () => {
    await nextTick();
    if (scrollEl.value) {
      scrollEl.value.scrollTop = scrollEl.value.scrollHeight;
    }
  }
);
</script>

<template>
  <div ref="scrollEl" class="chat-scroll flex-1 space-y-4 overflow-y-auto bg-slate-50 px-5 py-5">
    <div
      v-if="messages.length === 0"
      class="flex h-full flex-col items-center justify-center gap-3 text-center"
    >
      <p class="text-[13px] text-slate-400">Start the conversation whenever you're ready.</p>
      <button
        class="rounded-xl border border-slate-200 bg-white px-5 py-2.5 text-[13px] font-medium text-navy-900 transition hover:border-amber-500 hover:text-amber-600"
        @click="emit('quick-action', 'Hi')"
      >
        👋 Say hi
      </button>
    </div>

    <MessageBubble
      v-for="(m, i) in messages"
      :key="i"
      :role="m.role"
      :content="m.content"
      :initials="initials"
    />

    <div v-if="isSending" class="flex items-end gap-2">
      <div
        class="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-amber-500 text-xs font-semibold text-navy-950"
      >
        {{ initials }}
      </div>
      <div class="flex items-center gap-1 rounded-2xl rounded-bl-sm bg-white px-4 py-3 shadow-sm ring-1 ring-black/5">
        <span class="h-1.5 w-1.5 animate-pulse rounded-full bg-navy-900/40" />
        <span class="h-1.5 w-1.5 animate-pulse rounded-full bg-navy-900/40 [animation-delay:150ms]" />
        <span class="h-1.5 w-1.5 animate-pulse rounded-full bg-navy-900/40 [animation-delay:300ms]" />
      </div>
    </div>

    <div
      v-if="error"
      class="rounded-2xl bg-rose-50 px-4 py-3 text-[13px] leading-relaxed text-rose-600 ring-1 ring-rose-100"
    >
      {{ error }}
    </div>
  </div>
</template>