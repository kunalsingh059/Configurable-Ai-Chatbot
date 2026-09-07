<script setup>
import { ref, watch } from "vue";
import ChatHeader from "./components/ChatHeader.vue";
import MessageList from "./components/MessageList.vue";
import ChatInput from "./components/ChatInput.vue";
import WidgetLauncher from "./components/WidgetLauncher.vue";
import ConfirmDialog from "./components/ConfirmDialog.vue";
import { useChat } from "./composables/useChat";
import { useBusinessConfig } from "./composables/useBusinessConfig";

const { messages, isSending, error, sendMessage, hasApiKey, isResolved, resetChat } = useChat();
const { businessName } = useBusinessConfig();

// Starts closed (just the bubble) - matches how every embedded chat widget
// behaves on a real site. The parent page's loader script listens for this
// and resizes the iframe itself, since an iframe can't resize from inside.
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

// DEV CONVENIENCE ONLY: when opened directly (no parent iframe - e.g.
// pasting the URL straight into a browser tab), the widget has nothing
// constraining its size, so it naturally fills the whole tab. In real
// production use, embed.js on the CLIENT'S page creates and sizes the
// iframe - this component never controls its own size there. This flag
// just simulates that same corner-card box locally, so you can preview
// the real look without needing a separate test HTML page every time.
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
      :class="isStandalone ? 'h-[600px] w-[380px] rounded-2xl shadow-2xl' : 'h-full w-full'"
    >
      <ChatHeader :name="businessName" @minimize="isOpen = false" @clear="showClearConfirm = true" />

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