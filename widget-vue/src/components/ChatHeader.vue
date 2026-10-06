<script setup>
import { ref } from "vue";

defineProps({
  name: { type: String, default: "Support Assistant" },
  initials: { type: String, default: "AI" },
  avatarUrl: { type: String, default: null },
  primaryColor: { type: String, default: null },
  handoffEnabled: { type: Boolean, default: false },
});
const emit = defineEmits(["minimize", "clear", "contact"]);

const menuOpen = ref(false);

function clearAndClose() {
  menuOpen.value = false;
  emit("clear");
}

function contactAndClose() {
  menuOpen.value = false;
  emit("contact");
}
</script>

<template>
  <div
    class="relative bg-navy-950 px-4 py-3.5 transition-colors"
    :style="primaryColor ? { backgroundColor: primaryColor } : {}"
  >
    <div class="pointer-events-none absolute inset-0 overflow-hidden">
      <div class="absolute -right-6 -top-10 h-32 w-32 rounded-full bg-white/10" />
    </div>
    <div class="relative flex items-center justify-between gap-2">
      <div class="flex min-w-0 items-center gap-2.5">
        <img
          v-if="avatarUrl"
          :src="avatarUrl"
          alt="Avatar"
          class="h-10 w-10 shrink-0 rounded-xl object-cover ring-1 ring-white/20"
          @error="(e) => (e.target.style.display = 'none')"
        />
        <div
          v-else
          class="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-amber-500 text-sm font-semibold text-navy-950"
        >
          {{ initials }}
        </div>
        <div class="min-w-0">
          <h1 class="truncate text-[14px] font-semibold text-white" :title="name">{{ name }}</h1>
          <p class="flex items-center gap-1.5 text-[11px] text-white/70">
            <span class="h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-400" />
            <span class="truncate">Online · Usually replies instantly</span>
          </p>
        </div>
      </div>

      <div class="relative z-10 flex shrink-0 items-center gap-0.5">
        <!-- Contact Human Support Button (T9) -->
        <button
          v-if="handoffEnabled"
          class="flex h-8 w-8 items-center justify-center rounded-lg text-white/70 transition hover:bg-white/10 hover:text-white"
          aria-label="Contact support"
          title="Talk to a person"
          @click="$emit('contact')"
        >
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z" />
          </svg>
        </button>

        <div class="relative">
          <button
            class="flex h-8 w-8 items-center justify-center rounded-lg text-white/70 transition hover:bg-white/10 hover:text-white"
            aria-label="More options"
            aria-haspopup="true"
            :aria-expanded="menuOpen"
            @click="menuOpen = !menuOpen"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
              <circle cx="12" cy="5" r="1.8" />
              <circle cx="12" cy="12" r="1.8" />
              <circle cx="12" cy="19" r="1.8" />
            </svg>
          </button>

          <div v-if="menuOpen" class="fixed inset-0 z-10" @click="menuOpen = false" />

          <Transition name="fade">
            <div
              v-if="menuOpen"
              class="absolute right-0 top-full z-20 mt-1 w-44 overflow-hidden rounded-xl bg-white py-1 text-navy-950 shadow-xl ring-1 ring-black/5"
            >
              <button
                v-if="handoffEnabled"
                class="block w-full px-3 py-2 text-left text-[13px] font-medium text-navy-950 transition hover:bg-slate-50 border-b border-slate-100"
                @click="contactAndClose"
              >
                Talk to a person
              </button>
              <button
                class="block w-full px-3 py-2 text-left text-[13px] font-medium text-navy-950 transition hover:bg-slate-50"
                @click="clearAndClose"
              >
                Clear conversation
              </button>
            </div>
          </Transition>
        </div>

        <button
          class="flex h-8 w-8 items-center justify-center rounded-lg text-white/70 transition hover:bg-white/10 hover:text-white"
          aria-label="Minimize chat"
          title="Minimize"
          @click="$emit('minimize')"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
            <path d="M6 12h12" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
          </svg>
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.12s ease, transform 0.12s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}
</style>