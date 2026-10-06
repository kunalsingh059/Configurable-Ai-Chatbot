<script setup>
defineProps({
  primaryColor: { type: String, default: null },
});
defineEmits(["click"]);
</script>

<template>
  <button
    class="flex h-16 w-16 items-center justify-center rounded-full bg-navy-950 text-amber-500 shadow-lg transition hover:scale-105 active:scale-95 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-500"
    :style="primaryColor ? { backgroundColor: primaryColor } : {}"
    aria-label="Open chat"
    @click="$emit('click')"
  >
    <svg width="26" height="26" viewBox="0 0 24 24" fill="none">
      <path
        d="M4 4h16v12H8l-4 4V4z"
        stroke="currentColor"
        stroke-width="1.8"
        stroke-linejoin="round"
      />
    </svg>
  </button>
</template>