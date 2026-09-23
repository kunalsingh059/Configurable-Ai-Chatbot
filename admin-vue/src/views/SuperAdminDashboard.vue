<script setup>
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { useAuthStore } from "../stores/auth";
import { api, ApiError } from "../services/api";
import { useToast } from "../composables/useToast";
import ConfirmDialog from "../components/ConfirmDialog.vue";

const auth = useAuthStore();
const router = useRouter();
const toast = useToast();

const owners = ref([]);
const isLoading = ref(true);
const error = ref(null);
const pendingId = ref(null);
const showLogoutConfirm = ref(false);

const searchQuery = ref("");
const statusFilter = ref("all"); // "all" | "active" | "pending"
const pendingDeactivate = ref(null); // the owner awaiting confirmation, or null

const totalCount = computed(() => owners.value.length);
const activeCount = computed(() => owners.value.filter((o) => o.is_active).length);
const pendingCount = computed(() => totalCount.value - activeCount.value);

const filteredOwners = computed(() => {
  let list = owners.value;
  if (statusFilter.value === "active") list = list.filter((o) => o.is_active);
  else if (statusFilter.value === "pending") list = list.filter((o) => !o.is_active);

  const q = searchQuery.value.trim().toLowerCase();
  if (q) {
    list = list.filter(
      (o) => o.username.toLowerCase().includes(q) || o.tenant_id.toLowerCase().includes(q)
    );
  }
  return list;
});

async function load() {
  isLoading.value = true;
  error.value = null;
  try {
    owners.value = await api.listOwners(auth.token);
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : "Couldn't load business owners.";
  } finally {
    isLoading.value = false;
  }
}

// Activating is safe (a business simply gains access) so it applies right
// away. Deactivating cuts off a live business's chatbot immediately, so - to
// match how the rest of the app treats destructive actions (see
// DocumentsManager's delete confirm) - it goes through ConfirmDialog first.
async function toggle(owner) {
  if (owner.is_active) {
    pendingDeactivate.value = owner;
    return;
  }
  await applyToggle(owner);
}

async function confirmDeactivate() {
  const owner = pendingDeactivate.value;
  pendingDeactivate.value = null;
  await applyToggle(owner);
}

async function applyToggle(owner) {
  pendingId.value = owner.id;
  try {
    if (owner.is_active) {
      await api.deactivateOwner(auth.token, owner.id);
      toast.success(`${owner.username} deactivated.`);
    } else {
      await api.activateOwner(auth.token, owner.id);
      toast.success(`${owner.username} activated.`);
    }
    owner.is_active = !owner.is_active;
  } catch (err) {
    toast.error(err instanceof ApiError ? err.message : "Couldn't update this account.");
  } finally {
    pendingId.value = null;
  }
}

function confirmLogout() {
  showLogoutConfirm.value = false;
  auth.logout();
  router.push("/login");
}

onMounted(load);
</script>

<template>
  <div class="mx-auto max-w-2xl px-4 py-8">
    <div class="mb-6 flex items-center justify-between">
      <div>
        <h1 class="text-lg font-semibold text-navy-950">Business owners</h1>
        <p class="text-sm text-slate-500">Activate accounts to let them use the platform.</p>
      </div>
      <button class="rounded-lg border border-slate-200 px-3 py-2 text-xs font-medium text-navy-900 hover:border-amber-500" @click="showLogoutConfirm = true">
        Log out
      </button>
    </div>

    <!-- Stats -->
    <div v-if="!isLoading && totalCount > 0" class="mb-4 grid grid-cols-3 gap-3">
      <div class="rounded-2xl bg-white p-4 text-center shadow-sm ring-1 ring-slate-100">
        <p class="text-2xl font-semibold text-navy-950">{{ totalCount }}</p>
        <p class="text-xs text-slate-500">Total</p>
      </div>
      <div class="rounded-2xl bg-white p-4 text-center shadow-sm ring-1 ring-slate-100">
        <p class="text-2xl font-semibold text-emerald-600">{{ activeCount }}</p>
        <p class="text-xs text-slate-500">Active</p>
      </div>
      <div class="rounded-2xl bg-white p-4 text-center shadow-sm ring-1 ring-slate-100">
        <p class="text-2xl font-semibold text-amber-600">{{ pendingCount }}</p>
        <p class="text-xs text-slate-500">Pending</p>
      </div>
    </div>

    <div class="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-slate-100">
      <p v-if="error" class="mb-3 rounded-lg bg-rose-50 px-3 py-2 text-xs text-rose-600">{{ error }}</p>
      <p v-if="isLoading" class="text-xs text-slate-400">Loading...</p>

      <template v-else-if="totalCount === 0">
        <div class="rounded-lg border border-dashed border-slate-200 px-4 py-8 text-center text-xs text-slate-400">
          No business owners have registered yet.
        </div>
      </template>

      <template v-else>
        <!-- Search + filter -->
        <div class="mb-4 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div class="relative flex-1">
            <svg class="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="11" cy="11" r="7" />
              <path d="m20 20-3.5-3.5" />
            </svg>
            <input
              v-model="searchQuery"
              type="text"
              placeholder="Search by name or business..."
              class="w-full rounded-lg border border-slate-200 py-2 pl-9 pr-3 text-sm outline-none focus:border-amber-500"
            />
          </div>
          <div class="flex shrink-0 gap-1.5">
            <button
              v-for="opt in [{ key: 'all', label: 'All' }, { key: 'active', label: 'Active' }, { key: 'pending', label: 'Pending' }]"
              :key="opt.key"
              class="rounded-lg px-3 py-2 text-xs font-medium transition"
              :class="statusFilter === opt.key ? 'bg-navy-950 text-white' : 'bg-slate-50 text-slate-600 hover:bg-slate-100'"
              @click="statusFilter = opt.key"
            >
              {{ opt.label }}
            </button>
          </div>
        </div>

        <div v-if="filteredOwners.length === 0" class="rounded-lg border border-dashed border-slate-200 px-4 py-8 text-center text-xs text-slate-400">
          No business owners match "{{ searchQuery }}".
        </div>

        <ul v-else class="divide-y divide-slate-100">
          <li v-for="owner in filteredOwners" :key="owner.id" class="flex items-center justify-between py-3">
            <div class="min-w-0">
              <p class="truncate text-sm font-medium text-navy-950">{{ owner.username }}</p>
              <p class="truncate text-xs text-slate-500">{{ owner.tenant_id }}</p>
            </div>
            <div class="flex shrink-0 items-center gap-3">
              <span
                class="rounded-full px-2 py-0.5 text-[11px] font-medium"
                :class="owner.is_active ? 'bg-emerald-50 text-emerald-600' : 'bg-slate-100 text-slate-500'"
              >
                {{ owner.is_active ? "Active" : "Pending" }}
              </span>
              <button
                :disabled="pendingId === owner.id"
                class="rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-navy-900 hover:border-amber-500 disabled:opacity-50"
                @click="toggle(owner)"
              >
                {{ owner.is_active ? "Deactivate" : "Activate" }}
              </button>
            </div>
          </li>
        </ul>

        <p v-if="filteredOwners.length > 0" class="mt-3 text-center text-[11px] text-slate-400">
          Showing {{ filteredOwners.length }} of {{ totalCount }}
        </p>
      </template>
    </div>

    <ConfirmDialog
      :open="!!pendingDeactivate"
      title="Deactivate this business?"
      :message="pendingDeactivate ? `${pendingDeactivate.username}'s chatbot will stop working immediately on their website.` : ''"
      confirm-label="Deactivate"
      danger
      @confirm="confirmDeactivate"
      @cancel="pendingDeactivate = null"
    />

    <ConfirmDialog
      :open="showLogoutConfirm"
      title="Log out?"
      message="You'll need to sign in again to manage business owners."
      confirm-label="Log out"
      danger
      @confirm="confirmLogout"
      @cancel="showLogoutConfirm = false"
    />
  </div>
</template>