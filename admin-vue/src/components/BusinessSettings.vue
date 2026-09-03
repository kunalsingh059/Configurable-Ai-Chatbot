<script setup>
import { onMounted, ref } from "vue";
import { useAuthStore } from "../stores/auth";
import { api, ApiError } from "../services/api";
import { useToast } from "../composables/useToast";

const auth = useAuthStore();
const toast = useToast();

const name = ref(auth.businessName || "");
const isLoading = ref(true);
const isSaving = ref(false);
const error = ref(null);

async function load() {
  try {
    const data = await api.getBusinessName(auth.token);
    name.value = data.business_name || "";
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : "Couldn't load your business name.";
  } finally {
    isLoading.value = false;
  }
}

async function save() {
  if (!name.value.trim()) return;
  isSaving.value = true;
  error.value = null;
  try {
    const data = await api.updateBusinessName(auth.token, name.value.trim());
    auth.setBusinessName(data.business_name);
    toast.success("Widget name updated - it'll show up next time the widget loads.");
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : "Couldn't save the name.";
  } finally {
    isSaving.value = false;
  }
}

onMounted(load);
</script>

<template>
  <div class="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-slate-100">
    <h2 class="text-sm font-semibold text-navy-950">Widget name</h2>
    <p class="mt-1 text-xs text-slate-500">
      Shown in your chat widget's header instead of the default "Support Assistant".
    </p>

    <p v-if="isLoading" class="mt-3 text-xs text-slate-400">Loading...</p>

    <form v-else class="mt-3 flex items-center gap-2" @submit.prevent="save">
      <input
        v-model="name"
        type="text"
        required
        placeholder="e.g. Life Secure Pathology Assistant"
        class="flex-1 rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-amber-500"
      />
      <button
        type="submit"
        :disabled="isSaving"
        class="shrink-0 rounded-lg bg-navy-950 px-4 py-2 text-xs font-medium text-white hover:bg-navy-900 disabled:opacity-60"
      >
        {{ isSaving ? "Saving..." : "Save" }}
      </button>
    </form>

    <p v-if="error" class="mt-2 rounded-lg bg-rose-50 px-3 py-2 text-xs text-rose-600">{{ error }}</p>
  </div>
</template>
