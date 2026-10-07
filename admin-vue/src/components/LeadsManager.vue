<script setup>
import { ref, onMounted, computed } from "vue";
import { useAuthStore } from "../stores/auth";
import { api, ApiError } from "../services/api";
import { useToast } from "../composables/useToast";

const auth = useAuthStore();
const toast = useToast();

const items = ref([]);
const totalCount = ref(0);
const counts = ref({ all: 0, new: 0, contacted: 0, closed: 0 });
const currentPage = ref(1);
const limit = 10;
const statusFilter = ref("all"); // "all" | "new" | "contacted" | "closed"
const isLoading = ref(true);
const isExporting = ref(false);
const error = ref(null);
const expandedLeadId = ref(null);
const updatingId = ref(null);

async function load() {
  isLoading.value = true;
  error.value = null;
  try {
    const data = await api.listLeads(auth.token, {
      status: statusFilter.value,
      page: currentPage.value,
      limit,
    });
    items.value = data.items || [];
    totalCount.value = data.total || 0;
    counts.value = data.counts || { all: 0, new: 0, contacted: 0, closed: 0 };
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : "Couldn't load customer leads.";
  } finally {
    isLoading.value = false;
  }
}

async function setStatus(lead, newStatus) {
  if (lead.status === newStatus) return;
  updatingId.value = lead.id;
  try {
    await api.updateLeadStatus(auth.token, lead.id, newStatus);
    lead.status = newStatus;
    toast.success(`Lead status updated to ${newStatus}.`);
    // Refresh counts in background
    load();
  } catch (err) {
    toast.error(err instanceof ApiError ? err.message : "Failed to update lead status.");
  } finally {
    updatingId.value = null;
  }
}

async function exportCsv() {
  isExporting.value = true;
  try {
    const blob = await api.exportLeadsCsv(auth.token);
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `leads_${auth.tenantId || "export"}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);
    toast.success("Leads CSV exported successfully.");
  } catch (err) {
    toast.error(err instanceof ApiError ? err.message : "Failed to export leads.");
  } finally {
    isExporting.value = false;
  }
}

function toggleExpand(id) {
  expandedLeadId.value = expandedLeadId.value === id ? null : id;
}

function changeFilter(filter) {
  statusFilter.value = filter;
  currentPage.value = 1;
  load();
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

const totalPages = computed(() => Math.ceil(totalCount.value / limit) || 1);

function prevPage() {
  if (currentPage.value > 1) {
    currentPage.value--;
    load();
  }
}

function nextPage() {
  if (currentPage.value < totalPages.value) {
    currentPage.value++;
    load();
  }
}

onMounted(load);
</script>

<template>
  <div class="rounded-2xl bg-white p-4 sm:p-5 shadow-sm ring-1 ring-slate-100">
    <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
      <div>
        <div class="flex items-center gap-2">
          <h2 class="text-sm font-semibold text-navy-950">Customer leads & inquiries</h2>
          <span
            v-if="counts.new > 0"
            class="rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-semibold text-emerald-800"
          >
            {{ counts.new }} new
          </span>
        </div>
        <p class="mt-1 text-xs text-slate-500">
          Visitors who requested human assistance or left contact information via chat.
        </p>
      </div>

      <div class="flex flex-col sm:flex-row sm:items-center gap-2 w-full sm:w-auto">
        <!-- Filter pills -->
        <div class="flex shrink-0 items-center gap-1 rounded-lg bg-slate-100 p-0.5 text-xs overflow-x-auto max-w-full">
          <button
            type="button"
            class="rounded-md px-2.5 py-1 text-[11px] font-medium whitespace-nowrap transition"
            :class="statusFilter === 'all' ? 'bg-white text-navy-950 shadow-sm' : 'text-slate-500 hover:text-slate-900'"
            @click="changeFilter('all')"
          >
            All ({{ counts.all }})
          </button>
          <button
            type="button"
            class="rounded-md px-2.5 py-1 text-[11px] font-medium whitespace-nowrap transition"
            :class="statusFilter === 'new' ? 'bg-white text-navy-950 shadow-sm' : 'text-slate-500 hover:text-slate-900'"
            @click="changeFilter('new')"
          >
            New ({{ counts.new }})
          </button>
          <button
            type="button"
            class="rounded-md px-2.5 py-1 text-[11px] font-medium whitespace-nowrap transition"
            :class="statusFilter === 'contacted' ? 'bg-white text-navy-950 shadow-sm' : 'text-slate-500 hover:text-slate-900'"
            @click="changeFilter('contacted')"
          >
            Contacted ({{ counts.contacted }})
          </button>
          <button
            type="button"
            class="rounded-md px-2.5 py-1 text-[11px] font-medium whitespace-nowrap transition"
            :class="statusFilter === 'closed' ? 'bg-white text-navy-950 shadow-sm' : 'text-slate-500 hover:text-slate-900'"
            @click="changeFilter('closed')"
          >
            Closed ({{ counts.closed }})
          </button>
        </div>

        <!-- Export CSV Button -->
        <button
          type="button"
          :disabled="isExporting || totalCount === 0"
          class="flex items-center justify-center gap-1.5 rounded-lg border border-slate-200 px-2.5 py-1 text-[11px] font-medium text-slate-700 transition hover:border-slate-300 hover:bg-slate-50 disabled:opacity-40 w-full sm:w-auto shrink-0"
          @click="exportCsv"
        >
          <svg class="h-3.5 w-3.5 text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
          {{ isExporting ? "Exporting..." : "Export CSV" }}
        </button>
      </div>
    </div>

    <p v-if="error" class="mt-3 rounded-lg bg-rose-50 px-3 py-2 text-xs text-rose-600">{{ error }}</p>
    <p v-if="isLoading" class="mt-4 text-xs text-slate-400">Loading leads...</p>

    <div
      v-else-if="items.length === 0"
      class="mt-4 rounded-xl border border-dashed border-slate-200 p-8 text-center"
    >
      <p class="text-xs font-medium text-slate-600">No leads captured yet.</p>
      <p class="mt-1 text-[11px] text-slate-400">
        When visitors submit their contact details via the chatbot, they'll appear here.
      </p>
    </div>

    <div v-else class="mt-4 divide-y divide-slate-100">
      <div
        v-for="lead in items"
        :key="lead.id"
        class="py-3.5 first:pt-0 last:pb-0"
      >
        <div class="flex flex-col gap-2.5 sm:flex-row sm:items-start sm:justify-between">
          <div class="min-w-0 flex-1">
            <div class="flex flex-wrap items-center gap-1.5 sm:gap-2">
              <span class="text-xs font-semibold text-navy-950">{{ lead.name }}</span>
              <span
                class="rounded-full px-2 py-0.5 text-[10px] font-medium capitalize"
                :class="{
                  'bg-emerald-50 text-emerald-800 border border-emerald-200/60': lead.status === 'new',
                  'bg-blue-50 text-blue-800 border border-blue-200/60': lead.status === 'contacted',
                  'bg-slate-100 text-slate-600': lead.status === 'closed',
                }"
              >
                {{ lead.status }}
              </span>
              <span class="text-[11px] text-slate-400">{{ formatDate(lead.created_at) }}</span>
            </div>

            <!-- Contact info pills -->
            <div class="mt-1.5 flex flex-wrap items-center gap-2 text-xs text-slate-600">
              <a
                v-if="lead.email"
                :href="`mailto:${lead.email}`"
                class="inline-flex items-center gap-1 rounded bg-slate-50 px-1.5 py-0.5 text-[11px] text-slate-600 hover:text-navy-900 hover:underline break-all"
              >
                <span>✉</span> {{ lead.email }}
              </a>
              <a
                v-if="lead.phone"
                :href="`tel:${lead.phone}`"
                class="inline-flex items-center gap-1 rounded bg-slate-50 px-1.5 py-0.5 text-[11px] text-slate-600 hover:text-navy-900 hover:underline break-all"
              >
                <span>📞</span> {{ lead.phone }}
              </a>
            </div>

            <!-- Customer Note / Message -->
            <p v-if="lead.message" class="mt-2 text-xs text-slate-700 bg-slate-50/70 rounded-lg p-2.5 border border-slate-100 break-words">
              <span class="font-medium text-slate-500">Note:</span> {{ lead.message }}
            </p>
          </div>

          <!-- Actions & Status Toggle -->
          <div class="flex shrink-0 items-center gap-2 pt-1 sm:pt-0 self-start sm:self-auto">
            <!-- Transcript Toggle -->
            <button
              v-if="lead.chat_history && lead.chat_history.length > 0"
              type="button"
              class="rounded-lg border border-slate-200 px-2 py-1 text-[11px] font-medium text-slate-600 transition hover:bg-slate-50"
              @click="toggleExpand(lead.id)"
            >
              {{ expandedLeadId === lead.id ? "Hide Chat" : "View Chat" }}
              ({{ lead.chat_history.length }})
            </button>

            <!-- Status Dropdown / Action -->
            <select
              :value="lead.status"
              :disabled="updatingId === lead.id"
              class="rounded-lg border border-slate-200 bg-white px-2 py-1 text-[11px] font-medium text-slate-700 transition hover:border-slate-300 focus:outline-none focus:ring-1 focus:ring-amber-400"
              @change="setStatus(lead, $event.target.value)"
            >
              <option value="new">Mark New</option>
              <option value="contacted">Mark Contacted</option>
              <option value="closed">Mark Closed</option>
            </select>
          </div>
        </div>

        <!-- Expanded Chat Transcript -->
        <div
          v-if="expandedLeadId === lead.id"
          class="mt-3 rounded-xl border border-slate-200/80 bg-slate-50/50 p-3 text-xs"
        >
          <div class="mb-2 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-1 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
            <span class="truncate">Recent conversation context (last {{ lead.chat_history.length }} msgs)</span>
            <span class="truncate font-mono text-[10px]">Session: {{ lead.session_id }}</span>
          </div>

          <div class="space-y-2 max-h-60 overflow-y-auto pr-1">
            <div
              v-for="(msg, idx) in lead.chat_history"
              :key="idx"
              class="rounded-lg p-2 text-xs"
              :class="msg.role === 'user' ? 'bg-amber-50/60 border border-amber-100/70' : 'bg-white border border-slate-200/60'"
            >
              <span class="block text-[10px] font-semibold uppercase tracking-wider" :class="msg.role === 'user' ? 'text-amber-800' : 'text-slate-400'">
                {{ msg.role === 'user' ? 'Customer' : 'Assistant' }}
              </span>
              <p class="mt-0.5 text-slate-800 whitespace-pre-wrap break-words">{{ msg.content }}</p>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Pagination -->
    <div
      v-if="!isLoading && totalCount > limit"
      class="mt-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 border-t border-slate-100 pt-3 text-xs text-slate-500"
    >
      <span class="text-center sm:text-left">Page {{ currentPage }} of {{ totalPages }} ({{ totalCount }} total)</span>
      <div class="flex items-center justify-center gap-1">
        <button
          type="button"
          :disabled="currentPage <= 1"
          class="rounded-md border border-slate-200 px-2 py-1 text-[11px] font-medium text-slate-600 disabled:opacity-40"
          @click="prevPage"
        >
          Previous
        </button>
        <button
          type="button"
          :disabled="currentPage >= totalPages"
          class="rounded-md border border-slate-200 px-2 py-1 text-[11px] font-medium text-slate-600 disabled:opacity-40"
          @click="nextPage"
        >
          Next
        </button>
      </div>
    </div>
  </div>
</template>
