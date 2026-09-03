<script setup>
import { ref } from "vue";
import { useRouter } from "vue-router";
import { useAuthStore } from "../stores/auth";
import ToolsManager from "../components/ToolsManager.vue";
import DocumentsManager from "../components/DocumentsManager.vue";
import WidgetEmbedCard from "../components/WidgetEmbedCard.vue";
import BusinessSettings from "../components/BusinessSettings.vue";
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
  <div class="mx-auto max-w-3xl px-4 py-8">
    <div class="mb-6 flex items-center justify-between">
      <div>
        <h1 class="text-lg font-semibold text-navy-950">{{ auth.tenantId }}</h1>
        <p class="text-sm text-slate-500">Business owner dashboard</p>
      </div>
      <button class="rounded-lg border border-slate-200 px-3 py-2 text-xs font-medium text-navy-900 hover:border-amber-500" @click="showLogoutConfirm = true">
        Log out
      </button>
    </div>

    <div class="space-y-5">
      <BusinessSettings />
      <WidgetEmbedCard v-if="auth.apiKey" :api-key="auth.apiKey" />
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
