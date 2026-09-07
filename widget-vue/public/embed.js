/**
 * Embed loader. A plain <iframe> can't resize itself from the inside, so
 * this script creates the iframe, keeps it small (just the launcher bubble)
 * by default, and expands/shrinks it by listening for postMessage events
 * sent from inside the widget (see App.vue's postResize()).
 *
 * Usage on a client's site:
 *   <script src="https://your-widget-domain.com/embed.js"
 *           data-api-key="sk_..."
 *           data-widget-url="https://your-widget-domain.com"
 *           data-position="bottom-right"   optional: "bottom-right" | "bottom-left"
 *           data-offset="20"               optional: px, default 20
 *           data-z-index="999999"          optional: default 999999
 *   ></script>
 */
(function () {
  var scriptTag = document.currentScript;
  var apiKey = scriptTag.getAttribute("data-api-key");
  var widgetUrl = scriptTag.getAttribute("data-widget-url");

  if (!apiKey || !widgetUrl) {
    console.error("Chatbot widget: missing data-api-key or data-widget-url on the embed script tag.");
    return;
  }

  var widgetOrigin;
  try {
    widgetOrigin = new URL(widgetUrl).origin;
  } catch (err) {
    console.error("Chatbot widget: invalid data-widget-url \"" + widgetUrl + "\".");
    return;
  }

  var normalizedWidgetUrl = widgetUrl.replace(/\/+$/, "");

  var position = scriptTag.getAttribute("data-position") === "bottom-left" ? "bottom-left" : "bottom-right";
  var offsetAttr = parseInt(scriptTag.getAttribute("data-offset"), 10);
  var OFFSET = (isFinite(offsetAttr) && offsetAttr >= 0 ? offsetAttr : 20) + "px";
  var zIndexAttr = parseInt(scriptTag.getAttribute("data-z-index"), 10);
  var Z_INDEX = String(isFinite(zIndexAttr) && zIndexAttr > 0 ? zIndexAttr : 999999);

  var BUBBLE_SIZE = "64px";
  var DESKTOP_WIDTH = "380px";
  var DESKTOP_HEIGHT = "600px";
  var MOBILE_BREAKPOINT = 480;

  var MOBILE_HEIGHT = (window.CSS && window.CSS.supports && window.CSS.supports("height", "100dvh"))
    ? "100dvh"
    : "100vh";

  var SIDE_PROP = position === "bottom-left" ? "left" : "right";
  var OTHER_SIDE_PROP = position === "bottom-left" ? "right" : "left";

  var iframe = document.createElement("iframe");
  iframe.src = normalizedWidgetUrl + "/";
  iframe.title = "Chat widget";
  iframe.setAttribute("aria-label", "Chat support");
  iframe.setAttribute("allow", "clipboard-write");

  iframe.style.position = "fixed";
  iframe.style.bottom = OFFSET;
  iframe.style[SIDE_PROP] = OFFSET;
  iframe.style[OTHER_SIDE_PROP] = "auto";
  iframe.style.width = BUBBLE_SIZE;
  iframe.style.height = BUBBLE_SIZE;
  iframe.style.border = "none";
  iframe.style.borderRadius = "9999px";
  iframe.style.overflow = "hidden";
  iframe.style.boxShadow = "0 8px 24px rgba(15, 23, 42, 0.18)";
  iframe.style.zIndex = Z_INDEX;
  iframe.style.colorScheme = "normal";
  iframe.style.display = "block";
  iframe.style.margin = "0";
  iframe.style.padding = "0";
  iframe.style.maxWidth = "none";
  iframe.style.maxHeight = "none";
  iframe.style.background = "transparent";
  iframe.style.transition = "box-shadow 0.15s ease";

  document.body.appendChild(iframe);

  function isMobile() {
    return window.innerWidth <= MOBILE_BREAKPOINT;
  }

  function openPanel() {
    if (isMobile()) {
      iframe.style.bottom = "0px";
      iframe.style[SIDE_PROP] = "0px";
      iframe.style.width = "100vw";
      iframe.style.height = MOBILE_HEIGHT;
      iframe.style.borderRadius = "0px";
    } else {
      iframe.style.bottom = OFFSET;
      iframe.style[SIDE_PROP] = OFFSET;
      iframe.style.width = "min(" + DESKTOP_WIDTH + ", calc(100vw - " + OFFSET + " * 2))";
      iframe.style.height = "min(" + DESKTOP_HEIGHT + ", calc(100vh - " + OFFSET + " * 2))";
      iframe.style.borderRadius = "16px";
    }
    iframe.style.boxShadow = "0 20px 48px rgba(15, 23, 42, 0.28)";
  }

  function closePanel() {
    iframe.style.bottom = OFFSET;
    iframe.style[SIDE_PROP] = OFFSET;
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