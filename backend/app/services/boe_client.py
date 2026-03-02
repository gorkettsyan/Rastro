"""BOE (Boletín Oficial del Estado) API client.

Fetches consolidated legislation from the BOE API and parses XML into articles.
"""
import asyncio
import logging
import re
from dataclasses import dataclass, field
from xml.etree import ElementTree as ET

import httpx

log = logging.getLogger(__name__)

BOE_API_BASE = "https://www.boe.es/datosabiertos/api/legislacion-consolidada/id"

# The 9 core Spanish laws to ingest
KNOWN_LAWS: list[dict] = [
    {"boe_id": "BOE-A-1889-4763", "title": "Código Civil", "short_name": "CC"},
    {"boe_id": "BOE-A-1885-6627", "title": "Código de Comercio", "short_name": "CCom"},
    {"boe_id": "BOE-A-2010-10544", "title": "Ley de Sociedades de Capital", "short_name": "LSC"},
    {"boe_id": "BOE-A-2017-12902", "title": "Ley de Contratos del Sector Público", "short_name": "LCSP"},
    {"boe_id": "BOE-A-1998-8789", "title": "Ley de Condiciones Generales de la Contratación", "short_name": "LCGC"},
    {"boe_id": "BOE-A-2007-20555", "title": "Ley General para la Defensa de los Consumidores y Usuarios", "short_name": "LGDCU"},
    {"boe_id": "BOE-A-2015-11430", "title": "Estatuto de los Trabajadores", "short_name": "ET"},
    {"boe_id": "BOE-A-2018-16673", "title": "Ley Orgánica de Protección de Datos Personales y Garantía de los Derechos Digitales", "short_name": "LOPDGDD"},
    {"boe_id": "BOE-A-2002-13758", "title": "Ley de Servicios de la Sociedad de la Información", "short_name": "LSSI"},
]

REQUEST_DELAY_MS = 100


@dataclass
class BoeArticle:
    block_id: str | None
    article_number: str | None
    section_title: str | None
    content: str
    boe_url: str


@dataclass
class BoeLawData:
    boe_id: str
    title: str
    short_name: str
    articles: list[BoeArticle] = field(default_factory=list)


def _parse_index(xml_text: str) -> list[str]:
    """Parse the index XML to extract block IDs.

    Real BOE format:
      <response><data>
        <bloque><id>a1</id><titulo>Artículo 1</titulo>...</bloque>
        ...
      </data></response>
    """
    block_ids = []
    try:
        root = ET.fromstring(xml_text)
        # Real BOE API: <response><data><bloque><id>
        for bloque in root.iter("bloque"):
            id_elem = bloque.find("id")
            if id_elem is not None and id_elem.text:
                block_ids.append(id_elem.text.strip())
    except ET.ParseError as e:
        log.warning("Failed to parse BOE index XML: %s", e)
    return block_ids


def _extract_text_from_element(elem) -> str:
    """Recursively extract text from an XML element and its children."""
    parts = []
    if elem.text:
        parts.append(elem.text.strip())
    for child in elem:
        child_text = _extract_text_from_element(child)
        if child_text:
            parts.append(child_text)
        if child.tail and child.tail.strip():
            parts.append(child.tail.strip())
    return " ".join(parts)


def _classify_title(titulo: str | None) -> tuple[str | None, str | None]:
    """Extract article_number and section_title from a block title."""
    if not titulo:
        return None, None
    art_match = re.match(r"(Art[íi]culo\s+\S+)", titulo, re.IGNORECASE)
    if art_match:
        return art_match.group(1), None
    return None, titulo


def _parse_block(xml_text: str, boe_id: str, block_id: str | None) -> BoeArticle | None:
    """Parse a single block XML into a BoeArticle.

    Real BOE block format:
      <response><data>
        <bloque id="a1" tipo="precepto" titulo="Artículo 1">
          <version ...>
            <p class="articulo">Artículo 1. Ámbito objetivo.</p>
            <p class="parrafo">...</p>
          </version>
        </bloque>
      </data></response>
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        log.warning("Failed to parse BOE block XML (block=%s): %s", block_id, e)
        return None

    # Find the <bloque> element — may be root itself or nested under <response><data>
    bloque = root.find(".//bloque")
    if bloque is None:
        bloque = root if root.tag == "bloque" else None
    if bloque is None:
        return None

    # Title from attribute or child element
    titulo = bloque.get("titulo")
    if not titulo:
        titulo_elem = bloque.find("titulo")
        titulo = titulo_elem.text.strip() if titulo_elem is not None and titulo_elem.text else None

    # Extract paragraphs from <version><p> or <texto><p>
    paragraphs = []
    # Try <version><p> first (real BOE API format)
    for version in bloque.iter("version"):
        for p in version.iter("p"):
            p_text = _extract_text_from_element(p)
            if p_text:
                paragraphs.append(p_text)
    # Fallback: <texto><p>
    if not paragraphs:
        texto_elem = bloque.find(".//texto")
        if texto_elem is not None:
            for p in texto_elem.iter("p"):
                p_text = _extract_text_from_element(p)
                if p_text:
                    paragraphs.append(p_text)

    if not paragraphs:
        return None

    content = "\n".join(paragraphs)
    article_number, section_title = _classify_title(titulo)

    if titulo:
        content = f"{titulo}\n\n{content}"

    boe_url = f"https://www.boe.es/buscar/act.php?id={boe_id}"

    return BoeArticle(
        block_id=block_id or bloque.get("id"),
        article_number=article_number,
        section_title=section_title,
        content=content,
        boe_url=boe_url,
    )


def _parse_full_text(xml_text: str, boe_id: str) -> list[BoeArticle]:
    """Parse the full consolidated text XML into articles.

    Real BOE full-text format:
      <response><data><texto>
        <bloque id="preambulo" ...><version>...</version></bloque>
        <bloque id="a1" ...><version>...</version></bloque>
        ...
      </texto></data></response>
    """
    articles = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        log.warning("Failed to parse BOE full text XML: %s", e)
        return articles

    for bloque in root.iter("bloque"):
        block_id = bloque.get("id")
        block_xml = ET.tostring(bloque, encoding="unicode")
        article = _parse_block(block_xml, boe_id, block_id)
        if article:
            articles.append(article)

    return articles


async def fetch_law(boe_id: str) -> BoeLawData | None:
    """Fetch a law from the BOE API and parse it into articles."""
    law_info = next((l for l in KNOWN_LAWS if l["boe_id"] == boe_id), None)
    if not law_info:
        log.error("Unknown BOE ID: %s", boe_id)
        return None

    law_data = BoeLawData(
        boe_id=boe_id,
        title=law_info["title"],
        short_name=law_info["short_name"],
    )

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Try fetching the index first
        index_url = f"{BOE_API_BASE}/{boe_id}/texto/indice"
        try:
            resp = await client.get(index_url, headers={"Accept": "application/xml"})
            resp.raise_for_status()
            block_ids = _parse_index(resp.text)
        except (httpx.HTTPError, Exception) as e:
            log.warning("Failed to fetch BOE index for %s: %s. Trying full text.", boe_id, e)
            block_ids = []

        if block_ids:
            # Fetch each block individually
            for block_id in block_ids:
                block_url = f"{BOE_API_BASE}/{boe_id}/texto/bloque/{block_id}"
                try:
                    await asyncio.sleep(REQUEST_DELAY_MS / 1000)
                    resp = await client.get(block_url, headers={"Accept": "application/xml"})
                    resp.raise_for_status()
                    article = _parse_block(resp.text, boe_id, block_id)
                    if article:
                        law_data.articles.append(article)
                except (httpx.HTTPError, Exception) as e:
                    log.warning("Failed to fetch block %s for %s: %s", block_id, boe_id, e)
        else:
            # Fallback: fetch full text at once
            full_url = f"{BOE_API_BASE}/{boe_id}/texto"
            try:
                resp = await client.get(full_url, headers={"Accept": "application/xml"})
                resp.raise_for_status()
                law_data.articles = _parse_full_text(resp.text, boe_id)
            except (httpx.HTTPError, Exception) as e:
                log.error("Failed to fetch BOE full text for %s: %s", boe_id, e)
                return None

    log.info("Fetched %d articles for %s (%s)", len(law_data.articles), boe_id, law_info["short_name"])
    return law_data
