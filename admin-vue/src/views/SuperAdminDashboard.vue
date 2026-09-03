<script setup>
import { onMounted, ref } from "vue";
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

async function toggle(owner) {
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

    <div class="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-slate-100">
      <p v-if="error" class="mb-3 rounded-lg bg-rose-50 px-3 py-2 text-xs text-rose-600">{{ error }}</p>
      <p v-if="isLoading" class="text-xs text-slate-400">Loading...</p>

      <div v-else-if="owners.length === 0" class="rounded-lg border border-dashed border-slate-200 px-4 py-8 text-center text-xs text-slate-400">
        No business owners have registered yet.
      </div>

      <ul v-else class="divide-y divide-slate-100">
        <li v-for="owner in owners" :key="owner.id" class="flex items-center justify-between py-3">
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
    </div>

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
