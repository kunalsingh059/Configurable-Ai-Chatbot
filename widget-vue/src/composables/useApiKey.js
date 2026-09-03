import { ref } from "vue";

/**
 * SECURITY: the api_key that identifies which business a chat belongs to
 * must never sit in the widget's URL - URLs get logged by servers, saved
 * in browser history, and are trivially visible to anyone who inspects the
 * iframe's src attribute. In production, embed.js (running on the client's
 * page) holds the key and hands it to this iframe via postMessage AFTER
 * the iframe has loaded - it never appears in any URL at all.
 *
 * A `?api_key=...` URL param is still supported ONLY as a local-dev
 * fallback (e.g. opening the widget directly in a browser tab with no
 * parent page at all, like we did during early testing). Real embeds via
 * embed.js never use this path.
 *
 * This state is module-level (not created fresh inside the function), so
 * every composable that calls useApiKey() shares the same resolved key
 * from a single postMessage handshake, instead of each running its own.
 */
const params = new URLSearchParams(window.location.search);
const urlKey = params.get("api_key");

const apiKey = ref(urlKey || null);
const isResolved = ref(!!urlKey);

let handshakeStarted = false;

function startHandshake() {
  if (handshakeStarted || urlKey) return;
  handshakeStarted = true;

  if (window.parent === window) {
    // Not inside an iframe at all, and no URL key either - nothing left to try.
    isResolved.value = true;
    return;
  }

  window.addEventListener("message", function handleMessage(event) {
    // Only accept the key from our direct parent window - never trust a
    // message claiming to be "widget-init" from anywhere else.
    if (event.source !== window.parent) return;
    if (!event.data || event.data.type !== "widget-init") return;

    apiKey.value = event.data.apiKey || null;
    isResolved.value = true;
  });

  // Announces "I'm ready" to the parent page. This message carries no
  // secret itself, so "*" is fine here - it's the *reply* (sent from
  // embed.js) that's origin-restricted, since that's the one with the key.
  window.parent.postMessage({ type: "widget-ready" }, "*");
}

startHandshake();

export function useApiKey() {
  return { apiKey, isResolved };
}