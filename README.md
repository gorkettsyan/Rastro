# Rastro

An AI-powered document search and knowledge assistant for organizations. Upload documents from Google Drive, Gmail, or directly; ask questions in natural language; and get grounded, cited answers from your own content.

---

## Search Algorithm

Rastro uses a **hybrid retrieval pipeline** that combines vector search, keyword search, fusion, and neural reranking.

### Pipeline overview

```
User query
    │
    ▼
1. Query rewriting (GPT-4o-mini)
    │  Short or vague queries are expanded into better search terms.
    │  Queries ≥ 5 words pass through unchanged.
    │
    ▼
2. Embedding (text-embedding-3-small, 1536 dims)
    │
    ├──────────────────────────────────┐
    ▼                                  ▼
3a. Vector search (pgvector)        3b. BM25 / full-text search (PostgreSQL tsvector)
    Cosine similarity over              websearch_to_tsquery with Spanish + English
    chunk embeddings. Top 20.           text configurations. Top 20.
    Filtered by score ≥ 0.35.
    │                                  │
    └──────────────┬───────────────────┘
                   ▼
           4. Reciprocal Rank Fusion (RRF, k=60)
               Merges both ranked lists.
               Chunks appearing in both lists rank highest.
               Formula: score(chunk) = Σ 1 / (k + rank_i)
                   │
                   ▼
           5. Cohere reranker (rerank-multilingual-v3.0)
               Re-scores fused top-50 chunks against the original query.
               Returns top 5. Falls back to RRF order if unavailable.
                   │
                   ▼
           6. GPT-4o answer generation (streaming)
               System prompt forces language consistency.
               Sources cited as [Source N].
                   │
                   ▼
           SSE stream → frontend (tokens → sources → done)
```

### Document ingestion

When a document is ingested (from Drive, Gmail, or direct upload):

1. **Chunking** — `SentenceSplitter` (llama-index) splits text into 512-token chunks with 50-token overlap.
2. **Embedding** — Each chunk is embedded with `text-embedding-3-small`.
3. **BM25 index** — `content_tsv` column (`tsvector`) is populated at write time with a generated column combining Spanish and English configurations.
4. **Storage** — Chunks stored in PostgreSQL with `embedding vector(1536)` (pgvector) and `content_tsv tsvector`.

---

## Memory Algorithm

Rastro maintains a persistent memory layer so the assistant can recall user context across conversations.

### Two types of memory

| Type | What it stores | Examples |
|------|---------------|---------|
| **Durable facts** | Long-term user attributes | "Works in corporate law", "Clients are Spanish SMEs", "Prefers concise answers" |
| **Recent topics** | What the user engaged with recently | "Asked about chess.com streak emails in Feb 2026", "Searched for early termination clauses" |

### Memory extraction (post-conversation)

After each conversation turn, a background job (`extract_memories`) runs:

```
Last 10 messages of the conversation
    │
    ▼
GPT-4o (extraction prompt, JSON mode)
    │  Extracts durable facts and recent topics.
    │  Returns { "memories": ["...", "..."] }
    │
    ▼
Embed each candidate (text-embedding-3-small)
    │
    ▼
Duplicate check (pgvector cosine similarity)
    │  Skip if any existing memory for this user
    │  has similarity > 0.92 with the candidate.
    │
    ▼
Store in `memories` table (user_id, org_id, content, embedding)
```

### Memory retrieval (per-turn, at prompt-build time)

Each time the user sends a message, two memory blocks are injected into the system prompt:

```
[What I remember about this user]        ← Part 1: most recent 20 stored memories
- Works in corporate law
- Clients are Spanish SMEs
- Asked about chess.com emails in Feb 2026

[Relevant past exchanges]                ← Part 2: semantically similar past Q&A pairs
- Q: What are the rules for early termination?
  A: The contract clause in section 4.2 states...
```

**Part 1** (always): The 20 most recent memories for the user, newest first.

**Part 2** (when a current query is available):

```
Embed current query
    │
    ▼
pgvector cosine similarity search over assistant messages
    │  Matches against Q&A pair embeddings (see below).
    │  Returns top 10 by similarity.
    │
    ▼
Deduplicate by answer prefix
    │  Skip answers that start identically (e.g. repeated
    │  "I don't have access" responses).
    │  Keep at most 3 unique exchanges.
    │
    ▼
Injected into system prompt as [Relevant past exchanges]
```

If pgvector is unavailable (e.g. SQLite in tests), Part 2 is skipped gracefully via a SAVEPOINT.

### Q&A pair embeddings

Assistant messages are embedded as **Q&A pairs** rather than standalone answers. This is because the user's question is semantically richer for retrieval than the assistant's answer alone.

```
User message:  "What are the notice periods in the contract?"
Assistant msg: "Section 4.1 requires 30 days notice..."

Embedded text: "Q: What are the notice periods in the contract?\nA: Section 4.1 requires 30 days notice..."
```

This embedding is computed asynchronously by a background worker (`embed_message` job) after each turn, using `text-embedding-3-small`.

---

## Architecture

```
┌─────────────┐     SSE / REST      ┌──────────────────────┐
│  React SPA  │◄───────────────────►│  FastAPI backend      │
│  (Vite)     │                     │  /api/v1/*            │
└─────────────┘                     └──────────┬───────────┘
                                               │
                          ┌────────────────────┼────────────────────┐
                          │                    │                    │
                    ┌─────▼──────┐    ┌────────▼───────┐   ┌──────▼──────┐
                    │ PostgreSQL │    │  LocalStack S3  │   │ LocalStack  │
                    │ + pgvector │    │  (documents)    │   │    SQS      │
                    └────────────┘    └────────────────┘   └──────┬──────┘
                                                                   │
                                                          ┌────────▼───────┐
                                                          │  Worker process │
                                                          │  (SQS poller)   │
                                                          │                 │
                                                          │ • ingest docs   │
                                                          │ • embed messages│
                                                          │ • extract memory│
                                                          └────────────────┘
```

### Key services

| Service | Role |
|---------|------|
| `backend` | FastAPI app — auth, chat, search, memory, document management |
| `worker` | SQS consumer — document ingestion, message embedding, memory extraction |
| `postgres` | PostgreSQL 16 + pgvector — chunks, messages, memories, conversations |
| `localstack` | Local AWS emulation — S3 (document storage) + SQS (job queue) |
| `frontend` | React 18 + Vite + TypeScript + Tailwind |

---

## Running locally

```bash
cp .env.example .env
# Fill in: GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, OPENAI_API_KEY,
#           SECRET_KEY, JWT_SECRET, COHERE_API_KEY

chmod +x infra/localstack-init.sh
docker-compose up --build

# Run migrations
docker-compose exec backend alembic upgrade head

# Run tests (from backend/ directory, outside Docker)
cd backend
env $(grep -v '^#' ../.env | xargs) uv run python -m pytest ../tests/ -v
```
