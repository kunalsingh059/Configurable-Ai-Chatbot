<script setup>
import ToastContainer from "./components/ToastContainer.vue";
</script>

<template>
  <div class="min-h-screen bg-slate-50 text-navy-950">
    <router-view />
    <ToastContainer />
  </div>
</template>