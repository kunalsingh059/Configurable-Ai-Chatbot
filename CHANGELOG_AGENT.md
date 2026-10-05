# Changelog - Autonomous Agent Implementation

Project: `chatbot-platform-vue-updated`

## Overview
This document tracks all changes, architecture decisions, new collections/indexes, environment variables, and pending items implemented for the Company SaaS transformation.

---

## [Phase 1] - In Progress

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
- **Status:** Implementing
- **Files Modified:**
  - `app/db.py`: Added `feedback_collection`.
  - `app/models.py`: Added `FeedbackModel` with rating validation (`up` / `down`) and length limits.
  - `app/main.py`: Added unique index on `(tenant_id, message_id)` and endpoint `POST /api/feedback`. Added `message_id` generation in SSE `/chat` stream.
  - `widget-vue/src/composables/useChat.js`: Stored `message_id` on assistant bubbles, added `submitFeedback()`.
  - `widget-vue/src/components/MessageBubble.vue`: Added thumbs-up / thumbs-down buttons with active states and accessible tooltips.
  - `widget-vue/src/components/MessageList.vue`: Forwarded rate event.
  - `widget-vue/src/App.vue`: Wired rating handler.
- **Database Collections & Indexes:**
  - `feedback`:
    - Unique compound index: `[("tenant_id", 1), ("message_id", 1)]`
    - Date index: `[("tenant_id", 1), ("created_at", -1)]`
- **Security & Multi-Tenancy:**
  - Validated by `get_tenant_from_api_key` (`X-API-Key` + `X-Embed-Origin` against allowed domains).
  - Cross-tenant tampering prevented: upsert strictly filters by `tenant_id`.
