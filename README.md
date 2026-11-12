# AI Software Academy — Intelligent Knowledge, RAG & AI Knowledge-to-Course Engine

**AI Software Academy** è la piattaforma modulare Python + LangChain dedicata al supporto operativo e alla formazione continua degli operatori della Pubblica Amministrazione.

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

### 7. File bat
Doppio clic su `start-demo.bat`. (Avvia tutto).