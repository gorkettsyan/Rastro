"""Tests for the BOE Knowledge Plugin."""
import json
import pytest
import uuid
from unittest.mock import AsyncMock, patch, MagicMock

from app.services.boe_client import (
    _parse_index,
    _parse_block,
    _parse_full_text,
    BoeArticle,
    BoeLawData,
)
from app.services.boe_ingestion import _split_long_article
from app.services.knowledge_registry import _plugins, register_plugin, get_plugins
from app.services.knowledge_base import BaseKnowledgePlugin
from app.services.rag import _make_system_prompt, RAGService


# ── 1. XML parsing tests ──


SAMPLE_INDEX_XML = """<?xml version="1.0"?>
<response>
  <status><code>200</code><text>ok</text></status>
  <data>
    <bloque><id>a1</id><titulo>Artículo 1</titulo></bloque>
    <bloque><id>a2</id><titulo>Artículo 2</titulo></bloque>
    <bloque><id>ci</id><titulo>CAPÍTULO I</titulo></bloque>
  </data>
</response>
"""

SAMPLE_BLOCK_XML = """<?xml version="1.0"?>
<response>
  <status><code>200</code><text>ok</text></status>
  <data>
    <bloque id="a1" tipo="precepto" titulo="Artículo 1. De las obligaciones">
      <version id_norma="BOE-A-1889-4763" fecha_publicacion="18890725">
        <p class="articulo">Artículo 1. De las obligaciones.</p>
        <p class="parrafo">Toda obligación consiste en dar, hacer o no hacer alguna cosa.</p>
        <p class="parrafo">El obligado a dar alguna cosa lo está también a conservarla con la diligencia propia de un buen padre de familia.</p>
      </version>
    </bloque>
  </data>
</response>
"""

SAMPLE_BLOCK_SECTION_XML = """<?xml version="1.0"?>
<response>
  <status><code>200</code><text>ok</text></status>
  <data>
    <bloque id="ci" tipo="estructura" titulo="Capítulo I. Disposiciones generales">
      <version id_norma="BOE-A-1889-4763" fecha_publicacion="18890725">
        <p class="parrafo">Este capítulo contiene las disposiciones generales aplicables.</p>
      </version>
    </bloque>
  </data>
</response>
"""

SAMPLE_EMPTY_BLOCK_XML = """<?xml version="1.0"?>
<response>
  <status><code>200</code><text>ok</text></status>
  <data>
    <bloque id="derogado" tipo="precepto" titulo="Artículo derogado">
    </bloque>
  </data>
</response>
"""


def test_parse_index_extracts_block_ids():
    ids = _parse_index(SAMPLE_INDEX_XML)
    assert ids == ["a1", "a2", "ci"]


def test_parse_index_empty_xml():
    ids = _parse_index("<response><data></data></response>")
    assert ids == []


def test_parse_index_malformed_xml():
    ids = _parse_index("not xml at all")
    assert ids == []


def test_parse_block_extracts_article():
    article = _parse_block(SAMPLE_BLOCK_XML, "BOE-A-1889-4763", "a1")
    assert article is not None
    assert article.article_number == "Artículo 1."
    assert article.block_id == "a1"
    assert "obligación" in article.content.lower()
    assert "boe.es" in article.boe_url


def test_parse_block_section_title():
    article = _parse_block(SAMPLE_BLOCK_SECTION_XML, "BOE-A-1889-4763", "ci")
    assert article is not None
    assert article.article_number is None
    assert article.section_title == "Capítulo I. Disposiciones generales"


def test_parse_block_empty_returns_none():
    article = _parse_block(SAMPLE_EMPTY_BLOCK_XML, "BOE-A-1889-4763", "derogado")
    assert article is None


def test_parse_block_malformed_xml():
    article = _parse_block("not xml", "BOE-A-1889-4763", "BLK-BAD")
    assert article is None


# ── 2. Article chunking tests ──


def test_short_article_single_chunk():
    article = BoeArticle(
        block_id="BLK-1",
        article_number="Artículo 1",
        section_title=None,
        content="Toda obligación consiste en dar, hacer o no hacer alguna cosa.",
        boe_url="https://www.boe.es/buscar/act.php?id=BOE-A-1889-4763",
    )
    chunks = _split_long_article(article, "CC")
    assert len(chunks) == 1
    assert chunks[0]["content"] == article.content


def test_long_article_splits_with_header():
    # Create an article with >512 tokens of content
    long_text = "Artículo 500\n\n" + ("Esta es una cláusula larga con muchas palabras. " * 200)
    article = BoeArticle(
        block_id="BLK-500",
        article_number="Artículo 500",
        section_title="Título Preliminar",
        content=long_text,
        boe_url="https://www.boe.es/buscar/act.php?id=BOE-A-1889-4763",
    )
    chunks = _split_long_article(article, "CC")
    assert len(chunks) > 1
    # Second chunk should have the header prepended
    assert "CC" in chunks[1]["content"]


# ── 3. Plugin format tests ──


def test_boe_plugin_chunk_id_prefix():
    from app.services.boe_plugin import BoeKnowledgePlugin

    plugin = BoeKnowledgePlugin()
    source = plugin.format_source({
        "chunk_id": "boe:some-uuid",
        "document_id": "boe:BOE-A-1889-4763",
        "title": "CC — Artículo 1",
        "content": "Toda obligación consiste en dar, hacer o no hacer alguna cosa.",
        "source_url": "https://www.boe.es/buscar/act.php?id=BOE-A-1889-4763",
        "law_name": "CC",
        "article_number": "Artículo 1",
        "boe_id": "BOE-A-1889-4763",
        "rrf_score": 0.05,
    })
    assert source["source_type"] == "boe"
    assert source["law_name"] == "CC"
    assert source["article_number"] == "Artículo 1"
    assert source["boe_id"] == "BOE-A-1889-4763"
    assert source["source"] == "boe"


# ── 4. RRF fusion with BOE results ──


def test_rrf_fusion_boe_and_private():
    private_vector = [
        {"chunk_id": "private-1", "content": "contract clause", "document_id": "doc1",
         "score": 0.9, "title": "Contract", "source": "upload", "source_url": None, "retrieval": "vector"},
    ]
    boe_vector = [
        {"chunk_id": "boe:boe-1", "content": "artículo 1", "document_id": "boe:BOE-A-1889-4763",
         "score": 0.85, "title": "CC — Artículo 1", "source": "boe", "source_url": "https://boe.es",
         "source_type": "boe", "law_name": "CC", "article_number": "Artículo 1", "retrieval": "vector"},
    ]
    private_bm25 = [
        {"chunk_id": "private-1", "content": "contract clause", "document_id": "doc1",
         "score": 2.5, "title": "Contract", "source": "upload", "source_url": None, "retrieval": "bm25"},
    ]
    boe_bm25 = [
        {"chunk_id": "boe:boe-1", "content": "artículo 1", "document_id": "boe:BOE-A-1889-4763",
         "score": 1.8, "title": "CC — Artículo 1", "source": "boe", "source_url": "https://boe.es",
         "source_type": "boe", "retrieval": "bm25"},
    ]

    all_vector = private_vector + boe_vector
    all_bm25 = private_bm25 + boe_bm25
    fused = RAGService._reciprocal_rank_fusion(all_vector, all_bm25)

    assert len(fused) == 2
    ids = [c["chunk_id"] for c in fused]
    assert "private-1" in ids
    assert "boe:boe-1" in ids

    for chunk in fused:
        assert chunk["rrf_score"] > 0


def test_diversify_sources_interleaves():
    """_diversify_sources ensures private chunks aren't buried by BOE."""
    chunks = [
        {"chunk_id": "boe:1", "source": "boe", "source_type": "boe"},
        {"chunk_id": "boe:2", "source": "boe", "source_type": "boe"},
        {"chunk_id": "boe:3", "source": "boe", "source_type": "boe"},
        {"chunk_id": "priv-1", "source": "upload"},
        {"chunk_id": "priv-2", "source": "upload"},
    ]
    result = RAGService._diversify_sources(chunks, 4)
    # Private chunks pulled up to alternate with BOE
    assert result[0]["chunk_id"] == "priv-1"
    assert result[1]["chunk_id"] == "boe:1"
    assert result[2]["chunk_id"] == "priv-2"
    assert result[3]["chunk_id"] == "boe:2"


def test_diversify_sources_single_type_passthrough():
    """When only one source type exists, top_n are returned in order."""
    chunks = [
        {"chunk_id": "boe:1", "source": "boe", "source_type": "boe"},
        {"chunk_id": "boe:2", "source": "boe", "source_type": "boe"},
    ]
    result = RAGService._diversify_sources(chunks, 5)
    assert len(result) == 2
    assert result[0]["chunk_id"] == "boe:1"


# ── 5. Knowledge registry tests ──


def test_plugin_auto_registration():
    """Importing boe_plugin should auto-register the BOE plugin."""
    import app.services.boe_plugin  # noqa: F401
    plugins = get_plugins()
    names = [p.name for p in plugins]
    assert "boe" in names


def test_register_plugin_idempotent():
    """Registering the same plugin twice should not duplicate it."""
    initial_count = len(get_plugins())
    import app.services.boe_plugin  # noqa: F401
    # Try registering again
    from app.services.boe_plugin import _boe_plugin
    register_plugin(_boe_plugin)
    assert len(get_plugins()) == initial_count


# ── 6. System prompt tests ──


def test_system_prompt_without_boe():
    prompt = _make_system_prompt("es", has_boe_results=False)
    assert "BOE" not in prompt
    assert "español" in prompt.lower()


def test_system_prompt_with_boe():
    prompt = _make_system_prompt("es", has_boe_results=True)
    assert "BOE" in prompt
    assert "Boletín Oficial del Estado" in prompt
    assert "español" in prompt.lower()


def test_system_prompt_english_with_boe():
    prompt = _make_system_prompt("en", has_boe_results=True)
    assert "BOE" in prompt
    assert "English" in prompt


# ── 7. Build context tests ──


def test_build_context_private_chunks():
    chunks = [
        {"content": "clause 1", "source": "upload"},
        {"content": "clause 2", "source": "drive"},
    ]
    ctx = RAGService._build_context(chunks)
    assert "[Source 1]" in ctx
    assert "[Source 2]" in ctx
    assert "clause 1" in ctx


def test_build_context_boe_chunks_include_law_info():
    chunks = [
        {"content": "private content", "source": "upload"},
        {
            "content": "art 1544 content",
            "source": "boe",
            "source_type": "boe",
            "law_name": "CC",
            "article_number": "Artículo 1544",
        },
    ]
    ctx = RAGService._build_context(chunks)
    assert "[Source 1]" in ctx
    assert "[Source 2] (CC, Artículo 1544)" in ctx
    assert "art 1544 content" in ctx


def test_build_context_boe_chunk_without_article():
    chunks = [
        {
            "content": "general provision",
            "source": "boe",
            "source_type": "boe",
            "law_name": "ET",
            "article_number": None,
        },
    ]
    ctx = RAGService._build_context(chunks)
    assert "[Source 1] (ET)" in ctx


# ── 8. Vague query gate tests ──


@pytest.mark.asyncio
async def test_vague_query_returns_helpful_message():
    """A vague query like 'contrato' should get a 'be more specific' message instead of RAG."""
    mock_embedding = AsyncMock()
    mock_reranker = AsyncMock()
    svc = RAGService(mock_embedding, mock_reranker)

    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()
    mock_db.commit = AsyncMock()

    # Mock the intent classifier to return "vague"
    mock_completion = MagicMock()
    mock_completion.choices = [MagicMock()]
    mock_completion.choices[0].message.content = "vague"

    with patch.object(svc, "_openai") as mock_openai:
        mock_openai.chat.completions.create = AsyncMock(return_value=mock_completion)

        events = []
        async for event in svc.stream_rag_response(
            db=mock_db,
            org_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            query="contrato",
            language="es",
        ):
            events.append(event)

    # Should emit a token with the vague message, sources=[], and done
    assert len(events) == 3
    token_event = json.loads(events[0].removeprefix("data: ").strip())
    assert token_event["type"] == "token"
    assert "demasiado general" in token_event["content"]

    sources_event = json.loads(events[1].removeprefix("data: ").strip())
    assert sources_event["type"] == "sources"
    assert sources_event["sources"] == []

    done_event = json.loads(events[2].removeprefix("data: ").strip())
    assert done_event["type"] == "done"


@pytest.mark.asyncio
async def test_vague_query_english_message():
    """Vague query with language='en' returns English message."""
    mock_embedding = AsyncMock()
    mock_reranker = AsyncMock()
    svc = RAGService(mock_embedding, mock_reranker)

    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()
    mock_db.commit = AsyncMock()

    mock_completion = MagicMock()
    mock_completion.choices = [MagicMock()]
    mock_completion.choices[0].message.content = "vague"

    with patch.object(svc, "_openai") as mock_openai:
        mock_openai.chat.completions.create = AsyncMock(return_value=mock_completion)

        events = []
        async for event in svc.stream_rag_response(
            db=mock_db,
            org_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            query="contract",
            language="en",
        ):
            events.append(event)

    token_event = json.loads(events[0].removeprefix("data: ").strip())
    assert "too broad" in token_event["content"]


@pytest.mark.asyncio
async def test_chat_intent_returns_empty():
    """A chat/greeting query should return empty sources and no answer."""
    mock_embedding = AsyncMock()
    mock_reranker = AsyncMock()
    svc = RAGService(mock_embedding, mock_reranker)

    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()
    mock_db.commit = AsyncMock()

    mock_completion = MagicMock()
    mock_completion.choices = [MagicMock()]
    mock_completion.choices[0].message.content = "chat"

    with patch.object(svc, "_openai") as mock_openai:
        mock_openai.chat.completions.create = AsyncMock(return_value=mock_completion)

        events = []
        async for event in svc.stream_rag_response(
            db=mock_db,
            org_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            query="hola",
            language="es",
        ):
            events.append(event)

    # Only sources + done, no token
    assert len(events) == 2
    sources_event = json.loads(events[0].removeprefix("data: ").strip())
    assert sources_event["type"] == "sources"
    assert sources_event["sources"] == []
