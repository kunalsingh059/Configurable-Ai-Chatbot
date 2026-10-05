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
  const { apiKey, isResolved, parentOrigin } = useApiKey();

  let sessionId = generateSessionId();

  const messages = ref([]);
  const isSending = ref(false);
  // Shown instead of/alongside the typing dots while nothing has streamed
  // in yet - e.g. "Looking that up..." while the model is mid tool-call.
  const statusText = ref(null);
  const error = ref(null);

  async function sendMessage(text) {
    const trimmed = text.trim();
    if (!trimmed || isSending.value) return;

    if (!apiKey.value) {
      error.value = "This widget isn't configured correctly. Please contact the site owner.";
      return;
    }

    messages.value.push({ role: "user", content: trimmed });
    // Placeholder assistant bubble - filled in token-by-token as the
    // stream arrives. MessageList hides the typing dots as soon as this
    // has any content, so the transition from "..." to real text is
    // seamless rather than a dots-then-pop-in-all-at-once swap.
    const tempMessageId = "msg_" + Math.random().toString(36).slice(2, 10);
    const assistantIndex = messages.value.push({
      role: "assistant",
      content: "",
      message_id: tempMessageId,
      rating: null,
    }) - 1;
    isSending.value = true;
    statusText.value = null;
    error.value = null;

    // The backend bounds a full chat turn at MAX_CHAT_TURN_SECONDS (45s
    // server-side default) and sends an SSE "error" event if exceeded -
    // this client-side abort is a safety net for the case the connection
    // itself hangs with no data at all, so the widget doesn't spin
    // forever with no way to recover. Set comfortably ABOVE the backend's
    // own bound so a normal slow-but-real timeout event has time to arrive
    // first.
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 55000);

    try {
      const res = await fetch(`${API_BASE}/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-API-Key": apiKey.value,
          ...(parentOrigin.value ? { "X-Embed-Origin": parentOrigin.value } : {}),
        },
        body: JSON.stringify({ session_id: sessionId, message: trimmed }),
        signal: controller.signal,
      });

      if (!res.ok) {
        // Failures BEFORE streaming starts (bad API key, rate limited,
        // etc.) still come back as a normal JSON error body with a real
        // HTTP status - same as before streaming existed.
        const data = await res.json().catch(() => ({}));
        console.error("Chat request failed:", res.status, data);
        messages.value.splice(assistantIndex, 1); // drop the empty placeholder bubble
        error.value = friendlyErrorFor(res.status);
        return;
      }

      if (!res.body) {
        // Some environments (very old browsers, certain proxies) don't
        // expose a readable stream - fail clearly rather than hang.
        messages.value.splice(assistantIndex, 1);
        error.value = "Your browser doesn't support streaming responses. Please try a different browser.";
        return;
      }

      await consumeEventStream(res.body, assistantIndex);
    } catch (err) {
      if (err.name === "AbortError") {
        console.error("Chat request timed out client-side");
        error.value = "That's taking too long. Please try again.";
      } else {
        console.error("Chat request errored:", err);
        error.value = "Can't reach the assistant right now. Please try again.";
      }
      // Leave whatever partial text already streamed in - better than
      // discarding a mostly-complete answer just because the tail end
      // of the connection dropped.
    } finally {
      clearTimeout(timeoutId);
      isSending.value = false;
      statusText.value = null;
    }
  }

  // Reads the SSE body (`data: {...}\n\n` frames) and applies each event
  // to the placeholder assistant message as it arrives. Not using the
  // browser's built-in EventSource here because EventSource only supports
  // GET requests with no custom headers - this needs POST + an API key
  // header, so the stream is parsed manually from a plain fetch() body.
  async function consumeEventStream(body, assistantIndex) {
    const reader = body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const frames = buffer.split("\n\n");
      buffer = frames.pop(); // last element may be an incomplete frame - keep it for next read

      for (const frame of frames) {
        const line = frame.trim();
        if (!line.startsWith("data:")) continue;

        let payload;
        try {
          payload = JSON.parse(line.slice(5).trim());
        } catch {
          continue; // ignore a malformed frame rather than crashing the whole stream
        }

        if (payload.type === "token") {
          messages.value[assistantIndex].content += payload.text;
          statusText.value = null;
        } else if (payload.type === "tool_start") {
          statusText.value = "Looking that up…";
        } else if (payload.type === "error") {
          error.value = payload.message;
          // If nothing streamed in before the error, drop the empty
          // placeholder bubble instead of leaving a blank one behind.
          if (!messages.value[assistantIndex].content) {
            messages.value.splice(assistantIndex, 1);
          }
        } else if (payload.type === "done") {
          if (payload.message_id) {
            messages.value[assistantIndex].message_id = payload.message_id;
          }
          // Backstop: if for any reason no token events arrived (a
          // provider that doesn't stream, an edge case), the full text
          // is still here on "done" so the bubble never ends up empty.
          if (!messages.value[assistantIndex].content && payload.text) {
            messages.value[assistantIndex].content = payload.text;
          }
        }
      }
    }
  }

  async function submitFeedback(messageId, rating, comment = null) {
    if (!apiKey.value || !messageId) return;
    const idx = messages.value.findIndex((m) => m.message_id === messageId);
    if (idx !== -1) {
      messages.value[idx].rating = rating;
    }

    const targetMsg = idx !== -1 ? messages.value[idx] : null;
    const prevMsg = idx > 0 ? messages.value[idx - 1] : null;
    const userQuestion = prevMsg && prevMsg.role === "user" ? prevMsg.content : null;
    const botAnswer = targetMsg ? targetMsg.content : null;

    try {
      await fetch(`${API_BASE}/api/feedback`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-API-Key": apiKey.value,
          ...(parentOrigin.value ? { "X-Embed-Origin": parentOrigin.value } : {}),
        },
        body: JSON.stringify({
          session_id: sessionId,
          message_id: messageId,
          rating,
          comment,
          user_question: userQuestion,
          bot_answer: botAnswer,
        }),
      });
    } catch (err) {
      console.error("Failed to submit feedback:", err);
    }
  }

  function resetChat() {
    sessionId = generateSessionId();
    messages.value = [];
    error.value = null;
    statusText.value = null;
  }

  const hasApiKey = computed(() => !!apiKey.value);

  return {
    messages,
    isSending,
    statusText,
    error,
    sendMessage,
    submitFeedback,
    hasApiKey,
    isResolved,
    resetChat,
  };
}