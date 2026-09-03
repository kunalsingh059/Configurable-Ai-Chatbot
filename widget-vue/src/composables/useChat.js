import { ref, computed } from "vue";
import { useApiKey } from "./useApiKey";

// Set VITE_API_BASE_URL at build time for production (e.g. your deployed
// FastAPI URL). Falls back to localhost for local dev, same as the old
// widget.html's hardcoded API_URL.
const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

const sessionId = "session-" + Math.random().toString(36).slice(2);

export function useChat() {
  const { apiKey, isResolved } = useApiKey();

  const messages = ref([
    {
      role: "assistant",
      content:
        "Hi! I'm your support assistant. I can help you with products, orders, menus, policies, and other questions.",
    },
  ]);
  const isSending = ref(false);
  const error = ref(null);

  async function sendMessage(text) {
    const trimmed = text.trim();
    if (!trimmed || isSending.value) return;

    if (!apiKey.value) {
      error.value =
        "This widget isn't configured correctly - no api_key was received.";
      return;
    }

    messages.value.push({ role: "user", content: trimmed });
    isSending.value = true;
    error.value = null;

    try {
      const res = await fetch(`${API_BASE}/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-API-Key": apiKey.value,
        },
        body: JSON.stringify({ session_id: sessionId, message: trimmed }),
      });

      const data = await res.json().catch(() => ({}));

      if (!res.ok) {
        error.value = data.detail || `Something went wrong (${res.status}).`;
        return;
      }

      messages.value.push({ role: "assistant", content: data.reply });
    } catch (err) {
      error.value = "Can't reach the assistant right now. Please try again.";
    } finally {
      isSending.value = false;
    }
  }

  const hasApiKey = computed(() => !!apiKey.value);

  return { messages, isSending, error, sendMessage, hasApiKey, isResolved };
}