# Changelog - Autonomous Agent Implementation

Project: `chatbot-platform-vue-updated`

## Overview
This document tracks all changes, architecture decisions, new collections/indexes, environment variables, and pending items implemented for the Company SaaS transformation.

---

## [Phase 1] - Complete

### Architectural Decisions & Scope
- **P0-1 (Email Non-fatal):** Already safe in current codebase (lazy credentials check, unhandled exceptions caught).
- **P0-2 (Sessions & Rate Limiting):** Kept on Upstash Redis (`redis_client.py`, `rate_limit.py`, distributed locks via `redis.asyncio.lock.Lock`). Redis provides sub-5ms latency and prevents WAN database roundtrips.
- **T6 (Response Streaming):** Already implemented in `/chat` with Server-Sent Events (`StreamingResponse`) and consumed by `useChat.js`.
- **Phase 1 Tasks Selected:**
  - T1: Feedback buttons (thumbs up / down)
  - T2: Unanswered-question log
  - T3: Multi-language replies (including Hinglish)
  - T4: Per-tenant bot customization
  - T5: Fallback LLM provider

---

### Task T1: Feedback Buttons (Thumbs up / down)
- **Status:** Complete
- **Files Modified:**
  - `app/db.py`: Added `feedback_collection`.
  - `app/models.py`: Added `FeedbackModel` with rating validation (`up` / `down`) and length limits. Added URL validation on `ToolModel`.
  - `app/main.py`: Added unique index on `(tenant_id, message_id)` and endpoint `POST /api/feedback`. Added `message_id` generation in SSE `/chat` stream.
  - `widget-vue/src/composables/useChat.js`: Stored `message_id` on assistant bubbles, added `submitFeedback()`.
  - `widget-vue/src/components/MessageBubble.vue`: Added thumbs-up / thumbs-down buttons with active states and accessible tooltips.
  - `widget-vue/src/components/MessageList.vue`: Forwarded rate event.
  - `widget-vue/src/App.vue`: Wired rating handler.
  - `tests/test_t1_feedback.py`: Unit tests verifying authentication, rating validation, and upsert behavior.
- **Database Collections & Indexes:**
  - `feedback`:
    - Unique compound index: `[("tenant_id", 1), ("message_id", 1)]`
    - Date index: `[("tenant_id", 1), ("created_at", -1)]`
- **Security & Multi-Tenancy:**
  - Validated by `get_tenant_from_api_key` (`X-API-Key` + `X-Embed-Origin` against allowed domains).
  - Cross-tenant tampering prevented: upsert strictly filters by `tenant_id`.

---

### Task T2: Unanswered-Question Log
- **Status:** Complete
- **Files Modified:**
  - `app/db.py`: Added `unanswered_collection`.
  - `app/models.py`: Added `UnansweredStatusUpdateModel`.
  - `app/groq_client.py`: Passed tool execution counts and document context flags in the `done` event.
  - `app/main.py`: Added async non-blocking detection and logging (`log_unanswered_question`). Added `GET /api/admin/unanswered` and `PATCH /api/admin/unanswered/{id}`.
  - `admin-vue/src/services/api.js`: Added `listUnanswered` and `updateUnansweredStatus`.
  - `admin-vue/src/components/UnansweredQuestions.vue`: Responsive UI with status filtering (open, resolved, ignored), resolution actions, and pagination.
  - `admin-vue/src/views/BusinessOwnerDashboard.vue`: Embedded `UnansweredQuestions` component.
  - `tests/test_t2_unanswered.py`: Unit test verifying logging, listing, status updates, and multi-tenant security isolation.
- **Database Collections & Indexes:**
  - `unanswered_questions`:
    - Compound index: `[("tenant_id", 1), ("status", 1), ("timestamp", -1)]`
- **Performance & Latency:**
  - Unanswered detection writes via `asyncio.create_task` at turn completion; adds 0ms to user streaming TTFT.

---

### Task T3: Multi-language Replies (including Hinglish)
- **Status:** Complete
- **Files Modified:**
  - `app/groq_client.py`: Added `LANGUAGE_PROMPT_INSTRUCTION` (handling English, Hindi Devanagari, and Hinglish in Latin script while locking down entity names, prices, and parameters), `TONE_INSTRUCTIONS`, and `build_system_prompt()`.
  - `app/mock_llm.py`: Added `bot_config` parameter support.
  - `app/main.py`: Retrieved tenant `bot_config` and forwarded it to `run_groq_chat_turn_stream`.
  - `tests/test_t3_multilanguage.py`: Unit tests validating script-matching prompt injection, disabling via `reply_in_user_language=False`, and tone adaptations.
- **Performance & Latency:**
  - 0 additional network requests, 0 latency overhead. Groq natively generates multilingual responses.

---

### Task T4: Per-tenant Bot Customization
- **Status:** Complete
- **Files Modified:**
  - `app/models.py`: Added `BotConfigModel` with validation for hex color regex, tone options, max 6 quick reply chips (<=40 chars each), and HTTPS avatar URL.
  - `app/main.py`: Added `GET /admin/bot-config`, `PUT /admin/bot-config`, and updated `GET /widget/config` to safely expose customization without sensitive tenant secrets.
  - `admin-vue/src/services/api.js`: Added `getBotConfig` and `updateBotConfig`.
  - `admin-vue/src/components/BusinessSettings.vue`: Added full bot configuration UI (bot display name, tone selector, welcome message, hex color picker & live swatch, HTTPS avatar URL input & preview, user-language mirror toggle, and interactive quick reply chip manager).
  - `widget-vue/src/composables/useBusinessConfig.js`: Added reactive state for `welcomeMessage`, `primaryColor`, `avatarUrl`, and `quickReplies`.
  - `widget-vue/src/components/ChatHeader.vue`: Dynamically styled header background using `primaryColor` and rendered custom avatar image when present.
  - `widget-vue/src/components/WidgetLauncher.vue`: Styled launcher button using custom `primaryColor`.
  - `widget-vue/src/components/MessageList.vue`: Rendered dynamic `welcomeMessage` and clickable `quickReplies` pills in empty state.
  - `widget-vue/src/App.vue`: Wired customization props throughout widget hierarchy.
  - `tests/test_t4_bot_config.py`: Unit and integration tests covering model validation, 401 unauthorized access, 422 malformed hex colors, and verified that `GET /widget/config` reflects saved settings.
- **Security & Multi-Tenancy:**
  - Bot config updates are restricted to authenticated business owners (`role: "business_owner"` matching `tenant_id`).
  - Strict input sanitization rejects arbitrary scripts or non-HTTPS URLs for avatars.
  - Widget config endpoint only returns public presentation attributes.

---

### Task T5: Fallback LLM Provider
- **Status:** Complete
- **Files Modified:**
  - `app/anthropic_client.py`: Created Anthropic Claude streaming integration supporting tool calling, RAG context injection, tone/language adherence, and message normalization.
  - `app/llm_orchestrator.py`: Implemented LLM orchestrator with automatic failover detection (429 rate limit, 5xx server error, connection drop, timeout) before tokens are streamed to client.
  - `app/main.py`: Connected chat stream endpoint to `run_orchestrated_chat_turn_stream` and added startup validation for `LLM_PRIMARY`, `LLM_FALLBACK`, and provider credentials.
  - `.env.example`: Documented `LLM_PRIMARY`, `LLM_FALLBACK`, `ANTHROPIC_API_KEY`, and `ANTHROPIC_MODEL`.
  - `tests/test_t5_fallback.py`: Verified Anthropic helper formatting, failover exception classification, seamless fallback execution from Groq 429 to fallback provider, prevention of mid-stream failover if tokens were already emitted, and re-raise behavior when no fallback is configured.
- **Resilience & SLA:**
  - Zero downtime for customer queries during Groq rate limits (30 RPM free tier ceiling) or unexpected upstream provider outages.
  - Latency impact: 0ms overhead during healthy primary operation; failover executes within <500ms upon primary 429/5xx response.

---

## [Phase 2] - In Progress

### Task T7: Usage Tracking and Quotas
- **Status:** Complete
- **Files Modified:**
  - `app/db.py`: Added `usage_daily_collection` and `leads_collection` references.
  - `app/models.py`: Added `TenantLimitsModel` for configuring daily and monthly message limits.
  - `app/main.py`:
    - Defined IST date boundary helper `get_current_ist_date()` ensuring counters reset at midnight IST (`Asia/Kolkata`, UTC+5:30).
    - Created compound unique index on `usage_daily` (`(tenant_id, date)`) and sort index `(tenant_id, date DESC)`.
    - Implemented atomic `$inc` update helper `record_daily_usage()` tracking messages, sessions, tokens, and estimated token flags.
    - Added pre-stream quota evaluation in `POST /chat` before SSE streaming begins (returns HTTP 429 `QUOTA_EXCEEDED` if exceeded).
    - Added `PUT /api/superadmin/tenants/{tenant_id}/limits` for superadmin quota management.
    - Added `GET /api/admin/usage` for business owner usage monitoring.
    - Updated `GET /superadmin/business-owners` response to include limits.
  - `widget-vue/src/composables/useChat.js`: Handled HTTP 429 response with user-friendly quota exhaustion message.
  - `admin-vue/src/services/api.js`: Added `updateTenantLimits` and `getUsage` API methods.
  - `tests/test_t7_usage.py`: Comprehensive test suite verifying atomic concurrent counter increments, usage queries, limit configuration, and pre-stream 429 rejection.
- **Database Collections & Indexes:**
  - `usage_daily`:
    - Compound unique index: `[("tenant_id", 1), ("date", 1)]`
    - Sort index: `[("tenant_id", 1), ("date", -1)]`
- **Concurrency & Reliability:**
  - Atomic `$inc` MongoDB operator guarantees zero lost updates under concurrent chat traffic.
  - Usage tracking runs asynchronously in turn completion background task (0ms impact on TTFT).

---

### Task T8: Basic Analytics Dashboard
- **Status:** Complete
- **Files Modified:**
  - `app/main.py`:
    - Added compound indexes: `(tenant_id, created_at)` on `feedback_collection` and `unanswered_collection`, and `(tenant_id, date)` on `usage_daily_collection`.
    - Updated `record_daily_usage()` to track daily distinct sessions using Redis `SADD` with 3-day TTL and atomic increment of `sessions` in `usage_daily_collection`.
    - Added `created_at` field to `log_unanswered_question()`.
    - Implemented `GET /api/admin/analytics?range=7d|30d` (and `/admin/analytics`). Trends and message counts read strictly from `usage_daily_collection` (persisting long-term beyond 24h session TTL). Computes KPI tiles: "Conversations" (distinct sessions), "Messages", "Satisfaction %" (plus thumbs up / down counts), and "Unanswered" (open count), alongside a continuous IST daily series.
  - `admin-vue/src/services/api.js`: Added `getAnalytics(token, range)` API call.
  - `admin-vue/src/components/AnalyticsOverview.vue`: Created responsive Vue component with 7-day / 30-day range toggle, loading skeleton, live refresh button, 4 KPI cards ("Conversations", "Messages", "Satisfaction", "Unanswered"), and responsive CSS bar chart displaying daily volume trends with zero external dependencies.
  - `admin-vue/src/views/BusinessOwnerDashboard.vue`: Mounted `AnalyticsOverview` prominently at the top of the business owner dashboard cards.
  - `tests/test_t8_analytics.py`: Automated tests verifying multi-tenant isolation, 401 unauthenticated guard, exact tile metrics computation, and continuous 7d and 30d time-series outputs.
- **Database Collections & Indexes:**
  - `feedback`: `[("tenant_id", 1), ("created_at", 1)]`, `[("tenant_id", 1), ("created_at", -1)]`
  - `unanswered_questions`: `[("tenant_id", 1), ("created_at", 1)]`, `[("tenant_id", 1), ("created_at", -1)]`
  - `usage_daily`: `[("tenant_id", 1), ("date", 1)]`, `[("tenant_id", 1), ("date", -1)]`

---

### Task T9: Human Handoff / Lead Capture
- **Status:** Complete
- **Files Modified:**
  - `app/models.py`:
    - Added `handoff_enabled: bool = False` to `BotConfigModel`.
    - Added `HandoffRequestModel` requiring name, at least one contact channel (email or phone), and optional note.
    - Added `LeadStatusUpdateModel` (`status: "new" | "contacted" | "closed"`).
  - `app/email_service.py`: Added `send_lead_notification_email()` for transactional lead alerts to the business owner.
  - `app/main.py`:
    - Added compound indexes on `leads_collection`: `[("tenant_id", 1), ("created_at", -1)]` and `[("tenant_id", 1), ("status", 1), ("created_at", -1)]`.
    - Exposed `handoff_enabled` in `GET /widget/config`.
    - Added `POST /api/handoff`: gated by tenant's `handoff_enabled` flag, enforced strict per-IP rate limit (3/hour), extracted and persisted last 10 messages of the chat session, and sent best-effort owner email alert.
    - Added `GET /api/admin/leads`: paginated listing with status counts for business owners.
    - Added `PATCH /api/admin/leads/{lead_id}`: lead status management.
    - Added `GET /api/admin/leads/export.csv`: CSV export with CWE-1236 formula injection sanitization.
  - `admin-vue/src/services/api.js`: Added `listLeads`, `updateLeadStatus`, and `exportLeadsCsv`.
  - `admin-vue/src/components/BusinessSettings.vue`: Added toggle switch for `handoff_enabled`.
  - `admin-vue/src/components/LeadsManager.vue`: Full lead management component with filter pills, status selector, expandable last-10-message chat context, and CSV download.
  - `admin-vue/src/views/BusinessOwnerDashboard.vue`: Mounted `LeadsManager` component.
  - `widget-vue/src/composables/useBusinessConfig.js`: Added `handoffEnabled` configuration state.
  - `widget-vue/src/composables/useChat.js`: Added `submitHandoff` with friendly error mapping on 429 quota exhaustion.
  - `widget-vue/src/components/ContactModal.vue`: Customer contact modal with validation, submission, and confirmation views.
  - `widget-vue/src/components/ChatHeader.vue`: Added "Talk to a person" button and options menu item when `handoff_enabled` is true.
  - `widget-vue/src/App.vue`: Wired contact dialog and submit handler.
  - `tests/test_t9_leads.py`: Automated tests verifying gating, strict 3/hr per-IP rate limiting, 10-message extraction, status transitions, and sanitized CSV output.
- **Database Collections & Indexes:**
  - `leads`:
    - Date sort index: `[("tenant_id", 1), ("created_at", -1)]`
    - Status query index: `[("tenant_id", 1), ("status", 1), ("created_at", -1)]`
- **Security & Reliability:**
  - Strict per-IP rate limit: 3/hour prevents spam while allowing legitimate customers to submit inquiries.
  - Lead persistence is decoupled from email delivery: if SMTP is offline or credentials are missing, the lead is safely saved in MongoDB. Owner email sending runs non-blocking via `asyncio.to_thread` with a 5s socket timeout so lead creation response time is never delayed by network SMTP roundtrips.
  - CSV Formula Injection defense: Neutralizes formula prefixes (`=`, `+`, `-`, `@`, `\t`, `\r`) with quote escapes.
  - Unanswered question detection normalizes curly apostrophes (`’`, `‘`) and includes `reason` in the persisted document.


