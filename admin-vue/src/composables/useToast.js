import { reactive } from "vue";

let nextId = 1;
const toasts = reactive([]);

/**
 * Simple app-wide toast queue. Any component can call useToast().success(...)
 * / .error(...) - ToastContainer.vue (mounted once in App.vue) renders
 * whatever's in the shared `toasts` array. Replaces alert()/silent failures
 * across login, register, logout, and every create/update/delete action.
 */
export function useToast() {
  function push(message, type = "info", duration = 3500) {
    const id = nextId++;
    toasts.push({ id, message, type });
    setTimeout(() => dismiss(id), duration);
  }

  function dismiss(id) {
    const index = toasts.findIndex((t) => t.id === id);
    if (index !== -1) toasts.splice(index, 1);
  }

  return {
    toasts,
    success: (message) => push(message, "success"),
    error: (message) => push(message, "error"),
    info: (message) => push(message, "info"),
    dismiss,
  };
}
