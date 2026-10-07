<script setup>
import { ref, onMounted, computed } from "vue";
import { useAuthStore } from "../stores/auth";
import { api, ApiError } from "../services/api";
import { useToast } from "../composables/useToast";

const auth = useAuthStore();
const toast = useToast();

const items = ref([]);
const totalCount = ref(0);
const openCount = ref(0);
const currentPage = ref(1);
const limit = 10;
const statusFilter = ref("open"); // "open" | "resolved" | "ignored" | "all"
const isLoading = ref(true);
const error = ref(null);
const updatingId = ref(null);

async function load() {
  isLoading.value = true;
  error.value = null;
  try {
    const data = await api.listUnanswered(auth.token, {
      status: statusFilter.value,
      page: currentPage.value,
      limit,
    });
    items.value = data.items || [];
    totalCount.value = data.total || 0;
    openCount.value = data.open_count || 0;
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : "Couldn't load unanswered questions.";
  } finally {
    isLoading.value = false;
  }
}

async function setStatus(item, newStatus) {
  updatingId.value = item.id;
  try {
    await api.updateUnansweredStatus(auth.token, item.id, newStatus);
    toast.success(`Question marked as ${newStatus}.`);
    // Reload to keep counts and filters accurate
    await load();
  } catch (err) {
    toast.error(err instanceof ApiError ? err.message : "Failed to update status.");
  } finally {
    updatingId.value = null;
  }
}

function formatDate(isoStr) {
  if (!isoStr) return "";
  try {
    const d = new Date(isoStr);
    return d.toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return isoStr;
  }
}

function changeFilter(newStatus) {
  statusFilter.value = newStatus;
  currentPage.value = 1;
  load();
}

const totalPages = computed(() => Math.ceil(totalCount.value / limit) || 1);

onMounted(load);
</script>

<template>
  <div class="rounded-2xl bg-white p-4 sm:p-5 shadow-sm ring-1 ring-slate-100">
    <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
      <div>
        <div class="flex items-center gap-2">
          <h2 class="text-sm font-semibold text-navy-950">Unanswered questions</h2>
          <span
            v-if="openCount > 0"
            class="rounded-full bg-amber-500/15 px-2 py-0.5 text-[11px] font-semibold text-amber-800"
          >
            {{ openCount }} open
          </span>
        </div>
        <p class="mt-1 text-xs text-slate-500">
          Questions customers asked where your assistant had no matching tools or documents.
        </p>
      </div>

      <!-- Filter pills -->
      <div class="flex shrink-0 items-center gap-1 rounded-lg bg-slate-100 p-0.5 text-xs overflow-x-auto max-w-full">
        <button
          type="button"
          class="rounded-md px-2.5 py-1 text-[11px] font-medium whitespace-nowrap transition"
          :class="statusFilter === 'open' ? 'bg-white text-navy-950 shadow-sm' : 'text-slate-500 hover:text-slate-900'"
          @click="changeFilter('open')"
        >
          Open
        </button>
        <button
          type="button"
          class="rounded-md px-2.5 py-1 text-[11px] font-medium whitespace-nowrap transition"
          :class="statusFilter === 'resolved' ? 'bg-white text-navy-950 shadow-sm' : 'text-slate-500 hover:text-slate-900'"
          @click="changeFilter('resolved')"
        >
          Resolved
        </button>
        <button
          type="button"
          class="rounded-md px-2.5 py-1 text-[11px] font-medium whitespace-nowrap transition"
          :class="statusFilter === 'all' ? 'bg-white text-navy-950 shadow-sm' : 'text-slate-500 hover:text-slate-900'"
          @click="changeFilter('all')"
        >
          All
        </button>
      </div>
    </div>

    <p v-if="error" class="mt-3 rounded-lg bg-rose-50 px-3 py-2 text-xs text-rose-600">{{ error }}</p>
    <p v-if="isLoading" class="mt-4 text-xs text-slate-400">Loading...</p>

    <div
      v-else-if="items.length === 0"
      class="mt-4 rounded-lg border border-dashed border-slate-200 px-4 py-8 text-center text-xs text-slate-400"
    >
      {{ statusFilter === 'open' ? 'No open unanswered questions! Your assistant answered everything.' : 'No questions found under this filter.' }}
    </div>

    <ul v-else class="mt-4 divide-y divide-slate-100">
      <li
        v-for="item in items"
        :key="item.id"
        class="flex flex-col gap-2.5 py-3 sm:flex-row sm:items-center sm:justify-between"
      >
        <div class="min-w-0 flex-1">
          <p class="text-sm font-medium text-navy-950 break-words">
            "{{ item.question }}"
          </p>
          <div class="mt-1 flex flex-wrap items-center gap-2 text-[11px] text-slate-400">
            <span>{{ formatDate(item.timestamp) }}</span>
            <span>&bull;</span>
            <span
              class="capitalize font-medium"
              :class="{
                'text-amber-600': item.status === 'open',
                'text-emerald-600': item.status === 'resolved',
                'text-slate-400': item.status === 'ignored',
              }"
            >
              {{ item.status }}
            </span>
            <span v-if="item.reason" class="text-slate-400">({{ item.reason.replace(/_/g, " ") }})</span>
          </div>
        </div>

        <div class="flex shrink-0 items-center gap-2 pt-1 sm:pt-0 self-start sm:self-auto">
          <button
            v-if="item.status === 'open'"
            type="button"
            :disabled="updatingId === item.id"
            class="rounded-lg border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-700 hover:bg-emerald-100 disabled:opacity-50"
            @click="setStatus(item, 'resolved')"
          >
            Resolve
          </button>
          <button
            v-if="item.status === 'open'"
            type="button"
            :disabled="updatingId === item.id"
            class="rounded-lg border border-slate-200 px-2.5 py-1 text-xs font-medium text-slate-600 hover:bg-slate-50 disabled:opacity-50"
            @click="setStatus(item, 'ignored')"
          >
            Ignore
          </button>
          <button
            v-if="item.status !== 'open'"
            type="button"
            :disabled="updatingId === item.id"
            class="rounded-lg border border-slate-200 px-2.5 py-1 text-xs font-medium text-slate-600 hover:bg-slate-50 disabled:opacity-50"
            @click="setStatus(item, 'open')"
          >
            Reopen
          </button>
        </div>
      </li>
    </ul>

    <!-- Pagination -->
    <div
      v-if="totalPages > 1"
      class="mt-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 border-t border-slate-100 pt-3 text-xs text-slate-500"
    >
      <span class="text-center sm:text-left">Page {{ currentPage }} of {{ totalPages }}</span>
      <div class="flex items-center justify-center gap-1.5">
        <button
          type="button"
          :disabled="currentPage <= 1 || isLoading"
          class="rounded border border-slate-200 px-2.5 py-1 font-medium disabled:opacity-40 hover:bg-slate-50"
          @click="currentPage--; load()"
        >
          Previous
        </button>
        <button
          type="button"
          :disabled="currentPage >= totalPages || isLoading"
          class="rounded border border-slate-200 px-2.5 py-1 font-medium disabled:opacity-40 hover:bg-slate-50"
          @click="currentPage++; load()"
        >
          Next
        </button>
      </div>
    </div>
  </div>
</template>
