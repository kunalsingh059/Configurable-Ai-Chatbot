<script setup>
import { ref, computed } from "vue";

const props = defineProps({
  disabled: { type: Boolean, default: false },
  maxLength: { type: Number, default: 1000 },
  poweredByText: { type: String, default: "Powered by Chatbot Platform" },
});
const emit = defineEmits(["send"]);

const text = ref("");

const showCounter = computed(() => text.value.length >= props.maxLength * 0.85);

function submit() {
  if (!text.value.trim() || props.disabled) return;
  emit("send", text.value);
  text.value = "";
}
</script>

<template>
  <div class="safe-bottom border-t border-slate-100 bg-white px-4 pt-3">
    <div
      class="flex items-center gap-2 rounded-2xl border border-amber-400/60 bg-white px-3 py-2 focus-within:border-amber-500"
    >
      <input
        v-model="text"
        type="text"
        :maxlength="maxLength"
        placeholder="Ask anything..."
        class="flex-1 border-none bg-transparent text-[14px] text-navy-900 outline-none placeholder:text-slate-400"
        @keydown.enter="submit"
      />
      <button
        :disabled="disabled || !text.trim()"
        class="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-navy-950 text-white transition disabled:cursor-not-allowed disabled:bg-slate-300"
        @click="submit"
        aria-label="Send message"
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
          <path
            d="M4 12L20 4L14 20L11 13L4 12Z"
            fill="currentColor"
          />
        </svg>
      </button>
    </div>
    <p class="mt-1.5 flex items-center justify-between px-1 text-[11px] text-slate-400">
      <span>{{ poweredByText }}</span>
      <span v-if="showCounter">{{ text.length }} / {{ maxLength }}</span>
    </p>
  </div>
</template>