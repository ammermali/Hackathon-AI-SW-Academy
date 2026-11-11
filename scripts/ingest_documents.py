"""CLI script to ingest or rebuild documents from DATA_DIR into ChromaDB."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    import operator_copilot  # noqa: F401
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from operator_copilot.config.settings import get_settings
from operator_copilot.ingestion.indexer import DocumentIndexer


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest documents into Operator Copilot vector store.")
    parser.add_argument("--rebuild", action="store_true", help="Clear existing index and rebuild from scratch.")
    parser.add_argument("--max-files", type=int, default=None, help="Optional limit on scanned files.")
    args = parser.parse_args()

    settings = get_settings()
    indexer = DocumentIndexer(settings=settings)
    result = indexer.run_ingestion(rebuild=args.rebuild, max_files=args.max_files)
    print(json.dumps(result.model_dump(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
