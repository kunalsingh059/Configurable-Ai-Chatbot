<script setup>
defineProps({
  name: { type: String, default: "Support Assistant" },
});
defineEmits(["minimize"]);
</script>

<template>
  <div class="relative overflow-hidden bg-navy-950 px-5 py-4">
    <div
      class="pointer-events-none absolute -right-6 -top-10 h-32 w-32 rounded-full bg-navy-800/60"
    />
    <div class="relative flex items-center justify-between">
      <div class="flex items-center gap-3 min-w-0">
        <div
          class="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-amber-500 text-sm font-semibold text-navy-950"
        >
          SA
        </div>
        <div class="min-w-0">
          <div class="flex items-center gap-2">
            <h1 class="truncate text-[15px] font-semibold text-white">{{ name }}</h1>
            <span
              class="shrink-0 rounded-full bg-white/10 px-2 py-0.5 text-[10px] font-medium text-white/80"
              >AI</span
            >
          </div>
          <p class="flex items-center gap-1.5 text-xs text-white/60">
            <span class="h-1.5 w-1.5 rounded-full bg-emerald-400" />
            Online · Usually replies instantly
          </p>
        </div>
      </div>

      <button
        class="relative z-10 ml-3 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-white/70 transition hover:bg-white/10 hover:text-white"
        aria-label="Minimize chat"
        @click="$emit('minimize')"
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
          <path d="M6 12h12" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
        </svg>
      </button>
    </div>
  </div>
</template>