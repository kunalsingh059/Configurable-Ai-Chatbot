<script setup>
import { ref, onMounted } from "vue";
import { useRoute } from "vue-router";
import { api, ApiError } from "../services/api";
import { useToast } from "../composables/useToast";
import PasswordInput from "../components/PasswordInput.vue";

const route = useRoute();
const toast = useToast();

const token = ref("");
const newPassword = ref("");
const confirmPassword = ref("");
const error = ref(null);
const isSubmitting = ref(false);
const succeeded = ref(false);

onMounted(() => {
  token.value = route.query.token || "";
  if (!token.value) {
    error.value = "This link is missing its reset token - please use the link from your email.";
  }
});

async function submit() {
  // Guard against a double-click/double-submit: :disabled="isSubmitting"
  // on the button only takes effect after Vue's next DOM update, which is
  // asynchronous - two clicks close enough together can both invoke
  // submit() before the button visually disables. Checking isSubmitting
  // here, synchronously, blocks the second call immediately in memory,
  // not just in the DOM. Without this, a double-click can fire two
  // /auth/reset-password requests with the same token: the first
  // succeeds, the second correctly gets rejected as "already used" by
  // the backend's one-time-use check - and if that error resolves after
  // the first request's success, it overwrites the success message even
  // though the password WAS actually changed.
  if (isSubmitting.value) return;

  error.value = null;

  if (newPassword.value !== confirmPassword.value) {
    error.value = "Passwords don't match.";
    return;
  }
  if (newPassword.value.length < 8) {
    error.value = "Password must be at least 8 characters.";
    return;
  }

  isSubmitting.value = true;
  try {
    await api.resetPassword(token.value, newPassword.value);
    succeeded.value = true;
    toast.success("Password updated.");
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : "Can't reach the backend. Is uvicorn running?";
  } finally {
    isSubmitting.value = false;
  }
}
</script>

<template>
  <div class="flex min-h-screen w-full items-start justify-center overflow-y-auto px-3.5 py-8 sm:items-center sm:px-4 sm:py-12">
    <div class="w-full max-w-sm">
      <div class="mb-6 text-center sm:mb-8">
        <div
          class="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-navy-950 text-sm font-semibold text-amber-500"
        >
          CP
        </div>
        <h1 class="text-lg font-semibold text-navy-950">Choose a new password</h1>
      </div>

      <div v-if="succeeded" class="rounded-2xl bg-white p-5 sm:p-6 text-center shadow-sm ring-1 ring-slate-100">
        <p class="text-sm text-navy-950">Your password has been updated.</p>
        <router-link to="/login" class="mt-4 inline-block text-sm font-medium text-amber-600 hover:underline">
          Log in now
        </router-link>
      </div>

      <form v-else class="space-y-4 rounded-2xl bg-white p-4 shadow-sm ring-1 ring-slate-100 sm:p-6" @submit.prevent="submit">
        <div>
          <label class="mb-1 block text-xs font-medium text-slate-600">New password</label>
          <PasswordInput v-model="newPassword" required autofocus autocomplete="new-password" />
        </div>
        <div>
          <label class="mb-1 block text-xs font-medium text-slate-600">Confirm new password</label>
          <PasswordInput v-model="confirmPassword" required autocomplete="new-password" />
        </div>

        <p v-if="error" class="rounded-lg bg-rose-50 px-3 py-2 text-xs text-rose-600">
          {{ error }}
        </p>

        <button
          type="submit"
          :disabled="isSubmitting || !token"
          class="w-full rounded-lg bg-navy-950 py-2.5 text-sm font-medium text-white transition hover:bg-navy-900 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {{ isSubmitting ? "Updating..." : "Update password" }}
        </button>
      </form>
    </div>
  </div>
</template>