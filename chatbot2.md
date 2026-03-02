# Proposal: `@@chatbot` for `zopyx.surveyjs`

## Goal
Add a dedicated browser view `@@chatbot` that answers:

- How this add-on works
- How to use and configure it in Plone
- Questions about SurveyJS documentation

The chatbot should be documentation-grounded (RAG) and avoid hallucinations by citing sources.

## Recommended Approach
Implement a **RAG assistant** in the existing Plone add-on, reusing current AI settings (`ai_model`, `ai_api_key`, `ollama_url`) and coding patterns from `@@ai`.

Why this fits this project:

- Existing AI plumbing already exists (`browser/services/ai.py`, `browser/survey_ai.py`).
- Documentation corpus is local (`README.md`, `docs/`, `AI.md`, `EMBEDDING.md`, etc.).
- SurveyJS docs can be indexed as an additional curated source.
- Buildout-based project benefits from a local/persistent vector store (no external service required).

## Functional Scope (MVP)
1. `@@chatbot` page (authenticated users, `zope2.View`).
2. `@@chat-api` JSON endpoint (`POST`) for chat messages.
3. Retrieval from:
   - Local project docs (`README.md`, `docs/**/*`, `AI.md`, `EMBEDDING.md`, `DEVELOP.rst`)
   - Optional SurveyJS docs whitelist (selected URLs).
4. Responses include:
   - Answer text
   - Source list (file path or URL)
   - Confidence hint (`high` / `medium` / `low` based on retrieval scores)
5. Basic chat history in browser session (no DB persistence in MVP).

## Architecture
Suggested package layout:

```text
src/zopyx/surveyjs/chatbot/
  __init__.py
  indexer.py          # local + remote docs ingestion/chunking
  vector_store.py     # persistent embeddings store
  retriever.py        # top-k retrieval + ranking
  engine.py           # prompt assembly + LLM call + source formatting
  policies.py         # guardrails and allowed-topic checks
```

Plone/browser integration:

```text
src/zopyx/surveyjs/browser/
  chatbot.py          # @@chatbot + @@chat-api + @@chatbot-mgmt
  chatbot.pt          # dedicated chat UI
  static/chatbot.js
  static/chatbot.css
```

ZCML registrations:

- `@@chatbot` on `ISurvey` (and optionally site root)
- `@@chat-api` on `ISurvey` (or folderish root if global chatbot is preferred)
- `@@chatbot-mgmt` for reindex/stats/reset (Manager only)

## Retrieval and Prompt Strategy
1. Retrieve top-k chunks (`k=5..8`) from local docs + SurveyJS docs.
2. Build prompt with:
   - Assistant role: “expert for zopyx.surveyjs + SurveyJS docs”
   - Current context: object title, current URL/view, user role
   - Retrieved chunks with source metadata
3. Enforce response policy:
   - If evidence is weak, say so explicitly
   - Never invent settings/view names/endpoints
   - Always include “Sources” section

## Security and Permissions
- Keep `@@chatbot` authenticated by default.
- Keep `@@chat-api` authenticated; optionally Manager/Editor only in first release.
- Do not expose secret settings or raw API keys in any response.
- Restrict remote indexing to a static SurveyJS allowlist.
- Add request throttling/rate-limit per session or user.

## Configuration
Reuse existing AI registry settings first. Add only if needed:

- `chatbot_enabled` (bool)
- `chatbot_max_context_chunks` (int, default 6)
- `chatbot_allow_remote_docs` (bool)
- `chatbot_docs_indexed` (bool/status marker)

Keep new settings minimal to avoid control-panel complexity.

## Data/Index Lifecycle
- Index location: under `var/` (persistent across restarts).
- Management endpoint:
  - Reindex project docs
  - Reindex SurveyJS allowlist
  - Show stats (#docs, #chunks, last indexed)
- Reindex trigger options:
  - Manual from `@@chatbot-mgmt` (MVP)
  - Optional periodic job later

## Testing Plan
Add tests similar to existing browser/service tests:

1. `test_chatbot_view_permissions.py`
2. `test_chat_api_validation.py`
3. `test_chat_retrieval_sources.py`
4. `test_chat_policies.py`
5. `test_chatbot_mgmt.py`

Focus assertions:

- Unauthorized users blocked
- Empty prompt rejected
- Sources are returned
- Non-domain questions are refused or redirected to supported topics
- Reindex flow works

## Rollout Plan
1. **Phase 1 (MVP, 2-3 days):**
   - `@@chatbot` UI + `@@chat-api`
   - Local docs indexing only
   - Sources in answers
2. **Phase 2 (1-2 days):**
   - SurveyJS remote docs allowlist indexing
   - mgmt page and stats
3. **Phase 3 (optional):**
   - Streaming responses (SSE)
   - Follow-up suggestions
   - Per-survey context enrichment (form JSON summary)

## Recommendation
Start with a **strict, local-doc-first MVP** and source citations. This gives fast value, low risk, and aligns with this add-on’s existing architecture. Then add SurveyJS remote indexing behind an explicit toggle once the core QA quality is verified.
