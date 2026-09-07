<script setup>
defineProps({
  open: { type: Boolean, default: false },
  title: { type: String, default: "Are you sure?" },
  message: { type: String, default: "" },
  confirmLabel: { type: String, default: "Confirm" },
});
defineEmits(["confirm", "cancel"]);
</script>

<template>
  <Transition name="fade">
    <div
      v-if="open"
      class="absolute inset-0 z-20 flex items-center justify-center bg-navy-950/40 p-6"
    >
      <div class="w-full max-w-[260px] rounded-2xl bg-white p-4 shadow-xl">
        <h3 class="text-[13px] font-semibold text-navy-950">{{ title }}</h3>
        <p v-if="message" class="mt-1 text-xs leading-relaxed text-slate-500">
          {{ message }}
        </p>
        <div class="mt-4 flex justify-end gap-2">
          <button
            class="rounded-lg px-3 py-1.5 text-xs font-medium text-slate-600 transition hover:bg-slate-50"
            @click="$emit('cancel')"
          >
            Cancel
          </button>
          <button
            class="rounded-lg bg-rose-600 px-3 py-1.5 text-xs font-medium text-white transition hover:bg-rose-700"
            @click="$emit('confirm')"
          >
            {{ confirmLabel }}
          </button>
        </div>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.15s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>