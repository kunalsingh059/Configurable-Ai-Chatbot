<script setup>
import { ref } from "vue";
import { api, ApiError } from "../services/api";

const email = ref("");
const error = ref(null);
const isSubmitting = ref(false);
const submitted = ref(false);

async function submit() {
  if (isSubmitting.value) return; // guard against double-click firing two requests before the button visually disables
  error.value = null;
  isSubmitting.value = true;
  try {
    await api.forgotPassword(email.value.trim());
    submitted.value = true;
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : "Can't reach the backend. Is uvicorn running?";
  } finally {
    isSubmitting.value = false;
  }
}
</script>

<template>
  <div class="flex min-h-screen w-full items-start justify-center overflow-y-auto px-4 py-10 sm:items-center sm:py-12">
    <div class="w-full max-w-sm">
      <div class="mb-6 text-center sm:mb-8">
        <div
          class="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-navy-950 text-sm font-semibold text-amber-500"
        >
          CP
        </div>
        <h1 class="text-lg font-semibold text-navy-950">Reset your password</h1>
        <p class="mt-1 text-sm text-slate-500">We'll email you a link to choose a new one</p>
      </div>

      <div v-if="submitted" class="rounded-2xl bg-white p-6 text-center shadow-sm ring-1 ring-slate-100">
        <p class="text-sm text-navy-950">
          If <strong>{{ email }}</strong> is registered, a reset link is on its way. Check your inbox
          (and spam folder) - the link expires in 30 minutes.
        </p>
        <router-link to="/login" class="mt-4 inline-block text-sm font-medium text-amber-600 hover:underline">
          Back to login
        </router-link>
      </div>

      <form v-else class="space-y-4 rounded-2xl bg-white p-5 shadow-sm ring-1 ring-slate-100 sm:p-6" @submit.prevent="submit">
        <div>
          <label class="mb-1 block text-xs font-medium text-slate-600">Email address</label>
          <input
            v-model="email"
            type="email"
            required
            autofocus
            placeholder="you@yourbusiness.com"
            class="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none transition focus:border-amber-500 focus:ring-2 focus:ring-amber-500/20"
          />
        </div>

        <p v-if="error" class="rounded-lg bg-rose-50 px-3 py-2 text-xs text-rose-600">
          {{ error }}
        </p>

        <button
          type="submit"
          :disabled="isSubmitting"
          class="w-full rounded-lg bg-navy-950 py-2.5 text-sm font-medium text-white transition hover:bg-navy-900 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {{ isSubmitting ? "Sending..." : "Send reset link" }}
        </button>
      </form>

      <p class="mt-4 text-center text-sm text-slate-500">
        <router-link to="/login" class="font-medium text-amber-600 hover:underline">Back to login</router-link>
      </p>
    </div>
  </div>
</template>