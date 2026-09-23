<script setup>
import { computed, onMounted, ref } from "vue";
import { useAuthStore } from "../stores/auth";
import { api, ApiError } from "../services/api";
import { useToast } from "../composables/useToast";
import ConfirmDialog from "./ConfirmDialog.vue";

const auth = useAuthStore();
const toast = useToast();

const domainsText = ref("");
const savedDomains = ref([]);
const requireDomains = ref(false);
const isLoading = ref(true);
const isSaving = ref(false);
const isRotating = ref(false);
const error = ref(null);
const showRotateConfirm = ref(false);

const isRestricted = computed(() => savedDomains.value.length > 0);

// One website per line; commas also work if someone pastes a comma-separated list.
function parseLines(text) {
  return text
    .split(/[\n,]+/)
    .map((s) => s.trim())
    .filter(Boolean);
}

async function load() {
  isLoading.value = true;
  error.value = null;
  try {
    const data = await api.getEmbedSettings(auth.token);
    savedDomains.value = data.allowed_domains || [];
    domainsText.value = savedDomains.value.join("\n");
    requireDomains.value = !!data.restriction_required;
    // Keep the embed snippet on the dashboard in sync with the real key
    // (it may have been regenerated from another device/browser).
    if (data.api_key && data.api_key !== auth.apiKey) auth.setApiKey(data.api_key);
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : "Couldn't load your website settings.";
  } finally {
    isLoading.value = false;
  }
}

async function save() {
  isSaving.value = true;
  error.value = null;
  try {
    const data = await api.updateAllowedDomains(auth.token, parseLines(domainsText.value));
    savedDomains.value = data.allowed_domains;
    domainsText.value = data.allowed_domains.join("\n");
    toast.success(
      data.allowed_domains.length
        ? "Allowed websites saved."
        : "Restriction removed - your widget can now be used on any website."
    );
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : "Couldn't save the websites.";
  } finally {
    isSaving.value = false;
  }
}

async function rotateKey() {
  showRotateConfirm.value = false;
  isRotating.value = true;
  try {
    const data = await api.regenerateApiKey(auth.token);
    auth.setApiKey(data.api_key);
    toast.success("New API key generated. Copy the updated embed snippet onto your website.");
  } catch (err) {
    toast.error(err instanceof ApiError ? err.message : "Couldn't regenerate the key.");
  } finally {
    isRotating.value = false;
  }
}

onMounted(load);
</script>

<template>
  <div class="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-slate-100">
    <div class="flex items-start justify-between gap-3">
      <div>
        <h2 class="text-sm font-semibold text-navy-950">Allowed websites</h2>
        <p class="mt-1 text-xs text-slate-500">
          Your chat widget only works on the websites listed here. If someone copies your embed code
          onto another site, it won't load.
        </p>
      </div>
      <span
        v-if="!isLoading"
        class="shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium"
        :class="isRestricted ? 'bg-emerald-50 text-emerald-600' : 'bg-amber-50 text-amber-800'"
      >
        {{ isRestricted ? "Restricted" : "Not restricted" }}
      </span>
    </div>

    <p v-if="isLoading" class="mt-3 text-xs text-slate-400">Loading...</p>

    <template v-else>
      <p v-if="!isRestricted" class="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800">
        <template v-if="requireDomains">
          No websites are listed yet, so your widget is blocked everywhere. Add your website below.
        </template>
        <template v-else>
          No websites are listed yet, so anyone who copies your embed code can use your chatbot on their
          own site. Add your website below to lock it down.
        </template>
      </p>

      <form class="mt-3" @submit.prevent="save">
        <label class="mb-1 block text-xs font-medium text-slate-600">Websites (one per line)</label>
        <textarea
          v-model="domainsText"
          rows="4"
          spellcheck="false"
          :placeholder="'mysite.com\nshop.mysite.com'"
          class="w-full rounded-lg border border-slate-200 px-3 py-2 font-mono text-xs outline-none focus:border-amber-500"
        />
        <p class="mt-1 text-[11px] text-slate-400">
          "mysite.com" also allows www.mysite.com and other subdomains. Add every site that shows your
          widget, or it will disappear there. Add "localhost" to test on your own computer.
        </p>
        <button
          type="submit"
          :disabled="isSaving"
          class="mt-3 rounded-lg bg-navy-950 px-4 py-2 text-xs font-medium text-white hover:bg-navy-900 disabled:opacity-60"
        >
          {{ isSaving ? "Saving..." : "Save websites" }}
        </button>
      </form>

      <p v-if="error" class="mt-2 rounded-lg bg-rose-50 px-3 py-2 text-xs text-rose-600">{{ error }}</p>

      <div class="mt-5 border-t border-slate-100 pt-4">
        <h3 class="text-xs font-semibold text-navy-950">Regenerate API key</h3>
        <p class="mt-1 text-xs text-slate-500">
          If your key was copied or misused, generate a new one. The old key stops working immediately, so
          you'll need to paste the new embed snippet onto your website.
        </p>
        <button
          :disabled="isRotating"
          class="mt-3 rounded-lg border border-rose-300 px-3 py-2 text-xs font-medium text-rose-600 hover:bg-rose-50 disabled:opacity-60"
          @click="showRotateConfirm = true"
        >
          {{ isRotating ? "Generating..." : "Regenerate API key" }}
        </button>
      </div>
    </template>

    <ConfirmDialog
      :open="showRotateConfirm"
      title="Regenerate API key?"
      message="Your current key stops working immediately. Your chat widget will stop working on your website until you paste the new embed snippet."
      confirm-label="Regenerate"
      danger
      @confirm="rotateKey"
      @cancel="showRotateConfirm = false"
    />
  </div>
</template>