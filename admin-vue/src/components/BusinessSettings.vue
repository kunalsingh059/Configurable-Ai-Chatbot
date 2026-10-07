<script setup>
import { onMounted, ref } from "vue";
import { useAuthStore } from "../stores/auth";
import { api, ApiError } from "../services/api";
import { useToast } from "../composables/useToast";

const auth = useAuthStore();
const toast = useToast();

const botName = ref("");
const welcomeMessage = ref("");
const primaryColor = ref("#0b1224");
const avatarUrl = ref("");
const tone = ref("friendly");
const handoffEnabled = ref(false);
const quickReplies = ref([]);
const newQuickReply = ref("");

const isLoading = ref(true);
const isSaving = ref(false);
const error = ref(null);

async function load() {
  isLoading.value = true;
  error.value = null;
  try {
    const data = await api.getBotConfig(auth.token);
    botName.value = data.bot_name || auth.businessName || "";
    welcomeMessage.value = data.welcome_message || "";
    primaryColor.value = data.primary_color || "#0b1224";
    avatarUrl.value = data.avatar_url || "";
    tone.value = data.tone || "friendly";
    handoffEnabled.value = Boolean(data.handoff_enabled);
    quickReplies.value = Array.isArray(data.quick_replies) ? [...data.quick_replies] : [];
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) {
      // Backend route pending or fresh tenant: fall back gracefully to business name
      try {
        const fallback = await api.getBusinessName(auth.token);
        botName.value = fallback.business_name || auth.businessName || "";
      } catch {
        botName.value = auth.businessName || "";
      }
    } else {
      error.value = err instanceof ApiError ? err.message : "Couldn't load bot customization settings.";
    }
  } finally {
    isLoading.value = false;
  }
}

function addQuickReply() {
  const text = newQuickReply.value.trim();
  if (!text) return;
  if (quickReplies.value.length >= 6) {
    toast.error("You can add at most 6 quick replies.");
    return;
  }
  if (text.length > 40) {
    toast.error("Quick reply must be 40 characters or fewer.");
    return;
  }
  quickReplies.value.push(text);
  newQuickReply.value = "";
}

function removeQuickReply(index) {
  quickReplies.value.splice(index, 1);
}

async function save() {
  if (!botName.value.trim()) {
    error.value = "Bot name is required.";
    return;
  }
  if (avatarUrl.value.trim() && !avatarUrl.value.trim().startsWith("https://")) {
    error.value = "Avatar URL must start with https://";
    return;
  }

  isSaving.value = true;
  error.value = null;
  try {
    const payload = {
      bot_name: botName.value.trim(),
      welcome_message: welcomeMessage.value.trim() || null,
      primary_color: primaryColor.value,
      avatar_url: avatarUrl.value.trim() || null,
      tone: tone.value,
      quick_replies: quickReplies.value,
      handoff_enabled: handoffEnabled.value,
    };
    const updated = await api.updateBotConfig(auth.token, payload);
    auth.setBusinessName(updated.bot_name || payload.bot_name);
    toast.success("Chatbot settings updated successfully.");
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) {
      try {
        await api.updateBusinessName(auth.token, botName.value.trim());
        auth.setBusinessName(botName.value.trim());
        toast.success("Business name saved. Full bot settings will apply once backend deployment completes.");
      } catch (fallbackErr) {
        error.value = fallbackErr instanceof ApiError ? fallbackErr.message : "Couldn't save name.";
      }
    } else {
      error.value = err instanceof ApiError ? err.message : "Couldn't save bot settings.";
    }
  } finally {
    isSaving.value = false;
  }
}

onMounted(load);
</script>

<template>
  <div class="rounded-2xl bg-white p-4 sm:p-5 shadow-sm ring-1 ring-slate-100">
    <div class="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between border-b border-slate-100 pb-3">
      <div>
        <h2 class="text-sm font-semibold text-navy-950">Chatbot Appearance & Personality</h2>
        <p class="mt-0.5 text-xs text-slate-500">
          Customize how your assistant looks, greets visitors, and speaks.
        </p>
      </div>
      <span
        v-if="!isLoading"
        class="self-start sm:self-auto inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-medium"
        :style="{ backgroundColor: `${primaryColor}15`, color: primaryColor }"
      >
        <span class="h-2 w-2 rounded-full" :style="{ backgroundColor: primaryColor }" />
        Theme Active
      </span>
    </div>

    <p v-if="isLoading" class="mt-4 text-xs text-slate-400">Loading settings...</p>

    <form v-else class="mt-4 space-y-4" @submit.prevent="save">
      <!-- Bot Name & Tone Row -->
      <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div>
          <label class="block text-xs font-medium text-slate-700">Bot Display Name</label>
          <input
            v-model="botName"
            type="text"
            required
            maxlength="100"
            placeholder="e.g. Support Assistant"
            class="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-amber-500"
          />
          <p class="mt-1 text-[11px] text-slate-400">Shown in widget header and conversation title.</p>
        </div>

        <div>
          <label class="block text-xs font-medium text-slate-700">Conversation Tone</label>
          <select
            v-model="tone"
            class="mt-1 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm outline-none focus:border-amber-500"
          >
            <option value="friendly">Friendly & Warm (Default)</option>
            <option value="professional">Professional & Concise</option>
            <option value="casual">Casual & Conversational</option>
          </select>
          <p class="mt-1 text-[11px] text-slate-400">Influences the assistant's personality and warmth.</p>
        </div>
      </div>

      <!-- Welcome Message -->
      <div>
        <label class="block text-xs font-medium text-slate-700">Welcome Message</label>
        <textarea
          v-model="welcomeMessage"
          rows="2"
          maxlength="300"
          placeholder="Start the conversation whenever you're ready."
          class="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-amber-500"
        />
        <p class="mt-1 text-[11px] text-slate-400">Displayed in the chat widget when a visitor opens it.</p>
      </div>

      <!-- Theme Color & Avatar URL Row -->
      <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div>
          <label class="block text-xs font-medium text-slate-700">Brand Header Color</label>
          <div class="mt-1 flex items-center gap-2">
            <input
              v-model="primaryColor"
              type="color"
              class="h-9 w-10 cursor-pointer rounded border border-slate-200 p-0.5"
            />
            <input
              v-model="primaryColor"
              type="text"
              maxlength="7"
              pattern="^#(?:[0-9a-fA-F]{3}){1,2}$"
              placeholder="#0b1224"
              class="flex-1 rounded-lg border border-slate-200 px-3 py-2 font-mono text-sm outline-none focus:border-amber-500"
            />
          </div>
          <p class="mt-1 text-[11px] text-slate-400">Applied to widget header and launcher button.</p>
        </div>

        <div>
          <label class="block text-xs font-medium text-slate-700">Avatar Image URL (HTTPS)</label>
          <div class="mt-1 flex items-center gap-2 min-w-0">
            <input
              v-model="avatarUrl"
              type="url"
              maxlength="500"
              placeholder="https://example.com/logo.png"
              class="min-w-0 flex-1 rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-amber-500"
            />
            <img
              v-if="avatarUrl && avatarUrl.startsWith('https://')"
              :src="avatarUrl"
              alt="Avatar preview"
              class="h-9 w-9 shrink-0 rounded-lg border border-slate-200 object-cover"
              @error="(e) => (e.target.style.display = 'none')"
            />
          </div>
          <p class="mt-1 text-[11px] text-slate-400">Optional square logo or avatar image.</p>
        </div>
      </div>

      <!-- Human handoff / Lead capture toggle (T9) -->
      <div class="rounded-xl border border-slate-100 bg-slate-50/70 p-3">
        <label class="flex items-start gap-2.5 cursor-pointer">
          <input
            v-model="handoffEnabled"
            type="checkbox"
            class="mt-0.5 h-4 w-4 rounded border-slate-300 text-amber-500 focus:ring-amber-400"
          />
          <div class="text-xs">
            <span class="font-medium text-navy-950">Enable Human Handoff & Lead Capture</span>
            <p class="text-slate-500">
              Allows website visitors to request human contact or leave their info in the chat widget. Submitted leads capture customer details and recent conversation context.
            </p>
          </div>
        </label>
      </div>

      <!-- Quick Replies -->
      <div>
        <label class="block text-xs font-medium text-slate-700">
          Quick Reply Suggestions (Max 6)
        </label>
        <p class="text-[11px] text-slate-400">
          Clickable suggestion pills shown in an empty chat window to help visitors start quickly.
        </p>

        <!-- Chips list -->
        <div v-if="quickReplies.length > 0" class="mt-2 flex flex-wrap gap-1.5">
          <span
            v-for="(chip, index) in quickReplies"
            :key="index"
            class="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-xs text-navy-950 shadow-sm"
          >
            <span class="break-words">{{ chip }}</span>
            <button
              type="button"
              class="text-slate-400 hover:text-rose-500"
              title="Remove"
              @click="removeQuickReply(index)"
            >
              ×
            </button>
          </span>
        </div>

        <!-- Add chip input -->
        <div v-if="quickReplies.length < 6" class="mt-2 flex flex-col sm:flex-row items-stretch sm:items-center gap-2">
          <input
            v-model="newQuickReply"
            type="text"
            maxlength="40"
            placeholder="e.g. Check appointment status"
            class="w-full sm:flex-1 rounded-lg border border-slate-200 px-3 py-2 text-xs outline-none focus:border-amber-500"
            @keydown.enter.prevent="addQuickReply"
          />
          <button
            type="button"
            class="w-full sm:w-auto shrink-0 rounded-lg border border-slate-200 bg-white px-3.5 py-2 text-xs font-medium text-slate-700 hover:border-amber-500 text-center"
            @click="addQuickReply"
          >
            + Add suggestion
          </button>
        </div>
      </div>

      <!-- Feedback / Error messages -->
      <p v-if="error" class="rounded-lg bg-rose-50 px-3 py-2 text-xs text-rose-600">
        {{ error }}
      </p>

      <div class="flex justify-end pt-2">
        <button
          type="submit"
          :disabled="isSaving"
          class="w-full sm:w-auto rounded-lg bg-navy-950 px-5 py-2.5 text-xs font-medium text-white shadow-sm hover:bg-navy-900 disabled:opacity-60 text-center"
        >
          {{ isSaving ? "Saving changes..." : "Save Bot Settings" }}
        </button>
      </div>
    </form>
  </div>
</template>
