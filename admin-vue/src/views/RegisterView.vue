<script setup>
import { ref, watch } from "vue";
import { useAuthStore } from "../stores/auth";
import { ApiError } from "../services/api";
import { useToast } from "../composables/useToast";
import PasswordInput from "../components/PasswordInput.vue";

const auth = useAuthStore();
const toast = useToast();

const businessName = ref("");   // what they actually type, e.g. "Life Secure Pathology"
const tenantId = ref("");        // auto-generated slug, e.g. "life-secure-pathology"
const tenantIdTouched = ref(false); // becomes true the moment they edit the ID field by hand

const username = ref("");
const email = ref("");           // used only for password-reset emails
const password = ref("");
const error = ref(null);
const isSubmitting = ref(false);
const succeeded = ref(false);

// Same idea as Notion/Shopify/GitHub org-name → URL-slug fields: turns
// "Life Secure Pathology" into "life-secure-pathology" - lowercase, spaces
// to hyphens, strips anything that isn't a letter/number/hyphen.
function slugify(text) {
  return text
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9\s-]/g, "")
    .replace(/\s+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "");
}

// Auto-fill the Business ID as they type the name - but only until they
// touch the ID field themselves. Once touched, we stop overwriting it, so
// someone can still manually fix a collision or type a custom slug.
watch(businessName, (val) => {
  if (!tenantIdTouched.value) {
    tenantId.value = slugify(val);
  }
});

function onTenantIdInput() {
  tenantIdTouched.value = true;
}

async function submit() {
  if (isSubmitting.value) return; // guard against double-click firing two registrations before the button visually disables
  error.value = null;
  isSubmitting.value = true;
  try {
    await auth.register(tenantId.value.trim(), businessName.value.trim(), username.value.trim(), email.value.trim(), password.value);
    toast.success("Account created - awaiting activation.");
    succeeded.value = true;
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
        <h1 class="text-lg font-semibold text-navy-950">Create your account</h1>
        <p class="mt-1 text-sm text-slate-500">A super admin must activate it before you can log in</p>
      </div>

      <div v-if="succeeded" class="rounded-2xl bg-white p-6 text-center shadow-sm ring-1 ring-slate-100">
        <p class="text-sm text-navy-950">
          Account created. It must be activated by a super admin before you can log in.
        </p>
        <router-link to="/login" class="mt-4 inline-block text-sm font-medium text-amber-600 hover:underline">
          Back to login
        </router-link>
      </div>

      <form v-else class="space-y-4 rounded-2xl bg-white p-5 shadow-sm ring-1 ring-slate-100 sm:p-6" @submit.prevent="submit">
        <div>
          <label class="mb-1 block text-xs font-medium text-slate-600">Business Name</label>
          <input
            v-model="businessName"
            type="text"
            required
            placeholder="e.g. Life Secure Pathology"
            class="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-amber-500"
          />
        </div>

        <div>
          <label class="mb-1 block text-xs font-medium text-slate-600">
            Business ID <span class="font-normal text-slate-400">(auto-generated - editable if needed)</span>
          </label>
          <input
            v-model="tenantId"
            type="text"
            required
            placeholder="life-secure-pathology"
            class="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-amber-500"
            @input="onTenantIdInput"
          />
          <p class="mt-1 text-[11px] text-slate-400">
            This identifies your account internally. It can't be changed after signup.
          </p>
        </div>

        <div>
          <label class="mb-1 block text-xs font-medium text-slate-600">Username</label>
          <input
            v-model="username"
            type="text"
            required
            class="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-amber-500"
          />
        </div>
        <div>
          <label class="mb-1 block text-xs font-medium text-slate-600">
            Email <span class="font-normal text-slate-400">(used to reset your password)</span>
          </label>
          <input
            v-model="email"
            type="email"
            required
            placeholder="you@yourbusiness.com"
            class="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-amber-500"
          />
        </div>
        <div>
          <label class="mb-1 block text-xs font-medium text-slate-600">Password</label>
          <PasswordInput v-model="password" required autocomplete="new-password" />
        </div>

        <p v-if="error" class="rounded-lg bg-rose-50 px-3 py-2 text-xs text-rose-600">
          {{ error }}
        </p>

        <button
          type="submit"
          :disabled="isSubmitting"
          class="w-full rounded-lg bg-navy-950 py-2.5 text-sm font-medium text-white transition hover:bg-navy-900 disabled:opacity-60"
        >
          {{ isSubmitting ? "Creating..." : "Create account" }}
        </button>
      </form>

      <p class="mt-4 text-center text-sm text-slate-500">
        Already have an account?
        <router-link to="/login" class="font-medium text-amber-600 hover:underline">Log in</router-link>
      </p>
    </div>
  </div>
</template>