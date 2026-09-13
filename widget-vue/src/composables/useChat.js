import { ref, computed } from "vue";
import { useApiKey } from "./useApiKey";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

function generateSessionId() {
  return "session-" + Math.random().toString(36).slice(2);
}

function friendlyErrorFor(status) {
  if (status === 401 || status === 403) {
    return "This widget isn't configured correctly. Please contact the site owner.";
  }
  if (status === 429) {
    return "You're sending messages a little too fast. Please wait a moment and try again.";
  }
  if (status >= 500) {
    return "Something went wrong on our end. Please try again in a moment.";
  }
  return "Sorry, I couldn't process that. Please try again.";
}

export function useChat(businessNameRef) {
  const { apiKey, isResolved } = useApiKey();

  let sessionId = generateSessionId();

  const messages = ref([]);
  const isSending = ref(false);
  const error = ref(null);

  async function sendMessage(text) {
    const trimmed = text.trim();
    if (!trimmed || isSending.value) return;

    if (!apiKey.value) {
      error.value = "This widget isn't configured correctly. Please contact the site owner.";
      return;
    }

    messages.value.push({ role: "user", content: trimmed });
    isSending.value = true;
    error.value = null;

    // The backend bounds a full chat turn at MAX_CHAT_TURN_SECONDS (45s
    // server-side default) and returns a proper 504 if it's exceeded - this
    // is a safety net for the case the backend/network hangs completely
    // with no response at all, so the widget doesn't spin forever with no
    // way to recover. Set comfortably ABOVE the backend's own bound so a
    // normal slow-but-real 504 response has time to arrive first.
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 55000);

    try {
      const res = await fetch(`${API_BASE}/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-API-Key": apiKey.value,
        },
        body: JSON.stringify({ session_id: sessionId, message: trimmed }),
        signal: controller.signal,
      });

      const data = await res.json().catch(() => ({}));

      if (!res.ok) {
        console.error("Chat request failed:", res.status, data);
        error.value = friendlyErrorFor(res.status);
        return;
      }

      messages.value.push({ role: "assistant", content: data.reply });
    } catch (err) {
      if (err.name === "AbortError") {
        console.error("Chat request timed out client-side");
        error.value = "That's taking too long. Please try again.";
      } else {
        console.error("Chat request errored:", err);
        error.value = "Can't reach the assistant right now. Please try again.";
      }
    } finally {
      clearTimeout(timeoutId);
      isSending.value = false;
    }
  }

  function resetChat() {
    sessionId = generateSessionId();
    messages.value = [];
    error.value = null;
  }

  const hasApiKey = computed(() => !!apiKey.value);

  return { messages, isSending, error, sendMessage, hasApiKey, isResolved, resetChat };
}