# Operator Copilot — Valutazione Sperimentale del Motore RAG

**Progetto:** Operator Copilot — Milestone 1 (RAG Engine)  
**Corpus reale valutato:** `data/` (`corpus_version = v_1794416931_4e8266`)  
**Configurazione misurata:** `EMBEDDING_PROVIDER=huggingface` (`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`), retrieval ibrido Chroma + `BM25Okapi` (`top_k=5`, `RETRIEVAL_SCORE_THRESHOLD=0.50`), generazione `LLM_PROVIDER=extractive`.

---

## 1. Riepilogo dell'Ingestion sul Corpus Reale (`data/`)

Comando eseguito:
```powershell
python scripts/ingest_documents.py --rebuild
```

| Metrica Ingestion | Valore Misurato |
| :--- | ---: |
| **File scansionati (escluso `INDEX.md`)** | **1.531** |
| **Documenti indicizzati in Chroma + SQLite** | **1.523** |
| **Duplicati / quasi-duplicati scartati** | **8** |
| **File falliti / illeggibili** | **0** |
| **Chunk creati e indicizzati** | **15.662** |
| **Tempo complessivo di rebuild** | **504.882 ms (~8,4 min)** |
| **Versione corpus attiva** | `v_1794416931_4e8266` |

---

## 2. Suite di Test Automatici (`pytest`)

Esecuzione completa della suite di test dopo l'ultima calibrazione della soglia (`RETRIEVAL_SCORE_THRESHOLD=0.50`):

- **Risultato:** **`18 passed in 5.54s`** (`0` failed, `0` skipped)
- **Moduli verificati:**
  - `tests/test_ingestion.py` (2 test): estrazione metadati, gestione file non leggibili, ingestion incrementale e aggiornamento file modificati.
  - `tests/test_retrieval.py` (3 test): recupero procedure con metadati reali, filtering per area/anno, astensione su query fuori dominio sotto soglia.
  - `tests/test_rag.py` (4 test): citazioni reali non inventate e output Pydantic valido, astensione su evidenze insufficienti, catena LangChain con `FakeListChatModel` + fallback controllato su errore, sanitizzazione anti-prompt-injection (`</retrieved_context>`).
  - `tests/test_cache.py` (5 test): miss -> hit con normalizzazione stringa, scadenza TTL, invalidazione su cambio `corpus_version` / `prompt_version`, isolamento utente `private` vs `public`, mancata memorizzazione di risposte con `needs_escalation=True`.
  - `tests/test_history.py` (3 test): guardia su `total_queries == 0`, registrazione query/topic/intent/feedback e KPI, retention policy e cancellazione storico per `user_id`.
  - `tests/test_api.py` (1 test): ciclo end-to-end sugli endpoint FastAPI (`/health`, `/api/v1/rag/ingest` con `X-Admin-Key`, `/api/v1/rag/query`, `/api/v1/rag/history/{user_id}`, `/api/v1/rag/feedback`, `/api/v1/rag/metrics`, `/api/v1/rag/documents`).

---

## 3. Valutazione Quantitativa sul Corpus Reale (`scripts/evaluate_rag.py`)

La valutazione end-to-end è stata eseguita su un benchmark manuale di **10 query realistiche** derivate direttamente dal dominio Cityware/CWOL (`8` in-domain su aree diverse + `2` out-of-domain per verificare l'astensione).

### Metriche Aggregate Misurate

| Metrica | Valore Misurato | Note |
| :--- | ---: | :--- |
| **Dataset complessivo** | **10 query** | 8 in-domain + 2 out-of-domain |
| **Recall@5** (`expected_source_substrings`) | **1.0000 (8/8)** | Documento atteso presente nelle top-5 fonti citate |
| **Citation Existence Rate** | **1.0000 (100%)** | Tutte le fonti citate esistono realmente su disco in `data/` |
| **Average Term Grounding** | **0.8750 (87,5%)** | Copertura dei termini chiave attesi nel testo della risposta |
| **Average Top Relevance Score** | **0.9133** | Score composito post-reranking sulle 8 query in-domain |
| **Abstention Accuracy (OOD)** | **1.0000 (2/2)** | Entrambe le query fuori dominio bloccate con `needs_escalation=True` e `sources=[]` |
| **Latenza media cold (cache miss)** | **2.389,8 ms** | Include il primo avvio del modello HF + sync BM25 sulla prima query (`18.608 ms`); le 7 query successive hanno latenza **`64–83 ms`** |
| **Latenza media warm (cache hit)** | **2,2 ms** | Risposta servita direttamente da SQLite su query ripetute/normalizzate |
| **Repeat Cache Hit Rate** | **1.0000 (4/4)** | 100% di hit sulla ripetizione delle prime 4 query |

### Dettaglio per Singola Query In-Domain

| # | Area / Query | Recall@5 | Top Score | Term Cov. | Latenza (ms) | Prima Fonte Citata |
| :---: | :--- | :---: | :---: | :---: | ---: | :--- |
| 1 | Apertura richiesta assistenza clienti Cityware Online | SI | 0.8868 | 1.0 | 18.608 *(cold init)* | `01 - Informazioni Generali/2024_c07_modalita_corretta_richiesta_assistenza_clienti.md` |
| 2 | Percorso versamento registro giornaliero in Conservazione | SI | 0.9445 | 1.0 | 67 | `04 - Protocollo/video/7_conservazione.md` |
| 3 | Percorso di menu per creare una Proposta di Determina | SI | 0.8228 | **0.0** | 80 | `05 - Segreteria degli Atti/043 - CREARE UNA PROPOSTA DI DETERMINA.md` |
| 4 | Rimozione verbale da un ruolo in Gestione Ruoli | SI | 0.9215 | 1.0 | 64 | `15 - Codice della Strada/video/3.md` |
| 5 | Gestione modalità Avviso PAGOPA e codice IUV nella liquidazione | SI | 0.8304 | 1.0 | 68 | `27 - Comunicazioni/06 - Comunicazioni 2023/allegati/2020_c10_liquidazione_pagamenti_pagopa.md` |
| 6 | Tentativi falliti di accesso e blocco dell'account | SI | 0.9502 | 1.0 | 83 | `02 - Modulo Base/007 - Blocco dell'account dopo tentativi falliti.md` |
| 7 | Percorso modello ISTAT AP10 movimento popolazione residente | SI | 1.0000 | 1.0 | 79 | `03 - SERVIZI DEMOGRAFICI/242 - Movimento della popolazione residente ISTAT (Mensile AP10).md` |
| 8 | Duplicazione AIRE tra due elezioni aperte | SI | 0.9503 | 1.0 | 69 | `03 - SERVIZI DEMOGRAFICI/123 - duplicazione aire tra elezioni.md` |

### Dettaglio Query Out-of-Domain (Astensione)

| Query | Risultato | `needs_escalation` | `top_relevance` | `sources_count` |
| :--- | :---: | :---: | :---: | ---: |
| `"Qual è la ricetta tradizionale per preparare gli spaghetti alla carbonara?"` | Astensione corretta | `true` | `null` | 0 |
| `"Quali sono le previsioni meteorologiche per domani a Milano?"` | Astensione corretta | `true` | `null` | 0 |

---

## 4. Osservazioni Critiche e Limiti Riscontrati

Un'analisi trasparente dei risultati evidenzia **4 limiti concreti** da tenere presenti prima del passaggio in produzione e nelle milestone successive:

1. **Modalità di Generazione Misurata (`extractive` vs LLM generativo esterno):**
   - Nell'ambiente di valutazione non era configurata una chiave API OpenAI/LLM live; la valutazione quantitativa sul corpus reale è stata quindi eseguita con `LLM_PROVIDER=extractive`, mentre l'integrazione LangChain LCEL con chat model (e relativo fallback) è stata verificata nei test automatici tramite `FakeListChatModel`.
   - Con un LLM generativo collegato in produzione cambieranno sia la fluidità delle risposte sia la latenza di generazione (`avg_generation_time_ms`).

2. **Ranking intra-documento su Query 3 (`Proposta di Determina`, `term_coverage = 0.0`):**
   - Pur avendo posizionato correttamente `05 - Segreteria degli Atti/043 - CREARE UNA PROPOSTA DI DETERMINA.md` al 1° e 2° posto del ranking, il retriever ha selezionato due chunk della sottosezione *Inserimento del Testo di Proposta* (`c0005` e `c0004`) invece del chunk introduttivo `c0000` che contiene il percorso di menu esplicito (`Gestione Documentale → Gestioni → Gestione Testi → Proposte`).
   - Un miglioramento futuro mirato consiste nel privilegiare i chunk introduttivi (`chunk_index == 0`) quando la query chiede esplicitamente *"percorso di menu"*.

3. **Soglia Near-Duplicate (`0.90`) sulle Comunicazioni Multi-Anno:**
   - L'indice attuale ha scartato **8** duplicati esatti/quasi-identici, ma copie dello stesso allegato salvate in cartelle di anni diversi con lievi variazioni di intestazione restano entrambe indicizzate (es. `2020_c10_liquidazione_pagamenti_pagopa.md` presente sia in `Comunicazioni 2020` sia in `Comunicazioni 2023`, entrambe apparse nei risultati di Query 5). Abbassare leggermente `NEAR_DUP_THRESHOLD` o deduplicare globalmente per `(filename_stem, canonical_shingles)` può ridurre ulteriormente queste ridondanze.

4. **Dimensione Ridotta del Benchmark Manuale:**
   - Il benchmark in `scripts/evaluate_rag.py` copre 10 query rappresentative costruite manualmente e verifica principalmente recall documentale, esistenza delle citazioni, copertura lessicale e astensione OOD. Non sostituisce una valutazione LLM-as-a-judge o umana su scala più ampia (50–100 query) con test specifici su documenti multi-tabella e confronti temporali tra versioni.
