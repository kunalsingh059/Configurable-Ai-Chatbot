<script setup>
import { nextTick, ref, watch } from "vue";
import MessageBubble from "./MessageBubble.vue";
import QuickActions from "./QuickActions.vue";

const props = defineProps({
  messages: { type: Array, required: true },
  error: { type: String, default: null },
  isSending: { type: Boolean, default: false },
});
const emit = defineEmits(["quick-action"]);

const scrollEl = ref(null);

watch(
  () => props.messages.length,
  async () => {
    await nextTick();
    if (scrollEl.value) {
      scrollEl.value.scrollTop = scrollEl.value.scrollHeight;
    }
  }
);
</script>

<template>
  <div ref="scrollEl" class="flex-1 space-y-4 overflow-y-auto bg-slate-50 px-5 py-5">
    <MessageBubble
      v-for="(m, i) in messages"
      :key="i"
      :role="m.role"
      :content="m.content"
    />

    <QuickActions v-if="messages.length === 1" @select="emit('quick-action', $event)" />

    <div
      v-if="isSending"
      class="flex items-center gap-2 text-xs text-navy-900/40"
    >
      <span class="h-1.5 w-1.5 animate-pulse rounded-full bg-navy-900/40" />
      <span class="h-1.5 w-1.5 animate-pulse rounded-full bg-navy-900/40 [animation-delay:150ms]" />
      <span class="h-1.5 w-1.5 animate-pulse rounded-full bg-navy-900/40 [animation-delay:300ms]" />
    </div>

    <div
      v-if="error"
      class="rounded-2xl bg-rose-50 px-4 py-3 text-[13px] leading-relaxed text-rose-600 ring-1 ring-rose-100"
    >
      Something went wrong.<br />
      {{ error }}
    </div>
  </div>
</template>