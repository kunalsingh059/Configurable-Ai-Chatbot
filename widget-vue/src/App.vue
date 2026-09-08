<script setup>
import { ref, computed, watch } from "vue";
import ChatHeader from "./components/ChatHeader.vue";
import MessageList from "./components/MessageList.vue";
import ChatInput from "./components/ChatInput.vue";
import WidgetLauncher from "./components/WidgetLauncher.vue";
import ConfirmDialog from "./components/ConfirmDialog.vue";
import { useChat } from "./composables/useChat";
import { useBusinessConfig } from "./composables/useBusinessConfig";

const { businessName } = useBusinessConfig();
const { messages, isSending, error, sendMessage, hasApiKey, isResolved, resetChat } = useChat(businessName);

const initials = computed(() => {
  const words = (businessName.value || "").trim().split(/\s+/).filter(Boolean);
  if (!words.length) return "AI";
  return words
    .slice(0, 2)
    .map((w) => w[0].toUpperCase())
    .join("");
});

const isOpen = ref(false);

function postResize(open) {
  window.parent.postMessage({ type: "chatbot-widget:resize", open }, "*");
}

watch(isOpen, (open) => postResize(open), { immediate: true });

const showClearConfirm = ref(false);

function confirmClear() {
  resetChat();
  showClearConfirm.value = false;
}

const isStandalone = window.parent === window;
</script>

<template>
    <div
      class="flex h-screen w-full items-end justify-end overflow-hidden"
      :class="isStandalone ? 'bg-slate-100 p-5' : 'bg-transparent'"
    >
      <WidgetLauncher v-if="!isOpen" @click="isOpen = true" />

      <div
        v-else
        class="relative flex flex-col overflow-hidden bg-white"
        :class="isStandalone ? 'h-[600px] max-h-[calc(100vh-2.5rem)] w-[380px] max-w-[calc(100vw-2.5rem)] rounded-2xl shadow-2xl' : 'h-full w-full'"
      >
      <ChatHeader
        :name="businessName"
        :initials="initials"
        @minimize="isOpen = false"
        @clear="showClearConfirm = true"
      />

      <div
        v-if="!isResolved"
        class="flex flex-1 items-center justify-center bg-slate-50 px-6 text-center text-[13px] text-slate-400"
      >
        Connecting...
      </div>
      <div
        v-else-if="!hasApiKey"
        class="flex flex-1 items-center justify-center bg-slate-50 px-6 text-center text-[13px] text-slate-500"
      >
        This widget isn't configured correctly.
      </div>
      <template v-else>
        <MessageList
          :messages="messages"
          :error="error"
          :is-sending="isSending"
          :initials="initials"
          @quick-action="sendMessage"
        />
        <ChatInput :disabled="isSending" @send="sendMessage" />
      </template>

      <ConfirmDialog
        :open="showClearConfirm"
        title="Clear this conversation?"
        message="This can't be undone."
        confirm-label="Clear chat"
        @confirm="confirmClear"
        @cancel="showClearConfirm = false"
      />
    </div>
  </div>
</template>