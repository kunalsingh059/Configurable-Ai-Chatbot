<script setup>
import { computed, ref } from "vue";

const props = defineProps({
  apiKey: { type: String, required: true },
});

// Base URL where the built widget bundle is hosted - update this once you
// deploy widget-vue's `dist/` somewhere (FastAPI static files, CDN, etc).
const WIDGET_URL = import.meta.env.VITE_WIDGET_URL || "https://yourdomain.com/widget/index.html";

const embedSnippet = computed(
  () =>
    `<script\n  src="${WIDGET_URL.replace('/index.html', '')}/embed.js"\n  data-api-key="${props.apiKey}"\n  data-widget-url="${WIDGET_URL.replace('/index.html', '')}"\n><\/script>`
);

const copiedKey = ref(false);
const copiedSnippet = ref(false);

async function copy(text, flag) {
  await navigator.clipboard.writeText(text);
  flag.value = true;
  setTimeout(() => (flag.value = false), 1500);
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
          class="shrink-0 rounded-lg border border-slate-200 px-3 py-2 text-xs font-medium text-navy-900 hover:border-amber-500"
          @click="copy(apiKey, copiedKey)"
        >
          {{ copiedKey ? "Copied" : "Copy" }}
        </button>
      </div>
    </div>

    <div class="mt-4">
      <label class="mb-1 block text-xs font-medium text-slate-600">Embed snippet</label>
      <pre class="overflow-x-auto rounded-lg bg-navy-950 px-3 py-3 text-[11px] leading-relaxed text-white/90"><code>{{ embedSnippet }}</code></pre>
      <button
        class="mt-2 rounded-lg border border-slate-200 px-3 py-2 text-xs font-medium text-navy-900 hover:border-amber-500"
        @click="copy(embedSnippet, copiedSnippet)"
      >
        {{ copiedSnippet ? "Copied" : "Copy snippet" }}
      </button>
    </div>
  </div>
</template>