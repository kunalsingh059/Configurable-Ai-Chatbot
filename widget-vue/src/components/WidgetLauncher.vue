<script setup>
defineEmits(["click"]);
</script>

<template>
  <button
    class="flex h-14 w-14 items-center justify-center rounded-full bg-navy-950 text-amber-500 shadow-lg transition hover:scale-105 active:scale-95"
    aria-label="Open chat"
    @click="$emit('click')"
  >
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
      <path
        d="M4 4h16v12H8l-4 4V4z"
        stroke="currentColor"
        stroke-width="1.8"
        stroke-linejoin="round"
      />
    </svg>
  </button>
</template>