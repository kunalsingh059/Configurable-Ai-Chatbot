<script setup>
import { computed, nextTick, ref, watch } from "vue";
import MessageBubble from "./MessageBubble.vue";

const props = defineProps({
  messages: { type: Array, required: true },
  error: { type: String, default: null },
  isSending: { type: Boolean, default: false },
  statusText: { type: String, default: null },
  initials: { type: String, default: "AI" },
});
const emit = defineEmits(["quick-action", "rate"]);

const scrollEl = ref(null);

// The last message is the streaming assistant placeholder while a reply
// is in flight (see useChat.js) - show the typing indicator only until
// that placeholder actually has content, so the dots hand off smoothly to
// real text arriving token-by-token instead of popping in all at once
// after the dots.
const lastMessage = computed(() => props.messages[props.messages.length - 1]);
const showTypingIndicator = computed(
  () => props.isSending && (!lastMessage.value || lastMessage.value.role !== "assistant" || !lastMessage.value.content)
);

watch(
  () => [props.messages.length, props.isSending, lastMessage.value?.content],
  async () => {
    await nextTick();
    if (scrollEl.value) {
      scrollEl.value.scrollTop = scrollEl.value.scrollHeight;
    }
  }
);
</script>

<template>
  <div ref="scrollEl" class="chat-scroll flex-1 space-y-4 overflow-x-hidden overflow-y-auto bg-slate-50 px-5 py-5">
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

    <template v-for="(m, i) in messages" :key="m.message_id || i">
      <!-- The trailing empty assistant placeholder (content still
           streaming in, nothing arrived yet) renders as the typing
           indicator below instead of an empty bubble. -->
      <MessageBubble
        v-if="m.role === 'user' || m.content"
        :role="m.role"
        :content="m.content"
        :initials="initials"
        :message-id="m.message_id"
        :rating="m.rating"
        :is-streaming="isSending && i === messages.length - 1"
        @rate="(rating) => emit('rate', { messageId: m.message_id, rating })"
      />
    </template>

    <div v-if="showTypingIndicator" class="flex items-end gap-2">
      <div
        class="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-amber-500 text-xs font-semibold text-navy-950"
      >
        {{ initials }}
      </div>
      <div class="flex items-center gap-2 rounded-2xl rounded-bl-sm bg-white px-4 py-3 shadow-sm ring-1 ring-black/5">
        <span v-if="statusText" class="text-[13px] text-slate-500">{{ statusText }}</span>
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