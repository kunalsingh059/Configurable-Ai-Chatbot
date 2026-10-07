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
  headers: "{}",
  existingHeaderKeys: [],
  params_schema: '{\n  "type": "object",\n  "properties": {},\n  "required": []\n}',
  response_fields: "",
});
const form = ref(emptyForm());
const formError = ref(null);

// "Test tool" panel state - lets an admin fire the live request with sample
// params right from the form, before saving, so a broken URL/header/param
// shows up here instead of in front of a real customer.
const testParams = ref("{}");
const isTesting = ref(false);
const testError = ref(null);
const testResult = ref(null); // pretty-printed JSON string, or null if not run yet
const testPreview = ref(null); // exact string the LLM would receive, after field filtering + truncation

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

function resetTestPanel() {
  testParams.value = "{}";
  testError.value = null;
  testResult.value = null;
  testPreview.value = null;
}

function openCreate() {
  editingId.value = null;
  form.value = emptyForm();
  formError.value = null;
  resetTestPanel();
  showForm.value = true;
}

function openEdit(tool) {
  editingId.value = tool.id;
  form.value = {
    name: tool.name,
    description: tool.description,
    method: tool.method,
    url_template: tool.url_template,
    // Headers are never sent back by the API once saved (see backend
    // serialize_tool) - only header_keys (names, no values) are, so this
    // starts blank on edit. Leaving it blank on save keeps the existing
    // encrypted headers untouched; typing new ones replaces them entirely.
    headers: "{}",
    existingHeaderKeys: tool.header_keys || [],
    params_schema: JSON.stringify(tool.params_schema, null, 2),
    response_fields: (tool.response_fields || []).join(", "),
  };
  formError.value = null;
  resetTestPanel();
  showForm.value = true;
}

// Turns "product_name, ingredients_text, nutriscore_grade" into a clean
// array, dropping stray commas/whitespace so a trailing comma or extra
// space doesn't turn into an empty/blank field name.
function parseResponseFields(text) {
  return text
    .split(",")
    .map((f) => f.trim())
    .filter(Boolean);
}

// Shared by submitForm and runTest - both need method/url/headers parsed
// the same way, and both should fail the same way on bad JSON.
function parseFormBasics() {
  let headers;
  try {
    headers = JSON.parse(form.value.headers || "{}");
  } catch {
    throw new Error("Headers must be valid JSON.");
  }
  if (!form.value.url_template.trim()) {
    throw new Error("URL template is required before testing.");
  }
  return { method: form.value.method, url_template: form.value.url_template, headers };
}

async function runTest() {
  testError.value = null;
  testResult.value = null;
  testPreview.value = null;

  let basics;
  let params;
  try {
    basics = parseFormBasics();
  } catch (err) {
    testError.value = err.message;
    return;
  }
  try {
    params = JSON.parse(testParams.value || "{}");
  } catch {
    testError.value = "Sample params must be valid JSON.";
    return;
  }

  isTesting.value = true;
  try {
    const { result, llm_preview } = await api.testTool(auth.token, {
      ...basics,
      params,
      response_fields: parseResponseFields(form.value.response_fields),
    });
    testResult.value = JSON.stringify(result, null, 2);
    testPreview.value = llm_preview;
    if (result && result.error) {
      // Still a "successful" HTTP round-trip through our own API, but the
      // live call itself failed (bad URL, blocked address, upstream 4xx/
      // 5xx) - surface that distinctly from a genuine network/auth error.
      testError.value = result.error;
    }
  } catch (err) {
    testError.value = err instanceof ApiError ? err.message : "Couldn't run the test.";
  } finally {
    isTesting.value = false;
  }
}

async function submitForm() {
  formError.value = null;
  let basics;
  try {
    basics = parseFormBasics();
  } catch (err) {
    formError.value = err.message;
    return;
  }

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
    method: basics.method,
    url_template: basics.url_template,
    headers: basics.headers,
    params_schema: parsedSchema,
    response_fields: parseResponseFields(form.value.response_fields),
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
  <div class="rounded-2xl bg-white p-4 sm:p-5 shadow-sm ring-1 ring-slate-100">
    <div class="mb-4 flex items-center justify-between gap-3">
      <div class="min-w-0">
        <h2 class="text-sm font-semibold text-navy-950">Tools</h2>
        <p class="text-xs text-slate-500">Live APIs your assistant can call to answer questions.</p>
      </div>
      <button
        class="shrink-0 rounded-lg bg-navy-950 px-3 py-2 text-xs font-medium text-white hover:bg-navy-900"
        @click="openCreate"
      >
        Add tool
      </button>
    </div>

    <p v-if="error" class="mb-3 rounded-lg bg-rose-50 px-3 py-2 text-xs text-rose-600">{{ error }}</p>
    <p v-if="isLoading" class="text-xs text-slate-400">Loading...</p>

    <div v-else-if="tools.length === 0" class="rounded-lg border border-dashed border-slate-200 px-4 py-8 text-center text-xs text-slate-400">
      No tools yet. Add one so your assistant can look up real, live data.
    </div>

    <ul v-else class="divide-y divide-slate-100">
      <li v-for="tool in tools" :key="tool.id" class="flex flex-col gap-2.5 sm:flex-row sm:items-center sm:justify-between py-3">
        <div class="min-w-0 flex-1">
          <p class="truncate text-sm font-medium text-navy-950">{{ tool.name }}</p>
          <p class="truncate text-xs font-mono text-slate-500">{{ tool.method }} {{ tool.url_template }}</p>
          <p v-if="tool.response_fields && tool.response_fields.length" class="truncate text-[11px] text-amber-600">
            Fields: {{ tool.response_fields.join(", ") }}
          </p>
        </div>
        <div class="flex shrink-0 items-center gap-2 self-start sm:self-auto">
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
    <div v-if="showForm" class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-3 sm:p-4 overflow-y-auto">
      <div class="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-2xl bg-white p-4 sm:p-6 shadow-xl">
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
          <div class="grid grid-cols-1 sm:grid-cols-3 gap-2">
            <div class="sm:col-span-1">
              <label class="mb-1 block text-xs font-medium text-slate-600">Method</label>
              <select v-model="form.method" class="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-amber-500">
                <option v-for="m in ['GET', 'POST', 'PUT', 'DELETE']" :key="m">{{ m }}</option>
              </select>
            </div>
            <div class="sm:col-span-2">
              <label class="mb-1 block text-xs font-medium text-slate-600">URL template</label>
              <input v-model="form.url_template" required placeholder="https://api.example.com/products/{id}" class="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-amber-500" />
            </div>
          </div>
          <p class="-mt-2 text-[11px] text-slate-400">
            Wrap any part the AI should fill in with <code class="rounded bg-slate-100 px-1">{curly braces}</code>, e.g. <code class="rounded bg-slate-100 px-1">{barcode}</code>.
          </p>

          <div>
            <label class="mb-1 block text-xs font-medium text-slate-600">
              Headers (JSON) - for an API key or auth token, e.g. <code class="rounded bg-slate-100 px-1 font-normal">{"\u0022Authorization\u0022: \u0022Bearer sk_...\u0022"}</code>
            </label>
            <textarea v-model="form.headers" rows="2" placeholder="{}" class="w-full rounded-lg border border-slate-200 px-3 py-2 font-mono text-xs outline-none focus:border-amber-500"></textarea>
            <p v-if="editingId && form.existingHeaderKeys.length" class="mt-1 text-[11px] text-slate-400">
              Currently set: {{ form.existingHeaderKeys.join(", ") }} (values are hidden for security - leave this blank to keep them unchanged, or enter new headers to replace them entirely).
            </p>
          </div>

          <div>
            <label class="mb-1 block text-xs font-medium text-slate-600">Params schema (JSON) - tells the AI what to fill in</label>
            <textarea v-model="form.params_schema" rows="5" class="w-full rounded-lg border border-slate-200 px-3 py-2 font-mono text-xs outline-none focus:border-amber-500"></textarea>
          </div>

          <div>
            <label class="mb-1 block text-xs font-medium text-slate-600">
              Only send the AI these fields (optional, comma-separated)
            </label>
            <input
              v-model="form.response_fields"
              placeholder="e.g. product_name, ingredients_text, nutriscore_grade"
              class="w-full rounded-lg border border-slate-200 px-3 py-2 font-mono text-xs outline-none focus:border-amber-500"
            />
            <p class="mt-1 text-[11px] text-slate-400">
              Live APIs often return far more than the AI needs. Leave blank to send the whole response (trimmed if it's very large); list specific top-level fields to keep replies faster and more focused.
            </p>
          </div>

          <p v-if="formError" class="rounded-lg bg-rose-50 px-3 py-2 text-xs text-rose-600">{{ formError }}</p>

          <!-- Test panel: runs the exact same request the AI would make -->
          <div class="rounded-xl border border-slate-200 p-3">
            <p class="mb-2 text-xs font-medium text-slate-600">Test this tool live</p>
            <div class="flex flex-col sm:flex-row items-stretch sm:items-start gap-2">
              <textarea
                v-model="testParams"
                rows="2"
                placeholder='{"barcode": "3017624010701"}'
                class="w-full sm:flex-1 rounded-lg border border-slate-200 px-3 py-2 font-mono text-xs outline-none focus:border-amber-500"
              ></textarea>
              <button
                type="button"
                :disabled="isTesting"
                class="w-full sm:w-auto shrink-0 rounded-lg border border-slate-200 px-3.5 py-2 text-xs font-medium text-navy-900 hover:border-amber-500 disabled:opacity-60 text-center"
                @click="runTest"
              >
                {{ isTesting ? "Running..." : "Run test" }}
              </button>
            </div>
            <p v-if="testError" class="mt-2 rounded-lg bg-rose-50 px-3 py-2 text-xs text-rose-600">{{ testError }}</p>
            <div v-if="testResult" class="mt-2 space-y-2">
              <div>
                <p class="mb-1 text-[11px] font-medium text-slate-500">Raw result</p>
                <pre class="max-h-40 overflow-auto rounded-lg bg-slate-50 px-3 py-2 text-[11px] leading-relaxed text-navy-900">{{ testResult }}</pre>
              </div>
              <div>
                <p class="mb-1 text-[11px] font-medium text-slate-500">What the AI actually receives</p>
                <pre class="max-h-40 overflow-auto rounded-lg bg-amber-50 px-3 py-2 text-[11px] leading-relaxed text-navy-900">{{ testPreview }}</pre>
              </div>
            </div>
          </div>

          <div class="flex flex-col-reverse sm:flex-row sm:justify-end gap-2 pt-2">
            <button type="button" class="w-full sm:w-auto rounded-lg px-4 py-2.5 text-xs font-medium text-slate-600 hover:bg-slate-50 text-center" @click="showForm = false">Cancel</button>
            <button type="submit" :disabled="isSubmitting" class="w-full sm:w-auto rounded-lg bg-navy-950 px-4 py-2.5 text-xs font-medium text-white hover:bg-navy-900 disabled:opacity-60 text-center">
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