import { ref, watch } from "vue";
import { useApiKey } from "./useApiKey";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

export function useBusinessConfig() {
  const { apiKey, parentOrigin } = useApiKey();
  const businessName = ref("Support Assistant");

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
          businessName.value = data.business_name || "Support Assistant";
        }
      } catch {
        // Silently keep the default name if config fetch fails - the chat
        // itself will surface a clearer error if the api_key is actually bad.
      }
    },
    { immediate: true }
  );

  return { businessName };
}