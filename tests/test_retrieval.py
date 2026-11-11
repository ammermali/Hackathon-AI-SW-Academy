"""Tests for hybrid retrieval, metadata filtering, and out-of-domain threshold filtering."""

from __future__ import annotations

from operator_copilot.retrieval.rag_engine import RAGEngine


def test_retrieves_relevant_procedure_with_metadata(indexed_engine: RAGEngine) -> None:
    chunks = indexed_engine.retriever.retrieve("Come rimuovere un verbale da un ruolo con F7?")
    assert len(chunks) >= 1
    top = chunks[0]
    assert "005 - Rimuovere verbale da ruolo.md" in top.document.metadata["source"]
    assert top.document.metadata["area_name"] == "Codice della Strada"
    assert top.relevance_score > 0


def test_metadata_filtering_restricts_results(indexed_engine: RAGEngine) -> None:
    chunks = indexed_engine.retriever.retrieve(
        "pratica di cancellazione irreperibilità",
        filters={"area_name": "SERVIZI DEMOGRAFICI"},
        top_k=3,
    )
    assert len(chunks) >= 1
    assert all(c.document.metadata.get("area_name") == "SERVIZI DEMOGRAFICI" for c in chunks)

    # Filtering on mismatched area should not return SERVIZI DEMOGRAFICI docs
    empty_or_different = indexed_engine.retriever.retrieve(
        "irreperibilità anagrafe",
        filters={"area_name": "Codice della Strada"},
        score_threshold=0.45,
    )
    assert all(c.document.metadata.get("area_name") == "Codice della Strada" for c in empty_or_different)


def test_out_of_domain_query_returns_no_results_above_threshold(indexed_engine: RAGEngine) -> None:
    chunks = indexed_engine.retriever.retrieve(
        "Ricetta della pasta alla carbonara con guanciale e pecorino",
        score_threshold=0.40,
    )
    assert chunks == []
