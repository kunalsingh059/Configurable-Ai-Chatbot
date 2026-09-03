<script setup>
import { onMounted, ref } from "vue";
import { useAuthStore } from "../stores/auth";
import { api, ApiError } from "../services/api";
import { useToast } from "../composables/useToast";
import ConfirmDialog from "./ConfirmDialog.vue";

const auth = useAuthStore();
const toast = useToast();

const tools = ref([]);
const isLoading = ref(true);
const error = ref(null);
const showForm = ref(false);
const isSubmitting = ref(false);
const editingId = ref(null); // null = creating, otherwise the tool.id being edited

const emptyForm = () => ({
  name: "",
  description: "",
  method: "GET",
  url_template: "",
  params_schema: '{\n  "type": "object",\n  "properties": {},\n  "required": []\n}',
});
const form = ref(emptyForm());
const formError = ref(null);

// Delete confirmation state
const pendingDelete = ref(null); // the tool object awaiting confirmation

async function load() {
  isLoading.value = true;
  error.value = null;
  try {
    tools.value = await api.listTools(auth.token);
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : "Couldn't load tools.";
  } finally {
    isLoading.value = false;
  }
}

function openCreate() {
  editingId.value = null;
  form.value = emptyForm();
  formError.value = null;
  showForm.value = true;
}

function openEdit(tool) {
  editingId.value = tool.id;
  form.value = {
    name: tool.name,
    description: tool.description,
    method: tool.method,
    url_template: tool.url_template,
    params_schema: JSON.stringify(tool.params_schema, null, 2),
  };
  formError.value = null;
  showForm.value = true;
}

async function submitForm() {
  formError.value = null;
  let parsedSchema;
  try {
    parsedSchema = JSON.parse(form.value.params_schema);
  } catch {
    formError.value = "Params schema must be valid JSON.";
    return;
  }

  const payload = {
    name: form.value.name,
    description: form.value.description,
    method: form.value.method,
    url_template: form.value.url_template,
    headers: {},
    params_schema: parsedSchema,
  };

  isSubmitting.value = true;
  try {
    if (editingId.value) {
      await api.updateTool(auth.token, editingId.value, payload);
      toast.success(`"${form.value.name}" updated.`);
    } else {
      await api.createTool(auth.token, payload);
      toast.success(`"${form.value.name}" added.`);
    }
    showForm.value = false;
    await load();
  } catch (err) {
    formError.value = err instanceof ApiError ? err.message : "Couldn't save the tool.";
  } finally {
    isSubmitting.value = false;
  }
}

function askDelete(tool) {
  pendingDelete.value = tool;
}

async function confirmDelete() {
  const tool = pendingDelete.value;
  pendingDelete.value = null;
  try {
    await api.deleteTool(auth.token, tool.id);
    tools.value = tools.value.filter((t) => t.id !== tool.id);
    toast.success(`"${tool.name}" deleted.`);
  } catch (err) {
    toast.error(err instanceof ApiError ? err.message : "Couldn't delete the tool.");
  }
}

onMounted(load);
</script>

<template>
  <div class="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-slate-100">
    <div class="mb-4 flex items-center justify-between">
      <div>
        <h2 class="text-sm font-semibold text-navy-950">Tools</h2>
        <p class="text-xs text-slate-500">APIs your assistant can call to answer questions.</p>
      </div>
      <button
        class="rounded-lg bg-navy-950 px-3 py-2 text-xs font-medium text-white hover:bg-navy-900"
        @click="openCreate"
      >
        Add tool
      </button>
    </div>

    <p v-if="error" class="mb-3 rounded-lg bg-rose-50 px-3 py-2 text-xs text-rose-600">{{ error }}</p>
    <p v-if="isLoading" class="text-xs text-slate-400">Loading...</p>

    <div v-else-if="tools.length === 0" class="rounded-lg border border-dashed border-slate-200 px-4 py-8 text-center text-xs text-slate-400">
      No tools yet. Add one so your assistant can look up real data.
    </div>

    <ul v-else class="divide-y divide-slate-100">
      <li v-for="tool in tools" :key="tool.id" class="flex items-center justify-between py-3">
        <div class="min-w-0">
          <p class="truncate text-sm font-medium text-navy-950">{{ tool.name }}</p>
          <p class="truncate text-xs text-slate-500">{{ tool.method }} {{ tool.url_template }}</p>
        </div>
        <div class="flex shrink-0 items-center gap-2">
          <button
            class="rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-navy-900 hover:border-amber-500"
            @click="openEdit(tool)"
          >
            Edit
          </button>
          <button
            class="rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-rose-600 hover:border-rose-300"
            @click="askDelete(tool)"
          >
            Delete
          </button>
        </div>
      </li>
    </ul>

    <!-- Create / edit tool modal -->
    <div v-if="showForm" class="fixed inset-0 z-10 flex items-center justify-center bg-black/40 px-4">
      <div class="w-full max-w-md rounded-2xl bg-white p-5 shadow-lg">
        <h3 class="mb-4 text-sm font-semibold text-navy-950">
          {{ editingId ? "Edit tool" : "Add tool" }}
        </h3>
        <form class="space-y-3" @submit.prevent="submitForm">
          <div>
            <label class="mb-1 block text-xs font-medium text-slate-600">Name</label>
            <input v-model="form.name" required class="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-amber-500" />
          </div>
          <div>
            <label class="mb-1 block text-xs font-medium text-slate-600">Description (tells the AI when to use it)</label>
            <textarea v-model="form.description" required rows="2" class="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-amber-500"></textarea>
          </div>
          <div class="grid grid-cols-3 gap-2">
            <div>
              <label class="mb-1 block text-xs font-medium text-slate-600">Method</label>
              <select v-model="form.method" class="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-amber-500">
                <option v-for="m in ['GET', 'POST', 'PUT', 'DELETE']" :key="m">{{ m }}</option>
              </select>
            </div>
            <div class="col-span-2">
              <label class="mb-1 block text-xs font-medium text-slate-600">URL template</label>
              <input v-model="form.url_template" required placeholder="https://api.example.com/products/{id}" class="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-amber-500" />
            </div>
          </div>
          <div>
            <label class="mb-1 block text-xs font-medium text-slate-600">Params schema (JSON)</label>
            <textarea v-model="form.params_schema" rows="5" class="w-full rounded-lg border border-slate-200 px-3 py-2 font-mono text-xs outline-none focus:border-amber-500"></textarea>
          </div>

          <p v-if="formError" class="rounded-lg bg-rose-50 px-3 py-2 text-xs text-rose-600">{{ formError }}</p>

          <div class="flex justify-end gap-2 pt-2">
            <button type="button" class="rounded-lg px-3 py-2 text-xs font-medium text-slate-600" @click="showForm = false">Cancel</button>
            <button type="submit" :disabled="isSubmitting" class="rounded-lg bg-navy-950 px-3 py-2 text-xs font-medium text-white hover:bg-navy-900 disabled:opacity-60">
              {{ isSubmitting ? "Saving..." : editingId ? "Save changes" : "Save tool" }}
            </button>
          </div>
        </form>
      </div>
    </div>

    <ConfirmDialog
      :open="!!pendingDelete"
      title="Delete this tool?"
      :message="pendingDelete ? `Deleting ${pendingDelete.name} can't be undone.` : ''"
      confirm-label="Delete"
      danger
      @confirm="confirmDelete"
      @cancel="pendingDelete = null"
    />
  </div>
</template>
