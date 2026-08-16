from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import OLLAMA_BASE_URL, OLLAMA_EMBED_MODEL, OLLAMA_LLM_MODEL
from rag.ingest import build_index, load_documents
from rag.memory import init_db


def ollama_models() -> list[str]:
    r = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
    r.raise_for_status()
    return sorted(m.get("name", "") for m in r.json().get("models", []))


def pull(model: str) -> None:
    print(f"\nDescargando/verificando {model} …")
    subprocess.run(["ollama", "pull", model], check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepara NutriMenú RAG con Ollama.")
    parser.add_argument("--pull", action="store_true", help="Descarga los modelos faltantes con ollama pull.")
    parser.add_argument("--skip-index", action="store_true", help="No crea el índice vectorial.")
    args = parser.parse_args()

    print("NutriMenú · Protein Food")
    print(f"LLM:        {OLLAMA_LLM_MODEL}")
    print(f"Embeddings: {OLLAMA_EMBED_MODEL}")
    print(f"Ollama:     {OLLAMA_BASE_URL}")

    try:
        models = ollama_models()
        print(f"\nOllama responde. Modelos locales: {len(models)}")
    except Exception as exc:
        print("\nERROR: Ollama no responde.")
        print("Abre Ollama o ejecuta `ollama serve` y vuelve a intentar.")
        print(f"Detalle: {type(exc).__name__}: {exc}")
        return 2

    for model in (OLLAMA_LLM_MODEL, OLLAMA_EMBED_MODEL):
        present = any(m == model or m.startswith(model + ":") for m in models)
        if not present:
            if args.pull:
                pull(model)
                models = ollama_models()
            else:
                print(f"FALTA: {model}. Ejecuta: ollama pull {model}")

    init_db()
    print("\nMemoria SQLite preparada.")

    if not args.skip_index:
        print(f"Construyendo índice con {len(load_documents())} chunks …")
        build_index(force=True)
        print("Índice RAG listo.")

    print("\nTodo listo. Inicia la web con: python app.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
