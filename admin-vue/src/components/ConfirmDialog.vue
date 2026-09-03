<script setup>
defineProps({
  open: { type: Boolean, default: false },
  title: { type: String, default: "Are you sure?" },
  message: { type: String, default: "" },
  confirmLabel: { type: String, default: "Confirm" },
  danger: { type: Boolean, default: false },
});
const emit = defineEmits(["confirm", "cancel"]);
</script>

<template>
  <div v-if="open" class="fixed inset-0 z-40 flex items-center justify-center bg-black/40 px-4">
    <div class="w-full max-w-sm rounded-2xl bg-white p-5 shadow-lg">
      <h3 class="text-sm font-semibold text-navy-950">{{ title }}</h3>
      <p v-if="message" class="mt-2 text-sm text-slate-600">{{ message }}</p>

      <div class="mt-5 flex justify-end gap-2">
        <button
          class="rounded-lg px-3 py-2 text-xs font-medium text-slate-600 hover:bg-slate-50"
          @click="emit('cancel')"
        >
          Cancel
        </button>
        <button
          class="rounded-lg px-3 py-2 text-xs font-medium text-white"
          :class="danger ? 'bg-rose-600 hover:bg-rose-700' : 'bg-navy-950 hover:bg-navy-900'"
          @click="emit('confirm')"
        >
          {{ confirmLabel }}
        </button>
      </div>
    </div>
  </div>
</template>
