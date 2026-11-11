"""Automated RAG evaluation script against the real `data/` corpus."""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path

try:
    import operator_copilot  # noqa: F401
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from operator_copilot.config.settings import get_settings
from operator_copilot.retrieval.rag_engine import RAGEngine
from operator_copilot.schemas.query import RAGQueryRequest


@dataclass
class EvalCase:
    query: str
    expected_source_substrings: list[str]
    expected_terms: list[str]
    should_abstain: bool = False


EVAL_DATASET: list[EvalCase] = [
    EvalCase(
        query="Come si apre correttamente una richiesta di assistenza clienti per Cityware Online?",
        expected_source_substrings=["2024_c07_modalita_corretta_richiesta_assistenza_clienti.md"],
        expected_terms=["assistenza", "ticket"],
    ),
    EvalCase(
        query="Qual è il percorso per versare il registro giornaliero e i protocolli in Conservazione?",
        expected_source_substrings=["014 - conservazione.md"],
        expected_terms=["Protocollo", "Conservazione", "Stampa Registro Giornaliero"],
    ),
    EvalCase(
        query="Quale percorso di menu bisogna seguire per creare una Proposta di Determina?",
        expected_source_substrings=["043 - CREARE UNA PROPOSTA DI DETERMINA.md"],
        expected_terms=["Gestione Documentale", "Proposte"],
    ),
    EvalCase(
        query="Come si rimuove un verbale da un ruolo in Gestione Ruoli?",
        expected_source_substrings=["15 - Codice della Strada/video/3.md"],
        expected_terms=["Gestione Ruoli", "F7"],
    ),
    EvalCase(
        query="Come si gestisce la modalità Avviso PAGOPA e il codice IUV nella liquidazione?",
        expected_source_substrings=["001 - INDICE - Frequently Asked Questions.md", "pagopa"],
        expected_terms=["PAGOPA", "IUV"],
    ),
    EvalCase(
        query="Cosa succede dopo tentativi falliti di accesso e come si verifica il blocco dell'account?",
        expected_source_substrings=["007 - Blocco dell'account dopo tentativi falliti.md"],
        expected_terms=["bloccato", "amministratore"],
    ),
    EvalCase(
        query="Cos'è e qual è il percorso del modello ISTAT AP10 per il movimento popolazione residente?",
        expected_source_substrings=["242 - Movimento della popolazione residente ISTAT (Mensile AP10).md"],
        expected_terms=["AP10", "popolazione"],
    ),
    EvalCase(
        query="Come si effettua la duplicazione AIRE tra due elezioni aperte?",
        expected_source_substrings=["123 - duplicazione aire tra elezioni.md"],
        expected_terms=["Elettorale", "Duplicazione Aire"],
    ),
    EvalCase(
        query="Qual è la ricetta tradizionale per preparare gli spaghetti alla carbonara?",
        expected_source_substrings=[],
        expected_terms=[],
        should_abstain=True,
    ),
    EvalCase(
        query="Quali sono le previsioni meteorologiche per domani a Milano?",
        expected_source_substrings=[],
        expected_terms=[],
        should_abstain=True,
    ),
]


def evaluate() -> dict:
    settings = get_settings()
    engine = RAGEngine(settings=settings)

    # Clear cache first to measure fresh retrieval + cold latency fairly
    engine.cache.invalidate_all()

    in_domain_cases = [c for c in EVAL_DATASET if not c.should_abstain]
    abstention_cases = [c for c in EVAL_DATASET if c.should_abstain]

    recall_hits = 0
    citation_real_hits = 0
    total_citations = 0
    term_coverage_scores: list[float] = []
    cold_latencies: list[int] = []
    relevance_scores: list[float] = []
    case_details = []

    for idx, case in enumerate(in_domain_cases):
        resp = engine.answer_query(
            RAGQueryRequest(query=case.query, user_id="eval_user", session_id="eval_sess")
        )
        cold_latencies.append(resp.processing_time_ms)
        if resp.retrieval.relevance_score is not None:
            relevance_scores.append(resp.retrieval.relevance_score)

        cited_docs = [s.document for s in resp.sources]
        matched_expected = any(
            any(exp.lower() in doc.lower() for exp in case.expected_source_substrings)
            for doc in cited_docs
        )
        if matched_expected:
            recall_hits += 1

        # Verify every cited source actually exists under DATA_DIR
        for doc_rel in cited_docs:
            total_citations += 1
            if (settings.data_dir / doc_rel).exists():
                citation_real_hits += 1

        ans_lower = resp.answer.lower()
        found_terms = sum(1 for t in case.expected_terms if t.lower() in ans_lower)
        term_cov = found_terms / len(case.expected_terms) if case.expected_terms else 1.0
        term_coverage_scores.append(term_cov)

        case_details.append(
            {
                "query": case.query,
                "recall_hit": matched_expected,
                "top_relevance": resp.retrieval.relevance_score,
                "term_coverage": round(term_cov, 2),
                "needs_escalation": resp.needs_escalation,
                "latency_ms": resp.processing_time_ms,
                "top_sources": cited_docs[:3],
                "answer_preview": resp.answer[:240].replace("\n", " "),
            }
        )

    # Abstention evaluation
    abstention_correct = 0
    abstention_details = []
    for case in abstention_cases:
        resp = engine.answer_query(
            RAGQueryRequest(query=case.query, user_id="eval_user", session_id="eval_sess")
        )
        ok = resp.needs_escalation and len(resp.sources) == 0
        if ok:
            abstention_correct += 1
        abstention_details.append(
            {
                "query": case.query,
                "abstained_correctly": ok,
                "needs_escalation": resp.needs_escalation,
                "top_relevance": resp.retrieval.relevance_score,
                "sources_count": len(resp.sources),
            }
        )

    # Cache hit test: repeat first 4 in-domain queries
    warm_latencies: list[int] = []
    cache_hits = 0
    for case in in_domain_cases[:4]:
        resp = engine.answer_query(
            RAGQueryRequest(query=case.query, user_id="eval_user", session_id="eval_sess")
        )
        warm_latencies.append(resp.processing_time_ms)
        if resp.cached:
            cache_hits += 1

    summary = {
        "dataset_size": len(EVAL_DATASET),
        "in_domain_queries": len(in_domain_cases),
        "abstention_queries": len(abstention_cases),
        "recall_at_k": round(recall_hits / len(in_domain_cases), 4),
        "citation_existence_rate": round(citation_real_hits / total_citations, 4) if total_citations else 0.0,
        "avg_term_grounding": round(sum(term_coverage_scores) / len(term_coverage_scores), 4),
        "avg_top_relevance_score": round(sum(relevance_scores) / len(relevance_scores), 4) if relevance_scores else 0.0,
        "abstention_accuracy": round(abstention_correct / len(abstention_cases), 4),
        "avg_cold_latency_ms": round(sum(cold_latencies) / len(cold_latencies), 1),
        "avg_warm_cache_latency_ms": round(sum(warm_latencies) / len(warm_latencies), 1),
        "repeat_cache_hit_rate": round(cache_hits / 4, 4),
        "in_domain_results": case_details,
        "abstention_results": abstention_details,
    }
    return summary


if __name__ == "__main__":
    result = evaluate()
    print(json.dumps(result, indent=2, ensure_ascii=False))
