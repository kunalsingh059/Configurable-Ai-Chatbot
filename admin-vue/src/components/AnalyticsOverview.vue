<script setup>
import { ref, onMounted, computed, watch } from "vue";
import { useAuthStore } from "../stores/auth";
import { api, ApiError } from "../services/api";

const auth = useAuthStore();

const selectedRange = ref("7d"); // "7d" | "30d"
const isLoading = ref(true);
const isRefreshing = ref(false);
const error = ref(null);

const tiles = ref({
  conversations: 0,
  messages: 0,
  satisfaction_pct: null,
  thumbs_up: 0,
  thumbs_down: 0,
  unanswered_open: 0,
});

const dailySeries = ref([]);

const maxMessages = computed(() => {
  if (!dailySeries.value.length) return 1;
  const max = Math.max(...dailySeries.value.map((d) => d.messages), 0);
  return max > 0 ? max : 1;
});

function formatShortDate(dateStr) {
  if (!dateStr) return "";
  const parts = dateStr.split("-");
  if (parts.length === 3) {
    const d = new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]));
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  }
  return dateStr;
}

async function loadAnalytics(background = false) {
  if (!background) {
    isLoading.value = true;
  } else {
    isRefreshing.value = true;
  }
  error.value = null;

  try {
    const data = await api.getAnalytics(auth.token, selectedRange.value);
    tiles.value = data.tiles || {
      conversations: 0,
      messages: 0,
      satisfaction_pct: null,
      thumbs_up: 0,
      thumbs_down: 0,
      unanswered_open: 0,
    };
    dailySeries.value = data.daily_series || [];
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : "Failed to load analytics.";
  } finally {
    isLoading.value = false;
    isRefreshing.value = false;
  }
}

watch(selectedRange, () => {
  loadAnalytics(false);
});

onMounted(() => {
  loadAnalytics(false);
});
</script>

<template>
  <div class="rounded-2xl bg-white p-4 sm:p-5 shadow-sm ring-1 ring-slate-100">
    <!-- Header -->
    <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <div class="flex items-center gap-2">
          <h2 class="text-sm font-semibold text-navy-950">Analytics overview</h2>
          <span
            v-if="isRefreshing"
            class="text-[11px] font-medium text-slate-400"
          >
            Refreshing...
          </span>
        </div>
        <p class="mt-1 text-xs text-slate-500">
          Activity volume, conversation trends, and satisfaction for your assistant.
        </p>
      </div>

      <div class="flex items-center justify-between sm:justify-end gap-2 w-full sm:w-auto">
        <!-- Range toggle pills -->
        <div class="flex shrink-0 items-center gap-1 rounded-lg bg-slate-100 p-0.5 text-xs">
          <button
            type="button"
            class="rounded-md px-2.5 py-1 text-[11px] font-medium transition"
            :class="selectedRange === '7d' ? 'bg-white text-navy-950 shadow-sm' : 'text-slate-500 hover:text-slate-900'"
            @click="selectedRange = '7d'"
          >
            7 Days
          </button>
          <button
            type="button"
            class="rounded-md px-2.5 py-1 text-[11px] font-medium transition"
            :class="selectedRange === '30d' ? 'bg-white text-navy-950 shadow-sm' : 'text-slate-500 hover:text-slate-900'"
            @click="selectedRange = '30d'"
          >
            30 Days
          </button>
        </div>

        <button
          type="button"
          title="Refresh analytics"
          class="rounded-lg border border-slate-200 p-1.5 text-slate-500 transition hover:border-slate-300 hover:text-navy-900"
          @click="loadAnalytics(true)"
        >
          <svg
            class="h-3.5 w-3.5"
            :class="{ 'animate-spin': isRefreshing }"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            stroke-width="2"
          >
            <path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
        </button>
      </div>
    </div>

    <p v-if="error" class="mt-3 rounded-lg bg-rose-50 px-3 py-2 text-xs text-rose-600">
      {{ error }}
    </p>

    <!-- Loading Skeleton -->
    <div v-if="isLoading" class="mt-4 grid grid-cols-2 gap-2.5 sm:gap-3 sm:grid-cols-4">
      <div v-for="i in 4" :key="i" class="h-20 animate-pulse rounded-xl bg-slate-50" />
    </div>

    <div v-else class="mt-4 space-y-4 sm:space-y-5">
      <!-- 4 Main Tiles -->
      <div class="grid grid-cols-2 gap-2.5 sm:gap-3 sm:grid-cols-4">
        <!-- Conversations Tile -->
        <div class="rounded-xl border border-slate-100 bg-slate-50/50 p-3 sm:p-3.5 transition hover:border-slate-200">
          <div class="flex items-center justify-between text-slate-500">
            <span class="text-xs font-medium">Conversations</span>
            <svg class="h-4 w-4 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
            </svg>
          </div>
          <div class="mt-2 flex items-baseline gap-1.5">
            <span class="text-lg sm:text-xl font-bold tracking-tight text-navy-950">
              {{ tiles.conversations.toLocaleString() }}
            </span>
          </div>
          <p class="mt-0.5 text-[10px] sm:text-[11px] text-slate-400">Distinct sessions</p>
        </div>

        <!-- Messages Tile -->
        <div class="rounded-xl border border-slate-100 bg-slate-50/50 p-3 sm:p-3.5 transition hover:border-slate-200">
          <div class="flex items-center justify-between text-slate-500">
            <span class="text-xs font-medium">Messages</span>
            <svg class="h-4 w-4 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 8h10M7 12h4m1 8l-4-4H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-3l-4 4z" />
            </svg>
          </div>
          <div class="mt-2 flex items-baseline gap-1.5">
            <span class="text-lg sm:text-xl font-bold tracking-tight text-navy-950">
              {{ tiles.messages.toLocaleString() }}
            </span>
          </div>
          <p class="mt-0.5 text-[10px] sm:text-[11px] text-slate-400">Total exchanges</p>
        </div>

        <!-- Satisfaction Tile -->
        <div class="rounded-xl border border-slate-100 bg-slate-50/50 p-3 sm:p-3.5 transition hover:border-slate-200">
          <div class="flex items-center justify-between text-slate-500">
            <span class="text-xs font-medium">Satisfaction</span>
            <svg class="h-4 w-4 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14 10h4.764a2 2 0 011.789 2.894l-3.5 7A2 2 0 0115.263 21h-4.017c-.163 0-.326-.02-.485-.06L7 20m7-10V5a2 2 0 00-2-2h-.095c-.5 0-.905.405-.905.905 0 .714-.211 1.412-.608 2.006L7 11v9m7-10h-2M7 20H5a2 2 0 01-2-2v-6a2 2 0 012-2h2.5" />
            </svg>
          </div>
          <div class="mt-2 flex items-baseline gap-1.5">
            <span class="text-lg sm:text-xl font-bold tracking-tight text-navy-950">
              {{ tiles.satisfaction_pct != null ? `${tiles.satisfaction_pct}%` : "—" }}
            </span>
          </div>
          <p class="mt-0.5 flex flex-wrap items-center gap-1 sm:gap-1.5 text-[10px] sm:text-[11px] text-slate-500">
            <span class="text-emerald-700 font-medium">👍 {{ tiles.thumbs_up }}</span>
            <span class="text-slate-300">·</span>
            <span class="text-rose-600 font-medium">👎 {{ tiles.thumbs_down }}</span>
          </p>
        </div>

        <!-- Unanswered Tile -->
        <div class="rounded-xl border border-slate-100 bg-slate-50/50 p-3 sm:p-3.5 transition hover:border-slate-200">
          <div class="flex items-center justify-between text-slate-500">
            <span class="text-xs font-medium">Unanswered</span>
            <svg class="h-4 w-4 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
          <div class="mt-2 flex items-baseline gap-1.5">
            <span
              class="text-lg sm:text-xl font-bold tracking-tight"
              :class="tiles.unanswered_open > 0 ? 'text-amber-800' : 'text-navy-950'"
            >
              {{ tiles.unanswered_open }}
            </span>
          </div>
          <p class="mt-0.5 text-[10px] sm:text-[11px]" :class="tiles.unanswered_open > 0 ? 'text-amber-800 font-medium' : 'text-slate-400'">
            {{ tiles.unanswered_open > 0 ? 'Open questions' : 'Zero unhandled' }}
          </p>
        </div>
      </div>

      <!-- Activity Trend Chart (reads from usage_daily) -->
      <div class="rounded-xl border border-slate-100 bg-slate-50/30 p-3.5 sm:p-4">
        <div class="mb-3 flex flex-wrap items-center justify-between gap-1">
          <h3 class="text-xs font-semibold uppercase tracking-wider text-slate-500">
            Daily Activity Trend (Messages & Conversations)
          </h3>
          <span class="text-[11px] text-slate-400">
            Last {{ selectedRange === '30d' ? '30' : '7' }} days
          </span>
        </div>

        <div v-if="dailySeries.length === 0" class="py-6 text-center text-xs text-slate-400">
          No usage activity recorded yet.
        </div>

        <div v-else class="space-y-2">
          <!-- Responsive CSS Bar Columns -->
          <div class="flex h-32 items-end gap-0.5 sm:gap-1.5 pt-4">
            <div
              v-for="(day, idx) in dailySeries"
              :key="day.date"
              class="group relative flex flex-1 flex-col items-center h-full justify-end"
            >
              <!-- Hover Tooltip -->
              <div
                class="pointer-events-none absolute -top-10 z-20 hidden whitespace-nowrap rounded-md bg-navy-950 px-2 py-1 text-[10px] text-white shadow-lg group-hover:block"
                :class="idx === 0 ? 'left-0' : idx === dailySeries.length - 1 ? 'right-0' : 'left-1/2 -translate-x-1/2'"
              >
                {{ formatShortDate(day.date) }}: {{ day.messages }} msgs, {{ day.conversations }} convs
              </div>

              <!-- Bar Fill -->
              <div
                class="w-full max-w-[28px] rounded-t transition-all duration-300"
                :class="day.messages > 0 ? 'bg-amber-500 hover:bg-amber-600' : 'bg-slate-200/60'"
                :style="{
                  height: day.messages > 0
                    ? `${Math.max(8, Math.round((day.messages / maxMessages) * 100))}%`
                    : '4px'
                }"
              />
            </div>
          </div>

          <!-- X-Axis Date Labels -->
          <div class="flex items-center justify-between border-t border-slate-200/60 pt-1.5 text-[10px] text-slate-400">
            <span>{{ formatShortDate(dailySeries[0]?.date) }}</span>
            <span v-if="dailySeries.length > 2">{{ formatShortDate(dailySeries[Math.floor(dailySeries.length / 2)]?.date) }}</span>
            <span>{{ formatShortDate(dailySeries[dailySeries.length - 1]?.date) }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
