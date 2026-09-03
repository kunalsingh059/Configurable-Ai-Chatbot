<script setup>
const emit = defineEmits(["select"]);

const actions = ["Browse products", "Ask about prices", "Policies"];
</script>

<template>
  <div class="flex flex-wrap gap-2 pl-10">
    <button
      v-for="action in actions"
      :key="action"
      class="rounded-xl border border-slate-200 bg-white px-4 py-2 text-[13px] font-medium text-navy-900 transition hover:border-amber-500 hover:text-amber-600"
      @click="emit('select', action)"
    >
      {{ action }}
    </button>
  </div>
</template>