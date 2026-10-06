<script setup>
import { ref } from "vue";

const props = defineProps({
  open: { type: Boolean, default: false },
  primaryColor: { type: String, default: null },
});

const emit = defineEmits(["close", "submit"]);

const name = ref("");
const email = ref("");
const phone = ref("");
const message = ref("");

const isSubmitting = ref(false);
const isSuccess = ref(false);
const errorMessage = ref(null);

function validate() {
  if (!name.value.trim()) {
    return "Please enter your name.";
  }
  if (!email.value.trim() && !phone.value.trim()) {
    return "Please provide an email address or phone number so we can reach you.";
  }
  return null;
}

async function handleSubmit() {
  errorMessage.value = null;
  const validationError = validate();
  if (validationError) {
    errorMessage.value = validationError;
    return;
  }

  isSubmitting.value = true;
  try {
    await emit("submit", {
      name: name.value.trim(),
      email: email.value.trim() || null,
      phone: phone.value.trim() || null,
      message: message.value.trim() || "",
      onSuccess: () => {
        isSuccess.value = true;
      },
      onError: (err) => {
        errorMessage.value = err?.message || "Failed to submit. Please try again.";
      },
    });
  } catch (err) {
    errorMessage.value = err?.message || "Failed to submit. Please try again.";
  } finally {
    isSubmitting.value = false;
  }
}

function handleClose() {
  if (isSuccess.value) {
    // Reset form after closing on success
    name.value = "";
    email.value = "";
    phone.value = "";
    message.value = "";
    isSuccess.value = false;
    errorMessage.value = null;
  }
  emit("close");
}
</script>

<template>
  <Transition name="modal-fade">
    <div
      v-if="open"
      class="absolute inset-0 z-50 flex items-center justify-center bg-navy-950/60 p-4 backdrop-blur-xs"
      @click.self="handleClose"
    >
      <div
        class="relative w-full max-w-sm rounded-2xl bg-white p-5 shadow-2xl ring-1 ring-black/5"
      >
        <!-- Close Button -->
        <button
          type="button"
          class="absolute right-3.5 top-3.5 flex h-7 w-7 items-center justify-center rounded-lg text-slate-400 hover:bg-slate-100 hover:text-slate-700"
          title="Close"
          @click="handleClose"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>

        <!-- Success Screen -->
        <div v-if="isSuccess" class="py-4 text-center">
          <div
            class="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-emerald-100 text-emerald-600 mb-3"
          >
            <svg class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5">
              <path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7" />
            </svg>
          </div>
          <h3 class="text-sm font-semibold text-navy-950">Message Sent!</h3>
          <p class="mt-1 text-xs text-slate-500">
            Thank you! We've received your contact details and recent chat context. Our team will get back to you shortly.
          </p>
          <button
            type="button"
            class="mt-4 w-full rounded-xl bg-navy-950 py-2.5 text-xs font-semibold text-white transition hover:bg-navy-900"
            :style="primaryColor ? { backgroundColor: primaryColor } : {}"
            @click="handleClose"
          >
            Back to Chat
          </button>
        </div>

        <!-- Form Screen -->
        <div v-else>
          <div>
            <h3 class="text-sm font-semibold text-navy-950">Talk to Human Support</h3>
            <p class="mt-0.5 text-xs text-slate-500">
              Leave your details and someone from our team will follow up directly.
            </p>
          </div>

          <p
            v-if="errorMessage"
            class="mt-2.5 rounded-lg bg-rose-50 px-3 py-2 text-xs text-rose-600"
          >
            {{ errorMessage }}
          </p>

          <form class="mt-3.5 space-y-2.5" @submit.prevent="handleSubmit">
            <div>
              <label class="block text-[11px] font-medium text-slate-700">Your Name *</label>
              <input
                v-model="name"
                type="text"
                required
                placeholder="e.g. Rahul Sharma"
                class="mt-1 w-full rounded-lg border border-slate-200 px-3 py-1.5 text-xs text-navy-950 placeholder-slate-400 focus:border-amber-500 focus:outline-none"
              />
            </div>

            <div class="grid grid-cols-2 gap-2">
              <div>
                <label class="block text-[11px] font-medium text-slate-700">Email</label>
                <input
                  v-model="email"
                  type="email"
                  placeholder="name@example.com"
                  class="mt-1 w-full rounded-lg border border-slate-200 px-3 py-1.5 text-xs text-navy-950 placeholder-slate-400 focus:border-amber-500 focus:outline-none"
                />
              </div>
              <div>
                <label class="block text-[11px] font-medium text-slate-700">Phone</label>
                <input
                  v-model="phone"
                  type="tel"
                  placeholder="+91 98765 43210"
                  class="mt-1 w-full rounded-lg border border-slate-200 px-3 py-1.5 text-xs text-navy-950 placeholder-slate-400 focus:border-amber-500 focus:outline-none"
                />
              </div>
            </div>

            <div>
              <label class="block text-[11px] font-medium text-slate-700">Note (Optional)</label>
              <textarea
                v-model="message"
                rows="2"
                placeholder="What can we help you with?"
                class="mt-1 w-full rounded-lg border border-slate-200 px-3 py-1.5 text-xs text-navy-950 placeholder-slate-400 focus:border-amber-500 focus:outline-none resize-none"
              />
            </div>

            <div class="pt-1 flex items-center justify-end gap-2">
              <button
                type="button"
                class="rounded-lg px-3 py-1.5 text-xs font-medium text-slate-500 hover:text-slate-800"
                @click="handleClose"
              >
                Cancel
              </button>
              <button
                type="submit"
                :disabled="isSubmitting"
                class="rounded-lg bg-navy-950 px-4 py-1.5 text-xs font-semibold text-white transition hover:bg-navy-900 disabled:opacity-50"
                :style="primaryColor ? { backgroundColor: primaryColor } : {}"
              >
                {{ isSubmitting ? "Sending..." : "Submit Inquiry" }}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.modal-fade-enter-active,
.modal-fade-leave-active {
  transition: opacity 0.15s ease;
}
.modal-fade-enter-from,
.modal-fade-leave-to {
  opacity: 0;
}
</style>
