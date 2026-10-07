<script setup>
import { ref } from "vue";
import { useRouter } from "vue-router";
import { useAuthStore } from "../stores/auth";
import AnalyticsOverview from "../components/AnalyticsOverview.vue";
import LeadsManager from "../components/LeadsManager.vue";
import ToolsManager from "../components/ToolsManager.vue";
import DocumentsManager from "../components/DocumentsManager.vue";
import WidgetEmbedCard from "../components/WidgetEmbedCard.vue";
import EmbedSecurity from "../components/EmbedSecurity.vue";
import BusinessSettings from "../components/BusinessSettings.vue";
import UnansweredQuestions from "../components/UnansweredQuestions.vue";
import ConfirmDialog from "../components/ConfirmDialog.vue";

const auth = useAuthStore();
const router = useRouter();
const showLogoutConfirm = ref(false);

function confirmLogout() {
  showLogoutConfirm.value = false;
  auth.logout();
  router.push("/login");
}
</script>

<template>
  <div class="mx-auto max-w-3xl px-3 sm:px-4 py-5 sm:py-8">
    <div class="mb-5 sm:mb-6 flex items-center justify-between gap-3">
      <div class="min-w-0 flex-1">
        <h1 class="truncate text-base sm:text-lg font-semibold text-navy-950" :title="auth.tenantId">{{ auth.tenantId }}</h1>
        <p class="text-xs sm:text-sm text-slate-500">Business owner dashboard</p>
      </div>
      <button
        class="shrink-0 rounded-lg border border-slate-200 px-3 py-1.5 sm:py-2 text-xs font-medium text-navy-900 transition hover:border-amber-500 focus:outline-none"
        @click="showLogoutConfirm = true"
      >
        Log out
      </button>
    </div>

    <div class="space-y-4 sm:space-y-5">
      <AnalyticsOverview />
      <LeadsManager />
      <UnansweredQuestions />
      <BusinessSettings />
      <WidgetEmbedCard v-if="auth.apiKey" :api-key="auth.apiKey" />
      <EmbedSecurity />
      <ToolsManager />
      <DocumentsManager />
    </div>

    <ConfirmDialog
      :open="showLogoutConfirm"
      title="Log out?"
      message="You'll need to sign in again to manage your assistant."
      confirm-label="Log out"
      danger
      @confirm="confirmLogout"
      @cancel="showLogoutConfirm = false"
    />
  </div>
</template>