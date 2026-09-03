<script setup>
import { onMounted, ref } from "vue";
import { useAuthStore } from "../stores/auth";
import { api, ApiError } from "../services/api";
import { useToast } from "../composables/useToast";
import ConfirmDialog from "./ConfirmDialog.vue";

const auth = useAuthStore();
const toast = useToast();

const documents = ref([]);
const isLoading = ref(true);
const isUploading = ref(false);
const error = ref(null);
const fileInput = ref(null);
const pendingDelete = ref(null);

async function load() {
  isLoading.value = true;
  error.value = null;
  try {
    documents.value = await api.listDocuments(auth.token);
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : "Couldn't load documents.";
  } finally {
    isLoading.value = false;
  }
}

async function onFileChange(e) {
  const file = e.target.files[0];
  if (!file) return;
  isUploading.value = true;
  error.value = null;
  try {
    await api.uploadDocument(auth.token, file);
    toast.success(`"${file.name}" uploaded.`);
    await load();
  } catch (err) {
    toast.error(err instanceof ApiError ? err.message : "Upload failed.");
  } finally {
    isUploading.value = false;
    if (fileInput.value) fileInput.value.value = "";
  }
}

function askDelete(doc) {
  pendingDelete.value = doc;
}

async function confirmDelete() {
  const doc = pendingDelete.value;
  pendingDelete.value = null;
  try {
    await api.deleteDocument(auth.token, doc.id);
    documents.value = documents.value.filter((d) => d.id !== doc.id);
    toast.success(`"${doc.name}" deleted.`);
  } catch (err) {
    toast.error(err instanceof ApiError ? err.message : "Couldn't delete the document.");
  }
}

onMounted(load);
</script>

<template>
  <div class="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-slate-100">
    <div class="mb-4 flex items-center justify-between">
      <div>
        <h2 class="text-sm font-semibold text-navy-950">Documents</h2>
        <p class="text-xs text-slate-500">FAQs, policies, or menus your assistant can reference.</p>
      </div>
      <label class="cursor-pointer rounded-lg bg-navy-950 px-3 py-2 text-xs font-medium text-white hover:bg-navy-900">
        {{ isUploading ? "Uploading..." : "Upload" }}
        <input ref="fileInput" type="file" class="hidden" :disabled="isUploading" @change="onFileChange" />
      </label>
    </div>

    <p v-if="error" class="mb-3 rounded-lg bg-rose-50 px-3 py-2 text-xs text-rose-600">{{ error }}</p>
    <p v-if="isLoading" class="text-xs text-slate-400">Loading...</p>

    <div v-else-if="documents.length === 0" class="rounded-lg border border-dashed border-slate-200 px-4 py-8 text-center text-xs text-slate-400">
      No documents yet.
    </div>

    <ul v-else class="divide-y divide-slate-100">
      <li v-for="doc in documents" :key="doc.id" class="flex items-center justify-between py-3">
        <p class="truncate text-sm font-medium text-navy-950">{{ doc.name }}</p>
        <button
          class="shrink-0 rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-rose-600 hover:border-rose-300"
          @click="askDelete(doc)"
        >
          Delete
        </button>
      </li>
    </ul>

    <ConfirmDialog
      :open="!!pendingDelete"
      title="Delete this document?"
      :message="pendingDelete ? `Deleting ${pendingDelete.name} can't be undone.` : ''"
      confirm-label="Delete"
      danger
      @confirm="confirmDelete"
      @cancel="pendingDelete = null"
    />
  </div>
</template>
