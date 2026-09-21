# Chatbot Platform - Day 1-2 Core Loop

## What this proves
The full tool-calling loop: user message -> Claude decides to call a tool ->
we hit a real API (fakestoreapi.com) -> result goes back to Claude -> natural
language answer. This is the core mechanic the entire product is built on.

## Setup

1. Create a virtual environment and install dependencies:
   ```
   python3 -m venv venv
   source venv/bin/activate   # on Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. Copy `.env.example` to `.env` and add your real Anthropic API key:
   ```
   cp .env.example .env
   ```

3. Run the server:
   ```
   uvicorn app.main:app --reload --port 8001
   ```

4. Open `widget/widget.html` directly in your browser (just double-click it,
   or use VSCode's "Live Server" extension). Try:
   - "tell me about product 1"
   - "show me electronics"
   - "what's the price of the third item you showed me?" (tests conversation memory)

## Test without the widget (curl)
```
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id": "test1", "message": "tell me about product 3"}'
```

## What changed (Day 3-4 update)
- Tools now live in a SQLite database (`chatbot.db`, auto-created on first run)
  instead of hardcoded Python, via `app/models.py` (SQLAlchemy model) and
  `app/dynamic_tools.py` (generic schema builder + HTTP executor).
- Two starter tools are auto-seeded on startup for tenant "default" so you
  have something to test immediately.
- Admin CRUD API added: `GET/POST/PUT/DELETE /admin/tools` - this is what
  the future Vue admin panel will call to let a non-technical admin add
  their own APIs without touching code.
- `/chat` now accepts an optional `tenant_id` (defaults to "default").

### Try adding a tool yourself (no code changes needed)
```
curl -X POST http://localhost:8000/admin/tools \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "default",
    "name": "get_all_products",
    "description": "List all products available in the store. Use this when the user asks what products are available in general.",
    "method": "GET",
    "url_template": "https://fakestoreapi.com/products",
    "params_schema": {"type": "object", "properties": {}, "required": []}
  }'
```
Then ask the widget "what products do you have?" — no restart needed.

## What's next (Day 5)
- Swap in-memory SESSIONS dict for Redis (conversation persistence across restarts)
- Add tenant lookup (name/logo/primary color) for widget branding
- Start RAG (Voyage AI + Qdrant) for FAQ/doc-based answers
