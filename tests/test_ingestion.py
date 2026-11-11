"""Tests for document scanning, loading, metadata extraction, deduplication, and incremental indexing."""

from __future__ import annotations

from pathlib import Path

from operator_copilot.config.settings import Settings
from operator_copilot.db.database import DatabaseManager
from operator_copilot.db.models import DocumentMetadata
from operator_copilot.ingestion.indexer import DocumentIndexer


def test_ingestion_extracts_text_metadata_and_handles_unreadable(
    test_settings: Settings,
    test_db: DatabaseManager,
) -> None:
    indexer = DocumentIndexer(settings=test_settings, db_manager=test_db)
    res = indexer.run_ingestion(rebuild=True)

    # INDEX.md is skipped; 5 remaining files: 3 unique valid, 1 near-duplicate skipped, 1 unreadable
    assert res.files_scanned == 5
    assert res.files_indexed == 3
    assert res.files_skipped_duplicate == 1
    assert res.files_failed == 1
    assert res.chunks_created >= 3

    with test_db.session() as db:
        rows = db.query(DocumentMetadata).all()
        by_source = {r.source: r for r in rows}

        assert by_source["03 - SERVIZI DEMOGRAFICI/067 - Cancellazione, la pratica resta in corso.md"].status == "indexed"
        assert by_source["03 - SERVIZI DEMOGRAFICI/067 - Cancellazione, la pratica resta in corso.md"].area_name == "SERVIZI DEMOGRAFICI"
        assert by_source["03 - SERVIZI DEMOGRAFICI/068 - Cancellazione, la pratica resta in corso.md"].status == "skipped_duplicate"
        assert by_source["03 - SERVIZI DEMOGRAFICI/corrupted_notes.txt"].status == "unreadable"

        comm = by_source["27 - Comunicazioni/08 - Comunicazioni 2025/2025_c10_siope_pagopa.md"]
        assert comm.document_type == "communication"
        assert comm.doc_year == 2025


def test_incremental_ingestion_skips_unchanged_and_updates_modified(
    test_settings: Settings,
    test_db: DatabaseManager,
    sample_data_dir: Path,
) -> None:
    indexer = DocumentIndexer(settings=test_settings, db_manager=test_db)
    first = indexer.run_ingestion(rebuild=True)
    v1 = first.corpus_version

    # Second run without changes should skip unchanged files and keep corpus_version
    second = indexer.run_ingestion(rebuild=False)
    assert second.files_indexed == 0
    assert second.files_skipped_unchanged == 3
    assert second.corpus_version == v1

    # Modify one indexed file -> must re-index only that file and bump corpus_version
    target = sample_data_dir / "15 - Codice della Strada" / "005 - Rimuovere verbale da ruolo.md"
    target.write_text(
        target.read_text(encoding="utf-8") + "\n\n## Nota aggiunta\nControllare stato ruolo.",
        encoding="utf-8",
    )

    third = indexer.run_ingestion(rebuild=False)
    assert third.files_indexed == 1
    assert third.files_skipped_unchanged == 2
    assert third.corpus_version != v1
