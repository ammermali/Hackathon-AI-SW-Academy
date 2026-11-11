# Operator Copilot — Intelligent Knowledge, RAG & AI Knowledge-to-Course Engine

**Operator Copilot** è la piattaforma modulare Python + LangChain dedicata al supporto operativo e alla formazione continua degli operatori della Pubblica Amministrazione.

Il repository implementa due milestone integrate sulla stessa architettura applicativa (FastAPI + LangChain + ChromaDB + SQLite):
- **Milestone 1**: Motore **RAG** enterprise-ready con ingestion incrementale, retrieval ibrido, Smart Question Cache, storico ricerche, metriche e API REST.
- **Milestone 2**: **AI Knowledge-to-Course Engine** (`Knowledge Intelligence Engine` + `AI Course Generator`) per trasformare automaticamente la documentazione della knowledge base in argomenti strutturati, rilevazione di lacune, proposte formative, corsi modulari, lezioni tracciate alle fonti e quiz di verifica con workflow di approvazione umana.

---

## Milestone 1: Intelligent Knowledge & RAG Engine

- **Ingestion & Deduplicazione Intelligente (`src/operator_copilot/ingestion/`)**:
  - Scansione ricorsiva di `data/` (escludendo `INDEX.md` di riepilogo per evitare inquinamento del retrieval).
  - Parsing robusto (UTF-8 con fallback CP1252, gestione file corrotti/illeggibili senza blocco).
  - Estrazione metadati deterministici (`area_code`, `area_name`, `document_type`, `doc_year`, `title`, `file_hash`, `updated_at`).
  - Deduplicazione a due livelli: hash canonico esatto + near-duplicate detection (`Jaccard >= 0.90` su shingle tra documenti con titolo identico).
  - Chunking strutturale Markdown-aware (`MarkdownHeaderTextSplitter` + `RecursiveCharacterTextSplitter` con protezione delle tabelle e prefisso contestuale `[Area | Documento | Sezione]`).
- **Vector Store & Retrieval Ibrido (`src/operator_copilot/retrieval/`)**:
  - Persistenza su **ChromaDB** con indice incrementale (rileva file nuovi, modificati ed eliminati).
  - Retrieval ibrido **Dense Cosine Similarity + Sparse BM25 (`rank_bm25`)** con filtro metadati, reranking (copertura termini, acronimi PA, recency, diversità) e **soglia di rilevanza con astensione controllata** (`needs_escalation=True`).
- **Answer Generation & Sicurezza (`src/operator_copilot/generation/`)**:
  - Catena LangChain LCEL con configurazione centralizzata su **Qwen** (`LLM_PROVIDER=openai_compatible` / `ollama`, default `qwen2.5:7b-instruct`), supporto `openai` ed `extractive` (fallback controllato in assenza di endpoint attivo o timeout).
  - Risposte operative in italiano con passaggi numerati e citazioni reali (`document`, `section`, `chunk_id`).
  - Protezione anti-prompt-injection tramite delimitazione/sanitizzazione `<retrieved_context>` e mascheramento PII (`redact_pii()`).
- **Smart Question Cache (`src/operator_copilot/cache/`)**:
  - Normalizzazione domanda, hash SHA-256, TTL configurabile, invalidazione automatica su cambio `corpus_version`, `prompt_version` o `model_version`.
  - **Isolamento utente** (`user_scope="public"` condivisibile vs `user_scope="private"` isolato per `user_id`) ed esclusione automatica delle risposte con astensione (`needs_escalation=True`).
- **Storico, Feedback & Analytics (`src/operator_copilot/history/`, `analytics/`)**:
  - Persistenza su **SQLite** (senza duplicare testi/vettori dal vector store), retention configurabile e metriche reali (`cache_hit_rate`, latenze, topic più richiesti, `learning_readiness`).
- **API REST RAG (`src/operator_copilot/api/main.py`)**:
  - `POST /api/v1/rag/query`
  - `GET /api/v1/rag/history/{user_id}` e `DELETE /api/v1/rag/history/{user_id}`
  - `GET /api/v1/rag/metrics`
  - `GET /api/v1/rag/documents`
  - `POST /api/v1/rag/feedback`
  - `POST /api/v1/rag/ingest` (protetto da header `X-Admin-Key`)

---

## Milestone 2: AI Knowledge-to-Course Engine

- **Knowledge Intelligence Engine (`src/operator_copilot/knowledge_intelligence/`)**:
  - **`KnowledgeExtractor`**: riutilizza i chunk già indicizzati in ChromaDB (con fallback on-demand su `data/`) per estrarre procedure, regole, vincoli, concetti ricorrenti, esempi pratici (corretti ed `ERRATO`), errori frequenti, moduli software, ruoli target e passaggi sorgente.
  - **`TopicClassifier`**: classificazione estensibile su 9 categorie operative (`Assistenza tecnica`, `Gestione degli errori`, `Sicurezza e autorizzazioni`, `Normativa e regolamenti`, `Amministrazione e contabilità`, `Gestione documentale`, `Utilizzo del software`, `Best practice operative`, `Procedure operative`).
  - **`RelevanceScorer`**: valutazione trasparente su 8 fattori (con frequenza limitata al 10% del peso) separando nettamente `algorithmic_score`, `llm_score` e `unverifiable_factors`.
  - **`KnowledgeGapDetector`**: individuazione automatica di lacune `insufficient`, `incomplete` (es. PDF esterni mancanti), `outdated` (`KNOWLEDGE_OBSOLETE_YEARS=4`) e `contradictory` cross-documento.
  - **`OpportunityAggregator`**: aggrega 1 o più documenti correlati in proposte formative distinguendo corsi `documental` (regole/comunicazioni/assistenza) e `applicative` (workflow su software gestionali).
  - **`KnowledgeJobRunner`**: analisi incrementale asincrona (`ThreadPoolExecutor`) o sincrona con scope `full | document | category | area`, skip automatico dei documenti invariati (`file_hash`) e ripresa da checkpoint (`resume_job()`).
- **AI Course Generator & Governance (`src/operator_copilot/course_generator/`)**:
  - **Prompt Modulari (`prompts.py`)**: 8 prompt versionati (`academy-v1.0`) con protezione `<retrieved_context>`.
  - **`AICourseGenerator`**: genera curriculum, moduli, lezioni complete (spiegazione, procedure, esempi, errori frequenti, esercitazioni, riepilogo), quiz ancorati ai chunk (`Quiz`, `QuizQuestion`) e rigenerazione mirata della singola lezione.
  - **`GroundingVerifier`**: verifica `LessonSource`, sovrapposizione lessicale, fonti obsolete/rimosse e conflitti di versione (`Cityware Client` / `CWOL`), assegnando `VERIFIED`, `WARNINGS` o `UNVERIFIED`.
  - **`CourseLifecycleManager`**: workflow controllato `PROPOSED -> GENERATED -> UNDER_REVIEW -> APPROVED -> PUBLISHED` (nessuna auto-pubblicazione, blocco su `UNVERIFIED`), snapshot `CourseRevision`, audit `CourseApprovalEvent` e rilevazione impatti da aggiornamento fonti (`NEEDS_UPDATE`).
- **API REST Academy (`src/operator_copilot/api/academy_router.py`)**:
  - `GET /api/v1/academy/llm-status`
  - `POST /api/v1/academy/analysis/jobs`, `GET /api/v1/academy/analysis/jobs/{job_id}`, `POST /api/v1/academy/analysis/jobs/{job_id}/resume`
  - `GET /api/v1/academy/topics`, `GET /api/v1/academy/topics/{topic_id}/score`, `GET /api/v1/academy/gaps`
  - `GET /api/v1/academy/opportunities`, `POST /api/v1/academy/opportunities/build`
  - `POST /api/v1/academy/courses/generate`, `GET /api/v1/academy/courses`, `GET /api/v1/academy/courses/{course_id}`
  - `PATCH /api/v1/academy/courses/{course_id}/lessons/{lesson_id}`, `POST /api/v1/academy/courses/{course_id}/lessons/{lesson_id}/regenerate`
  - `POST /api/v1/academy/courses/{course_id}/quizzes/generate`, `POST /api/v1/academy/courses/{course_id}/validate`
  - `POST /api/v1/academy/courses/{course_id}/lifecycle`, `GET /api/v1/academy/courses/{course_id}/sources`, `GET /api/v1/academy/courses/{course_id}/revisions`, `GET /api/v1/academy/courses/impact-check`
  - Multi-tenancy (`X-Tenant-ID`), RBAC (`X-User-Role`, `allowed_roles`) e protezione anti-spoofing con `X-Admin-Key` sulle operazioni privilegiate e sul ruolo `admin`.

---

## Installazione e Avvio

### 1. Requisiti
- Python **3.11+** (verificato su Python **3.13.9**)

### 2. Installazione Dipendenze (con o senza `.venv`)
```bash
# Opzione A: installazione diretta da pyproject.toml (anche senza .venv)
pip install -e ".[dev]"

# Opzione B: con ambiente virtuale dedicato
python -m venv .venv
# Windows PowerShell:
.\.venv\Scripts\Activate.ps1
# Linux/macOS:
# source .venv/bin/activate

pip install -r requirements.txt
pip install -e . --no-deps
```

### 3. Configurazione (`.env`)
Copiare `.env.example` in `.env` e impostare il provider desiderato:
```bash
cp .env.example .env
```
- **Embeddings locali gratuiti**: `EMBEDDING_PROVIDER=huggingface` (`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`).
- **LLM Qwen centralizzato**: impostare `LLM_PROVIDER=ollama` (es. `LLM_BASE_URL=http://localhost:11434/v1` e `LLM_MODEL=qwen2.5:7b-instruct`) oppure `openai_compatible` con `LLM_API_KEY` e `LLM_BASE_URL`; in assenza di endpoint attivo entra automaticamente il fallback deterministico sicuro.
- **Sicurezza e Knowledge-to-Course**: personalizzare `ADMIN_API_KEY` (default di sviluppo `dev-admin-key-change-me`), `COURSE_PROMPT_VERSION=academy-v1.0`, `KNOWLEDGE_OBSOLETE_YEARS=4`, `PII_REDACT_BEFORE_LLM=true`.

### 4. Analisi Dati & Ingestion
```bash
# Analisi esplorativa della cartella data/
python scripts/analyze_data.py

# Indicizzazione completa (rebuild) o incrementale
python scripts/ingest_documents.py --rebuild
```

### 5. Avvio API FastAPI & Uso Rapido Milestone 2
```bash
uvicorn operator_copilot.api.main:app --reload --port 8000
```
Documentazione interattiva Swagger/OpenAPI disponibile su `http://localhost:8000/docs`:
1. Verifica configurazione Qwen: `GET /api/v1/academy/llm-status`
2. Genera subito un corso (con `X-Admin-Key`) via `POST /api/v1/academy/courses/generate` passando ad esempio:
   ```json
   {
     "document_source": "2024_c07_modalita_corretta_richiesta_assistenza_clienti.md",
     "course_type": "documental",
     "allowed_roles": ["operatore", "admin"]
   }
   ```
3. Consulta i corsi e le relative lezioni create tramite `GET /api/v1/academy/courses` o `GET /api/v1/academy/courses/{course_id}`.

### 6. Test Automatici & Valutazione
```bash
# Suite completa di test automatici (RAG + Knowledge-to-Course Engine)
pytest

# Valutazione quantitativa RAG su domande reali estratte da data/
python scripts/evaluate_rag.py
```

---

## Documentazione Progetto

<<<<<<< Updated upstream
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md): architettura tecnica, flussi, schema DB e decisioni progettuali.
=======
- [`docs/DATA_ANALYSIS.md`](docs/DATA_ANALYSIS.md): audit completo dei 1.532 documenti in `data/` e delle criticità rilevate.
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md): architettura tecnica della Milestone 1 (RAG Engine, flussi, schema DB, cache).
- [`docs/MILESTONE_2_KNOWLEDGE_TO_COURSE.md`](docs/MILESTONE_2_KNOWLEDGE_TO_COURSE.md): specifica tecnica completa della Milestone 2 (Knowledge Intelligence Engine, AI Course Generator, Grounding, Lifecycle, 13 nuove tabelle DB ed endpoint Academy).
- [`docs/RAG_EVALUATION.md`](docs/RAG_EVALUATION.md): dataset di valutazione reale, metriche misurate e limiti.
>>>>>>> Stashed changes
