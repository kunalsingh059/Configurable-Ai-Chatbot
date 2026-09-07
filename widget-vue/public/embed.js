/**
 * Embed loader. A plain <iframe> can't resize itself from the inside, so
 * this script creates the iframe, keeps it small (just the launcher bubble)
 * by default, and expands/shrinks it by listening for postMessage events
 * sent from inside the widget (see App.vue's postResize()).
 *
 * All rounding/shadow is controlled HERE, on the iframe element itself
 * (with overflow: hidden so it actually clips the widget's content to
 * match) - not inside the Vue app. This guarantees the floating-card look
 * is consistent regardless of the iframe's internal viewport size, and
 * keeps the widget from ever covering the full page on desktop.
 *
 * On small/mobile screens, the panel expands to fill the viewport instead
 * of staying a fixed 380px box - same pattern Intercom/Crisp/Drift use,
 * since a fixed-width card doesn't fit well on a phone screen.
 *
 * Usage on a client's site:
 *   <script src="https://your-widget-domain.com/embed.js"
 *           data-api-key="sk_..."
 *           data-widget-url="https://your-widget-domain.com"></script>
 */
(function () {
  var scriptTag = document.currentScript;
  var apiKey = scriptTag.getAttribute("data-api-key");
  var widgetUrl = scriptTag.getAttribute("data-widget-url");

  if (!apiKey || !widgetUrl) {
    console.error("Chatbot widget: missing data-api-key or data-widget-url on the embed script tag.");
    return;
  }

  var widgetOrigin = new URL(widgetUrl).origin;

  var MARGIN = "20px";
  var BUBBLE_SIZE = "64px";
  var DESKTOP_WIDTH = "380px";
  var DESKTOP_HEIGHT = "600px";
  var MOBILE_BREAKPOINT = 480; // px - below this, go edge-to-edge like every modern chat widget does on phones

  var iframe = document.createElement("iframe");
  iframe.src = widgetUrl + "/";
  iframe.style.position = "fixed";
  iframe.style.bottom = MARGIN;
  iframe.style.right = MARGIN;
  iframe.style.width = BUBBLE_SIZE;
  iframe.style.height = BUBBLE_SIZE;
  iframe.style.border = "none";
  iframe.style.borderRadius = "9999px";
  iframe.style.overflow = "hidden"; // together with border-radius, actually clips the widget's content to match
  iframe.style.boxShadow = "0 8px 24px rgba(15, 23, 42, 0.18)";
  iframe.style.zIndex = "2147483647";
  // Only the shadow transitions smoothly - width/height/border-radius/
  // position snap instantly, same as the local dev preview. Animating a
  // circle morphing into a rectangle over time looks distractingly odd;
  // an instant snap reads as cleaner and more "modern app" than a slow
  // stretch.
  iframe.style.transition = "box-shadow 0.15s ease";
  iframe.title = "Chat widget";

  document.body.appendChild(iframe);

  function isMobile() {
    return window.innerWidth <= MOBILE_BREAKPOINT;
  }

  function openPanel() {
    if (isMobile()) {
      iframe.style.bottom = "0px";
      iframe.style.right = "0px";
      iframe.style.width = "100vw";
      iframe.style.height = "100vh";
      iframe.style.borderRadius = "0px";
    } else {
      iframe.style.bottom = MARGIN;
      iframe.style.right = MARGIN;
      // min() clamps against BOTH viewport dimensions so the panel can
      // never overflow - whether the window is short (laptop screens,
      // browser zoom at 100%) or narrow - it always shrinks to fit with
      // the same 20px breathing room the bubble already uses.
      iframe.style.width = "min(" + DESKTOP_WIDTH + ", calc(100vw - 40px))";
      iframe.style.height = "min(" + DESKTOP_HEIGHT + ", calc(100vh - 40px))";
      iframe.style.borderRadius = "16px";
    }
    iframe.style.boxShadow = "0 20px 48px rgba(15, 23, 42, 0.28)";
  }

  function closePanel() {
    iframe.style.bottom = MARGIN;
    iframe.style.right = MARGIN;
    iframe.style.width = BUBBLE_SIZE;
    iframe.style.height = BUBBLE_SIZE;
    iframe.style.borderRadius = "9999px";
    iframe.style.boxShadow = "0 8px 24px rgba(15, 23, 42, 0.18)";
  }

  window.addEventListener("message", function (event) {
    if (event.origin !== widgetOrigin) return;
    if (!event.data) return;

    if (event.data.type === "widget-ready") {
      iframe.contentWindow.postMessage({ type: "widget-init", apiKey: apiKey }, widgetOrigin);
      return;
    }

    if (event.data.type === "chatbot-widget:resize") {
      if (event.data.open) {
        openPanel();
      } else {
        closePanel();
      }
    }
  });
})();