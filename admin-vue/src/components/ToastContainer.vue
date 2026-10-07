<script setup>
import { useToast } from "../composables/useToast";

const { toasts, dismiss } = useToast();
</script>

<template>
  <div class="pointer-events-none fixed inset-x-0 top-3 sm:top-4 z-50 flex flex-col items-center gap-2 px-3 sm:px-4">
    <transition-group name="toast">
      <div
        v-for="toast in toasts"
        :key="toast.id"
        class="pointer-events-auto flex w-full max-w-sm items-center gap-2 rounded-xl px-3.5 py-2.5 sm:px-4 sm:py-3 text-xs sm:text-sm font-medium shadow-lg ring-1"
        :class="{
          'bg-emerald-50 text-emerald-700 ring-emerald-100': toast.type === 'success',
          'bg-rose-50 text-rose-700 ring-rose-100': toast.type === 'error',
          'bg-white text-navy-900 ring-slate-100': toast.type === 'info',
        }"
      >
        <span class="min-w-0 flex-1 break-words">{{ toast.message }}</span>
        <button class="shrink-0 p-1 text-xs opacity-60 hover:opacity-100 transition" @click="dismiss(toast.id)">
          ✕
        </button>
      </div>
    </transition-group>
  </div>
</template>

<style scoped>
.toast-enter-active,
.toast-leave-active {
  transition: all 0.2s ease;
}
.toast-enter-from {
  opacity: 0;
  transform: translateY(-8px);
}
.toast-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}
</style>
