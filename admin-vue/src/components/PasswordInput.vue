<script setup>
import { ref } from "vue";

// defineModel (Vue 3.4+) - lets this be used exactly like a plain
// <input v-model="password" /> from the parent, no extra props/emits needed.
const model = defineModel({ type: String, default: "" });

defineProps({
  placeholder: { type: String, default: "" },
  required: { type: Boolean, default: false },
  autocomplete: { type: String, default: "current-password" },
  autofocus: { type: Boolean, default: false },
});

const visible = ref(false);
</script>

<template>
  <div class="relative">
    <input
      v-model="model"
      :type="visible ? 'text' : 'password'"
      :placeholder="placeholder"
      :required="required"
      :autocomplete="autocomplete"
      :autofocus="autofocus"
      class="w-full rounded-lg border border-slate-200 px-3 py-2 pr-10 text-base sm:text-sm outline-none transition focus:border-amber-500 focus:ring-2 focus:ring-amber-500/20"
    />
    <button
      type="button"
      tabindex="-1"
      class="absolute inset-y-0 right-0 flex w-9 items-center justify-center text-slate-400 hover:text-navy-900"
      :aria-label="visible ? 'Hide password' : 'Show password'"
      @click="visible = !visible"
    >
      <!-- Eye (visible) -->
      <svg v-if="visible" class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7Z" />
        <circle cx="12" cy="12" r="3" />
      </svg>
      <!-- Eye-off (hidden) -->
      <svg v-else class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M17.94 17.94A10.94 10.94 0 0 1 12 19c-6.5 0-10-7-10-7a18.6 18.6 0 0 1 4.22-5.19M9.9 4.24A9.12 9.12 0 0 1 12 4c6.5 0 10 7 10 7a18.5 18.5 0 0 1-2.16 3.19M14.12 14.12a3 3 0 1 1-4.24-4.24" />
        <path d="M1 1l22 22" />
      </svg>
    </button>
  </div>
</template>