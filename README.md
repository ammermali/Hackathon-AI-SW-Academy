# Operator Copilot — Milestone 1: Intelligent Knowledge & RAG Engine

**Operator Copilot** è la piattaforma modulare Python + LangChain dedicata al supporto operativo e alla futura formazione continua degli operatori aziendali.

In questa **Milestone 1** è implementato esclusivamente il **motore RAG** (ingestion incrementale, vector store persistente, retrieval ibrido, generazione ancorata con citazioni, Smart Question Cache, storico ricerche, metriche e API FastAPI), progettato per integrarsi in futuro con corsi generati da AI, quiz personalizzati e dashboard formative.

---

## Caratteristiche Implementate

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
  - Catena LangChain LCEL con supporto `openai`, `openai_compatible`, `ollama` ed `extractive` (fallback controllato in assenza di API key o timeout).
  - Risposte operative in italiano con passaggi numerati e citazioni reali (`document`, `section`, `chunk_id`).
  - Protezione anti-prompt-injection tramite delimitazione e sanitizzazione di `<retrieved_context>`.
- **Smart Question Cache (`src/operator_copilot/cache/`)**:
  - Normalizzazione domanda, hash SHA-256, TTL configurabile, invalidazione automatica su cambio `corpus_version`, `prompt_version` o `model_version`.
  - **Isolamento utente** (`user_scope="public"` condivisibile vs `user_scope="private"` isolato per `user_id`).
  - Esclusione automatica dalla cache delle risposte con evidenze insufficienti (`needs_escalation=True`).
- **Storico, Feedback & Analytics (`src/operator_copilot/history/`, `analytics/`)**:
  - Persistenza su **SQLite** (senza duplicare testi/vettori dal vector store).
  - Raggruppamento ricerche per argomento (`topics_summary`), retention configurabile e cancellazione per `user_id`.
  - Metriche reali: latenze, `cache_hit_rate`, `error_rate`, documenti più consultati, argomenti più richiesti, feedback e segnali per futura personalizzazione.
- **API REST FastAPI (`src/operator_copilot/api/main.py`)**:
  - `POST /api/v1/rag/query`
  - `GET /api/v1/rag/history/{user_id}` e `DELETE /api/v1/rag/history/{user_id}`
  - `GET /api/v1/rag/metrics`
  - `GET /api/v1/rag/documents`
  - `POST /api/v1/rag/feedback`
  - `POST /api/v1/rag/ingest` (protetto da header `X-Admin-Key`)

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
- Per usare **embeddings locali gratuiti** (`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`), impostare `EMBEDDING_PROVIDER=huggingface`.
- Per usare un LLM OpenAI/compatibile/Ollama impostare `LLM_PROVIDER` e `LLM_API_KEY` (oppure `LLM_PROVIDER=extractive` per sintesi estrattiva locale senza API key).

### 4. Analisi Dati & Ingestion
```bash
# Analisi esplorativa della cartella data/
python scripts/analyze_data.py

# Indicizzazione completa (rebuild) o incrementale
python scripts/ingest_documents.py --rebuild
```

### 5. Avvio API FastAPI
```bash
uvicorn operator_copilot.api.main:app --reload --port 8000
```
Documentazione interattiva Swagger/OpenAPI disponibile su `http://localhost:8000/docs`.

### 6. Test Automatici & Valutazione
```bash
# Suite di test automatici (unit + integration)
pytest

# Valutazione quantitativa su domande reali estratte da data/
python scripts/evaluate_rag.py
```

---

## Documentazione Progetto

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md): architettura tecnica, flussi, schema DB e decisioni progettuali.
