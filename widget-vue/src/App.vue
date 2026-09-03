<script setup>
import { ref, watch } from "vue";
import ChatHeader from "./components/ChatHeader.vue";
import MessageList from "./components/MessageList.vue";
import ChatInput from "./components/ChatInput.vue";
import WidgetLauncher from "./components/WidgetLauncher.vue";
import { useChat } from "./composables/useChat";
import { useBusinessConfig } from "./composables/useBusinessConfig";

const { messages, isSending, error, sendMessage, hasApiKey, isResolved } = useChat();
const { businessName } = useBusinessConfig();

// Starts closed (just the bubble) - matches how every embedded chat widget
// behaves on a real site. The parent page's loader script listens for this
// and resizes the iframe itself, since an iframe can't resize from inside.
const isOpen = ref(false);

function postResize(open) {
  window.parent.postMessage({ type: "chatbot-widget:resize", open }, "*");
}

watch(isOpen, (open) => postResize(open), { immediate: true });
</script>

<template>
  <div class="flex h-screen w-full items-end justify-end overflow-hidden bg-transparent">
    <WidgetLauncher v-if="!isOpen" @click="isOpen = true" />

    <div
      v-else
      class="flex h-full w-full flex-col overflow-hidden bg-white"
    >
      <ChatHeader :name="businessName" @minimize="isOpen = false" />

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
    </div>
  </div>
</template>