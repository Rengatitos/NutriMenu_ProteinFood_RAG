from __future__ import annotations

import json
import re
from pathlib import Path

from langchain_community.vectorstores import LanceDB
from langchain_core.documents import Document
from langchain_ollama import OllamaEmbeddings

from config import CATALOG_PATH, CHUNKS_PATH, LANCEDB_DIR, OLLAMA_BASE_URL, OLLAMA_EMBED_MODEL


def looks_like_prompt_injection(text: str) -> bool:
    patterns = [
        r"ignora\w*\s+(todas\s+)?(las\s+)?instrucciones",
        r"olvida\w*\s+(todo\s+)?lo\s+anterior",
        r"nueva\s+directiva",
        r"ignore\s+(all\s+)?previous\s+instructions",
    ]
    return any(re.search(p, text or "", re.I) for p in patterns)


def load_catalog() -> list[dict]:
    return json.loads(Path(CATALOG_PATH).read_text(encoding="utf-8"))


def load_documents() -> list[Document]:
    chunks = json.loads(Path(CHUNKS_PATH).read_text(encoding="utf-8"))
    catalog = load_catalog()
    by_product = {str(p["producto"]).strip().lower(): p for p in catalog}
    docs: list[Document] = []
    for ch in chunks:
        content = str(ch.get("contenido") or "").strip()
        if not content or looks_like_prompt_injection(content):
            continue
        metadata = {
            "chunk_id": ch.get("chunk_id"),
            "tipo": ch.get("tipo"),
            "seccion": ch.get("seccion"),
            "titulo": ch.get("titulo"),
            "categoria": ch.get("categoria"),
            "producto": ch.get("producto"),
            "imagen_png": ch.get("imagen_png") or "",
            "fuente": ch.get("fuente") or "base_conocimiento",
        }
        product_name = str(ch.get("producto") or "").strip().lower()
        if product_name and product_name in by_product:
            p = by_product[product_name]
            metadata.update({
                "product_id": p.get("id"),
                "precio_pen": p.get("precio_pen"),
                "kcal_min_est": p.get("kcal_min_est"),
                "kcal_max_est": p.get("kcal_max_est"),
                "kcal_ref_est": p.get("kcal_ref_est"),
                "nivel_proteico": p.get("nivel_proteico"),
                "imagen_png": p.get("imagen_png") or metadata["imagen_png"],
            })
        docs.append(Document(page_content=content, metadata=metadata))
    return docs


def build_index(force: bool = True) -> LanceDB:
    LANCEDB_DIR.mkdir(parents=True, exist_ok=True)
    embeddings = OllamaEmbeddings(model=OLLAMA_EMBED_MODEL, base_url=OLLAMA_BASE_URL)
    docs = load_documents()
    mode = "overwrite" if force else "create"
    return LanceDB.from_documents(
        docs,
        embeddings,
        uri=str(LANCEDB_DIR),
        table_name="nutrimenu",
        mode=mode,
    )


if __name__ == "__main__":
    db = build_index(force=True)
    print(f"Índice creado en {LANCEDB_DIR} con {len(load_documents())} fragmentos.")
