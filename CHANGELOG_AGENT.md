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
