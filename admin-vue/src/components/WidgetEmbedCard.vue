<script setup>
import { computed, ref } from "vue";
import { useToast } from "../composables/useToast";

const props = defineProps({
  apiKey: { type: String, required: true },
});

const toast = useToast();

// Base URL where the built widget bundle is hosted - update this once you
// deploy widget-vue's `dist/` somewhere (FastAPI static files, CDN, etc).
const WIDGET_URL = import.meta.env.VITE_WIDGET_URL || "https://yourdomain.com/widget/index.html";

const embedSnippet = computed(
  () =>
    `<script\n  src="${WIDGET_URL.replace('/index.html', '')}/embed.js"\n  data-api-key="${props.apiKey}"\n  data-widget-url="${WIDGET_URL.replace('/index.html', '')}"\n><\/script>`
);

const copiedKey = ref(false);
const copiedSnippet = ref(false);
const copyError = ref(false);

// Copies `text` to the clipboard, falling back to the old execCommand trick
// if navigator.clipboard is unavailable/denied. Returns true/false so the
// caller decides what UI feedback to show - kept separate from the refs so
// this function is never invoked directly from a template (see the two
// wrapper functions below for why that matters).
async function copyText(text) {
  try {
    if (!navigator.clipboard) throw new Error("Clipboard API unavailable");
    await navigator.clipboard.writeText(text);
    return true;
  } catch (err) {
    console.error("Clipboard copy failed, using fallback:", err);
    try {
      const textarea = document.createElement("textarea");
      textarea.value = text;
      textarea.style.position = "fixed";
      textarea.style.opacity = "0";
      document.body.appendChild(textarea);
      textarea.focus();
      textarea.select();
      document.execCommand("copy");
      document.body.removeChild(textarea);
      return true;
    } catch (fallbackErr) {
      console.error("Fallback copy also failed:", fallbackErr);
      return false;
    }
  }
}

// IMPORTANT: each button calls one of these two functions by name
// (@click="copyApiKey"), never something like @click="copy(apiKey, copiedKey)".
// Vue auto-unwraps a ref to its plain value when it's referenced inside a
// template expression - including when it's passed as a function argument -
// so a ref passed that way arrives as a plain boolean, not the ref object,
// and `flag.value = true` inside the function would throw. Reading/writing
// copiedKey.value here, inside <script setup> instead of the template,
// avoids that entirely.
async function copyApiKey() {
  copyError.value = false;
  const success = await copyText(props.apiKey);
  if (!success) {
    copyError.value = true;
    toast.error("Couldn't copy - please select and copy manually.");
    setTimeout(() => (copyError.value = false), 2000);
    return;
  }
  copiedKey.value = true;
  toast.success("API key copied to clipboard.");
  setTimeout(() => (copiedKey.value = false), 1500);
}

async function copySnippet() {
  copyError.value = false;
  const success = await copyText(embedSnippet.value);
  if (!success) {
    copyError.value = true;
    toast.error("Couldn't copy - please select and copy manually.");
    setTimeout(() => (copyError.value = false), 2000);
    return;
  }
  copiedSnippet.value = true;
  toast.success("Embed snippet copied to clipboard.");
  setTimeout(() => (copiedSnippet.value = false), 1500);
}
</script>

<template>
  <div class="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-slate-100">
    <h2 class="text-sm font-semibold text-navy-950">Your widget</h2>
    <p class="mt-1 text-xs text-slate-500">
      This key identifies your business to the chat widget. Don't share it publicly outside your own site.
    </p>

    <div class="mt-4">
      <label class="mb-1 block text-xs font-medium text-slate-600">API key</label>
      <div class="flex items-center gap-2">
        <code class="flex-1 truncate rounded-lg bg-slate-50 px-3 py-2 text-xs text-navy-900 ring-1 ring-slate-200">
          {{ apiKey }}
        </code>
        <button
          class="flex shrink-0 items-center gap-1.5 rounded-lg border px-3 py-2 text-xs font-medium transition"
          :class="copiedKey
            ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
            : 'border-slate-200 text-navy-900 hover:border-amber-500'"
          @click="copyApiKey"
        >
          <svg v-if="copiedKey" class="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M20 6 9 17l-5-5" />
          </svg>
          {{ copiedKey ? "Copied!" : "Copy" }}
        </button>
      </div>
    </div>

    <div class="mt-4">
      <label class="mb-1 block text-xs font-medium text-slate-600">Embed snippet</label>
      <pre class="overflow-x-auto rounded-lg bg-navy-950 px-3 py-3 text-[11px] leading-relaxed text-white/90"><code>{{ embedSnippet }}</code></pre>
      <button
        class="mt-2 flex items-center gap-1.5 rounded-lg border px-3 py-2 text-xs font-medium transition"
        :class="copiedSnippet
          ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
          : 'border-slate-200 text-navy-900 hover:border-amber-500'"
        @click="copySnippet"
      >
        <svg v-if="copiedSnippet" class="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M20 6 9 17l-5-5" />
        </svg>
        {{ copiedSnippet ? "Copied!" : "Copy snippet" }}
      </button>
    </div>

    <p v-if="copyError" class="mt-2 text-xs text-rose-600">
      Couldn't copy automatically - please select and copy the text manually.
    </p>
  </div>
</template>