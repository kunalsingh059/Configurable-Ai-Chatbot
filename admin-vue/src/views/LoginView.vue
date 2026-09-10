<script setup>
import { ref } from "vue";
import { useRouter } from "vue-router";
import { useAuthStore } from "../stores/auth";
import { ApiError } from "../services/api";
import { useToast } from "../composables/useToast";

const router = useRouter();
const auth = useAuthStore();
const toast = useToast();

const username = ref("");
const password = ref("");
const error = ref(null);
const isSubmitting = ref(false);

async function submit() {
  if (isSubmitting.value) return; // guard against double-click firing two logins before the button visually disables
  error.value = null;
  isSubmitting.value = true;
  try {
    const data = await auth.login(username.value.trim(), password.value);
    toast.success("Welcome back.");
    router.push(data.role === "super_admin" ? "/superadmin" : "/dashboard");
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
        <h1 class="text-lg font-semibold text-navy-950">Chatbot Platform</h1>
        <p class="mt-1 text-sm text-slate-500">Sign in to your dashboard</p>
      </div>

      <form class="space-y-4 rounded-2xl bg-white p-5 shadow-sm ring-1 ring-slate-100 sm:p-6" @submit.prevent="submit">
        <div>
          <label class="mb-1 block text-xs font-medium text-slate-600">Username</label>
          <input
            v-model="username"
            type="text"
            required
            autofocus
            autocomplete="username"
            class="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none transition focus:border-amber-500 focus:ring-2 focus:ring-amber-500/20"
          />
        </div>
        <div>
          <label class="mb-1 block text-xs font-medium text-slate-600">Password</label>
          <input
            v-model="password"
            type="password"
            required
            autocomplete="current-password"
            class="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none transition focus:border-amber-500 focus:ring-2 focus:ring-amber-500/20"
          />
          <router-link
            to="/forgot-password"
            class="mt-1.5 inline-block text-xs font-medium text-amber-600 hover:underline"
          >
            Forgot password?
          </router-link>
        </div>

        <p v-if="error" class="rounded-lg bg-rose-50 px-3 py-2 text-xs text-rose-600">
          {{ error }}
        </p>

        <button
          type="submit"
          :disabled="isSubmitting"
          class="flex w-full items-center justify-center gap-2 rounded-lg bg-navy-950 py-2.5 text-sm font-medium text-white transition hover:bg-navy-900 disabled:cursor-not-allowed disabled:opacity-60"
        >
          <svg
            v-if="isSubmitting"
            class="h-4 w-4 animate-spin"
            viewBox="0 0 24 24"
            fill="none"
          >
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
          </svg>
          {{ isSubmitting ? "Signing in..." : "Log in" }}
        </button>
      </form>

      <p class="mt-4 text-center text-sm text-slate-500">
        New business?
        <router-link to="/register" class="font-medium text-amber-600 hover:underline">
          Create an account
        </router-link>
      </p>
    </div>
  </div>
</template>