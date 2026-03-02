# Chatbot Feature Specification

A RAG-based (Retrieval-Augmented Generation) chat assistant for `zopyx.surveyjs` that answers questions about SurveyJS form building in context of the current Plone view.

---

## Architecture

### Module Layout

```
src/zopyx/surveyjs/
├── chatbot/
│   ├── __init__.py           # exports: VectorStore, DocumentationIndexer, ChatEngine, ChatContext
│   ├── vector_store.py       # ChromaDB embedded vector store
│   ├── embeddings.py         # llm-based embedding provider + ChromaDB adapter
│   ├── indexer.py            # Documentation indexer (local files + remote URLs)
│   └── chat_engine.py        # RAG pipeline: retrieval + LLM generation
└── browser/
    ├── chatbot.py             # Plone browser views
    ├── static/chatbot.css     # Chat widget styles
    └── templates/
        ├── chat_widget.pt     # Embeddable floating chat widget
        └── chat_standalone.pt # Standalone chat page
```

### Dependencies

All declared in `setup.py`:

| Package | Purpose |
|---------|---------|
| `chromadb` | Embedded vector store (SQLite backend) |
| `llm` | LLM abstraction layer (generation + embeddings) |
| `llm-ollama` | Ollama plugin for local models |
| `llm-anthropic` | Anthropic/Claude plugin |
| `llm-deepseek` | DeepSeek plugin |
| `beautifulsoup4` | HTML parsing for remote doc indexing |
| `requests` | HTTP fetching for remote doc indexing |
| `tiktoken` | Tokenization utilities |

---

## Components

### VectorStore (`chatbot/vector_store.py`)

ChromaDB-backed persistent vector store.

- **Default storage path**: `var/surveyjs_chatbot/` (relative to buildout root)
- **Default collection**: `surveyjs_docs`
- **Backend**: SQLite (no external service required)
- **Similarity metric**: cosine distance

Key methods:

| Method | Description |
|--------|-------------|
| `add_documents(documents, ids, metadatas)` | Add text chunks in batches of 100 |
| `query(query_text, n_results, filter_metadata)` | Semantic search, returns list of `{document, metadata, distance}` |
| `get_stats()` | Returns `{collection, document_count, persist_directory}` |
| `reset()` | Deletes all collections |

### EmbeddingProvider (`chatbot/embeddings.py`)

Wraps the `llm` module for generating text embeddings.

- **Default hosted model**: `text-embedding-3-small` (OpenAI)
- **Default local model**: `nomic-embed-text` (Ollama)
- Auto-prefixes Ollama model names with `ollama/`
- `ChromaEmbeddingFunction` wraps `EmbeddingProvider` into ChromaDB's callable interface

> **Note**: ChromaDB currently uses its own default embedding function (not wired to `EmbeddingProvider` unless explicitly passed at collection creation).

### DocumentationIndexer (`chatbot/indexer.py`)

Indexes documentation sources into the vector store.

**Text chunking** (`TextChunker`):
- Target chunk size: 1000 characters
- Overlap: 200 characters
- Breaks at sentence boundaries (`. `, `? `, `! `, `\n\n`), falls back to word boundaries

**Index sources**:

1. **`index_local_files(file_paths, source_type)`** — reads UTF-8 text files, extracts markdown `# Title`, chunks and stores with metadata `{source, source_type, title, chunk_index, total_chunks}`

2. **`index_remote_docs(urls, max_pages=50)`** — fetches SurveyJS documentation URLs, strips nav/footer/header/aside, extracts main content, chunks and stores. Default URLs:
   - `https://surveyjs.io/form-library/documentation/overview`
   - `https://surveyjs.io/survey-creator/documentation/overview`
   - `https://surveyjs.io/form-library/documentation/design-survey/create-a-simple-survey`
   - `https://surveyjs.io/form-library/documentation/design-survey/question-types`
   - `https://surveyjs.io/form-library/documentation/design-survey/conditional-logic`
   - `https://surveyjs.io/form-library/documentation/design-survey/validate-input`
   - `https://surveyjs.io/form-library/documentation/design-survey/accessibility`
   - `https://surveyjs.io/survey-creator/documentation/customize-question-types`

   > **Known bug**: `documents.append(chunk)` should be `documents.append(chunk["content"])` — chunk is a dict but a string is expected by ChromaDB.

3. **`index_project_docs(project_root=None)`** — auto-detects project root, indexes:
   - All `*.md` and `docs/**/*.md` files as `project_docs`
   - Up to 50 Python source files (excluding test files) as `api_docs` — extracts module docstrings and class/function docstrings

### ChatContext (`chatbot/chat_engine.py`)

Dataclass carrying per-request context:

| Field | Type | Description |
|-------|------|-------------|
| `current_view` | `str` | Active view: `@@editor`, `@@results`, `@@viewer`, `@@ai`, `@@view` |
| `survey_json` | `dict` | Parsed form JSON (editor view only) |
| `survey_title` | `str` | Title of the current survey |
| `user_role` | `str` | `Manager`, `Editor`, or `Viewer` |
| `conversation_history` | `list` | List of `{role, content}` dicts |

`to_prompt_context()` serialises non-null fields into a human-readable string for prompt injection. If a form JSON is present it summarises page and question counts.

### ChatEngine (`chatbot/chat_engine.py`)

RAG pipeline combining vector retrieval and LLM generation.

**Constructor parameters**:

| Parameter | Description |
|-----------|-------------|
| `vector_store` | `VectorStore` instance |
| `embedding_provider` | Optional custom `EmbeddingProvider` |
| `model_name` | LLM model name (e.g. `gpt-4o`, `claude-sonnet-4-6`, `ollama/llama3.2`) |
| `api_key` | API key for OpenAI or Anthropic |
| `ollama_url` | Ollama server URL (sets `OLLAMA_HOST` env var) |

**`chat(message, context, n_results=5)`** — returns:
```json
{
  "response": "...",
  "sources": [{"source": "...", "source_type": "...", ...}],
  "context_used": {"view": "@@editor", "docs_retrieved": 5}
}
```

**`stream_chat(message, context, n_results=5)`** — generator yielding text chunks. Uses `response.text_iter()` if available, falls back to full response.

**`suggest_followups(current_topic, context)`** — returns up to 3 follow-up question strings.

**Prompt structure** (assembled in order):
1. System prompt (role definition, guidelines, language instruction)
2. Current context block (`--- Current Context ---`)
3. Retrieved documentation chunks (`--- Relevant Documentation ---`, up to 800 chars each)
4. Last 3 conversation history exchanges
5. User question

**Model selection logic**:
- If `ollama_url` set → prefix model name with `ollama/`, default to `ollama/llama3.2`
- If `api_key` set → inject as `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` based on model name
- Falls back to `llm.get_default_model()` if no model configured

---

## Browser Views

Registered in `browser/configure.zcml`.

### `@@chat-api` — `ChatAPIView`

**Permission**: `zope2.View` (authenticated users only — anonymous blocked at runtime)

| Sub-path | Method | Description |
|----------|--------|-------------|
| (root) | POST | Handle chat message |
| `/stats` | GET | Vector store statistics |
| `/index` | POST | Trigger indexing (Manager only) |

**POST body**:
```json
{
  "message": "How do I add a rating question?",
  "stream": false,
  "current_view": "@@editor",
  "survey_title": "My Survey",
  "survey_json": {...},
  "user_role": "Editor",
  "history": [
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."}
  ]
}
```

**Streaming**: set `"stream": true` to receive `text/event-stream` SSE:
```
data: {"chunk": "partial text"}
data: {"chunk": " more text"}
data: {"done": true, "response": "full response text"}
```

LLM settings are loaded from the Plone registry (`IFormsSettings`): `ai_model`, `ai_api_key`, `ollama_url`.

### `@@chat-widget` — `ChatWidgetView`

**Permission**: `zope2.View`
Renders a floating chat widget embedded in the Plone master template. Loads `chatbot.css`. Widget is context-aware — detects current view from URL and injects survey title and JSON automatically.

**Widget UI features**:
- Floating toggle button (bottom-right)
- Message thread with simple markdown rendering (code blocks, inline code, bold)
- 3 default suggestion buttons: "How do I add a matrix?", "Enable validation", "Export results"
- Auto-resizing textarea input, Enter to send (Shift+Enter for newline)
- Reset/clear conversation button
- "Thinking..." status indicator
- `window.surveyjsChat` debug handle exposed

### `@@chat-support` — `ChatStandaloneView`

**Permission**: `zope2.View`, registered on `IPloneSiteRoot`
Standalone chat page at the site root.

### `@@chatbot-mgmt` — `ChatbotManagementView`

**Permission**: `cmf.ManagePortal`, registered on `IPloneSiteRoot`

| Sub-path | Description |
|----------|-------------|
| `/index-docs` | Index project documentation (local MD + Python source files) |
| `/reset` | Delete all documents from vector store |
| `/stats` | Vector store statistics (requires `cmf.ModifyPortalContent`) |
| (root) | Print help text |

After indexing, sets `IFormsSettings.chatbot_docs_indexed = True` in registry.

---

## Configuration (Plone Registry)

Via `@@forms-settings` control panel, stored in `IFormsSettings`:

| Registry key | Description |
|--------------|-------------|
| `ai_model` | LLM model name |
| `ai_api_key` | API key (OpenAI / Anthropic) |
| `ollama_url` | Ollama server URL |
| `chatbot_enabled` | Enable/disable chatbot widget |
| `chatbot_docs_indexed` | Flag set after successful indexing |

---

## Setup / First-Time Quickstart

```bash
# 1. Install missing dependencies (not yet present in venv)
.venv/bin/pip install chromadb beautifulsoup4 requests

# 2. Restart Plone

# 3. Index project documentation (requires Manager)
curl -X POST -u admin:admin http://localhost:8080/Plone/@@chatbot-mgmt/index-docs

# 4. Verify indexing
curl -u admin:admin http://localhost:8080/Plone/@@chatbot-mgmt/stats

# 5. Chat widget appears automatically on survey pages for authenticated users
#    Standalone chat at: http://localhost:8080/Plone/@@chat-support
```

---

## Known Bugs

| Location | Description |
|----------|-------------|
| `indexer.py:206` | `index_remote_docs`: `documents.append(chunk)` should be `documents.append(chunk["content"])` — chunk is a dict `{"content": str, "title": str}`, not a string. Only triggered when calling `index_remote_docs()` directly. |
