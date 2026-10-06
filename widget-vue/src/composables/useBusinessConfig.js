import { ref, watch } from "vue";
import { useApiKey } from "./useApiKey";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

export function useBusinessConfig() {
  const { apiKey, parentOrigin } = useApiKey();
  const businessName = ref("Support Assistant");
  const welcomeMessage = ref("Start the conversation whenever you're ready.");
  const primaryColor = ref("#0b1224");
  const avatarUrl = ref(null);
  const quickReplies = ref([]);

  watch(
    apiKey,
    async (key) => {
      if (!key) return;
      try {
        const res = await fetch(`${API_BASE}/widget/config`, {
          headers: {
            "X-API-Key": key,
            ...(parentOrigin.value ? { "X-Embed-Origin": parentOrigin.value } : {}),
          },
        });
        if (res.ok) {
          const data = await res.json();
          businessName.value = data.bot_name || data.business_name || "Support Assistant";
          welcomeMessage.value = data.welcome_message || "Start the conversation whenever you're ready.";
          primaryColor.value = data.primary_color || "#0b1224";
          avatarUrl.value = data.avatar_url || null;
          quickReplies.value = Array.isArray(data.quick_replies) ? data.quick_replies : [];
        }
      } catch {
        // Silently keep default config if config fetch fails
      }
    },
    { immediate: true }
  );

  return {
    businessName,
    welcomeMessage,
    primaryColor,
    avatarUrl,
    quickReplies,
  };
}