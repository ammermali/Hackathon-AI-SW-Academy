# Criticità Note e Debito Tecnico Residuo (Stato MVP)

Questo documento raccoglie le criticità di sicurezza, isolamento multi-tenant, concorrenza e infrastruttura emerse durante la Codebase Audit & Technical Debt Review che **non sono state modificate intenzionalmente** in questa fase MVP.

Per un ambiente di sviluppo/demo o pilota controllato questi aspetti sono gestibili operativamente; **prima di un rilascio in produzione multi-organizzazione o esposto su rete pubblica**, è raccomandato pianificarne la risoluzione nell'ordine di priorità indicato.

---

## 1. Criticità ad Alta Priorità (Da affrontare prima della produzione)

### B1 — Stored XSS nella Dashboard Owner UI (`/owner`)
- **Dove:** `src/operator_copilot/owner_dashboard/ui.py` (righe 445–539)
- **Dettaglio tecnico:** Il frontend Vanilla JS costruisce dinamicamente tabelle e pannelli di dettaglio interpolando campi utente, topic e metriche tramite `.innerHTML` senza sanitizzazione HTML, includendo attributi inline come `onclick="loadUserDetail('${encodeURIComponent(u.user_id)}')"`. Poiché `encodeURIComponent` non codifica l'apice singolo (`'`), un `user_id` o un nome manipolato potrebbe rompere l'attributo ed eseguire JavaScript arbitrario nel browser dell'Owner autenticato.
- **Impatto:** Rischio di esecuzione script nel contesto della sessione Owner (es. esfiltrazione di `X-Owner-Key` o azioni amministrative non autorizzate).
- **Mitigazione consigliata:** Sostituire l'interpolazione HTML con creazione DOM sicura (`textContent`, `document.createElement`) o applicare un helper di escaping HTML/attributo rigoroso (`&`, `<`, `>`, `"`, `'`) e usare `addEventListener` con `dataset`.

### B2 — Assenza di Autenticazione/Autorizzazione e Isolamento Tenant sulle API RAG Milestone 1 (IDOR / BOLA)
- **Dove:**
  - `src/operator_copilot/api/main.py` (righe 65–143: `/api/v1/rag/query`, `/api/v1/rag/history/{user_id}` GET/DELETE, `/api/v1/rag/feedback`, `/api/v1/rag/metrics`, `/api/v1/rag/documents`)
  - `src/operator_copilot/db/models.py` (righe 32–100: `QueryHistory`, `QueryFeedback`, `CacheEntry`)
- **Dettaglio tecnico:** Gli endpoint RAG della Milestone 1 non utilizzano `build_caller_context_dependency` / `assert_user_access` e accettano qualsiasi `user_id` fornito nella query o nel path senza verificare l'identità del chiamante né associare un `tenant_id` ai record `QueryHistory`, `QueryFeedback` e `CacheEntry`.
- **Impatto:** Un chiamante può interrogare o cancellare lo storico (`DELETE /api/v1/rag/history/{user_id}`) di qualunque utente e accedere alle metriche aggregate senza controllo ruoli/tenant.
- **Mitigazione consigliata:** Aggiungere la colonna `tenant_id` (con migrazione DB) a `QueryHistory`, `QueryFeedback` e `CacheEntry` e applicare le dipendenze di autorizzazione già presenti in `src/operator_copilot/api/dependencies.py`.

### B3 — Cross-Tenant Leakage nell'Adaptive Learning da `QueryHistory`
- **Dove:**
  - `src/operator_copilot/adaptive_learning/gap_detector.py` (righe 49–58)
  - `src/operator_copilot/adaptive_learning/profiler.py` (righe 159–168)
  - `src/operator_copilot/adaptive_learning/service.py` (riga 553: `delete_user_learning_data`)
- **Dettaglio tecnico:** Connessa a B2: poiché `QueryHistory` non possiede `tenant_id`, il profilo utente, il rilevatore di lacune e la cancellazione GDPR (`delete_user_learning_data`) filtrano la cronologia delle domande RAG solo per `user_id`.
- **Impatto:** Se lo stesso `user_id` esistesse su due tenant distinti, le sue interazioni RAG (e la relativa cancellazione GDPR) verrebbero condivise tra tenant diversi.
- **Mitigazione consigliata:** Propagare il filtro `tenant_id` su tutte le query verso `QueryHistory` contestualmente alla risoluzione di B2.

### B4 — Allocazione di `ThreadPoolExecutor` per singola richiesta HTTP
- **Dove:**
  - `src/operator_copilot/api/academy_router.py` (righe 166–177) -> `KnowledgeJobRunner.__init__` (`src/operator_copilot/knowledge_intelligence/job_runner.py`, riga 39)
  - `src/operator_copilot/api/customquiz_router.py` (righe 35–36) -> `CustomQuizEngine` -> `CustomQuizGenerator.__init__` (`src/operator_copilot/adaptive_learning/quiz_generator.py`, riga 49)
- **Dettaglio tecnico:** Gli helper `_services()` (Academy) e `_engine()` (Custom Quiz) vengono istanziati ad ogni richiesta HTTP, creando ogni volta nuovi `ThreadPoolExecutor` dedicati ai job asincroni/LLM.
- **Impatto:** Sotto traffico elevato può causare crescita progressiva di thread/risorse OS non riutilizzati e difficoltà di shutdown ordinato.
- **Mitigazione consigliata:** Istantziare `KnowledgeJobRunner` e `CustomQuizGenerator`/`CustomQuizEngine` come singleton a livello di `app.state` (inizializzati nel `lifespan` FastAPI) con chiusura esplicita allo shutdown.

### B5 — Fiducia su Header Auto-Dichiarati e Chiavi Statiche Globali
- **Dove:**
  - `src/operator_copilot/api/dependencies.py` (righe 16–85: `build_caller_context_dependency`, `build_owner_context_dependency`)
  - `src/operator_copilot/config/settings.py` (righe 84–85: `admin_api_key`, `owner_api_key`)
- **Dettaglio tecnico:** L'identità applicativa (`X-User-ID`, `X-Tenant-ID`, `X-User-Role`, `X-Owner-Scope`) viene letta direttamente dagli header HTTP inviati dal client, mentre l'autenticazione privilegia chiavi statiche condivise (`admin_api_key`, `owner_api_key`) valide trasversalmente per qualsiasi tenant.
- **Impatto:** Adatto a un MVP o a chiamate protette dietro un API Gateway fidato, ma insufficiente per esposizione diretta ad utenti finali senza token firmati.
- **Mitigazione consigliata:** Sostituire gli header auto-dichiarati con JWT/OIDC (es. OAuth2 Bearer) firmati, derivando `user_id`, `tenant_id`, `role` e `scope` esclusivamente dai claim verificati del token.

### B6 — Esposizione di `correct_answer` nei Payload dei Quiz Tradizionali
- **Dove:** `src/operator_copilot/api/academy_router.py` (righe 125–137: `_serialize_course` -> `QuizQuestionResponse.correct_answer`)
- **Dettaglio tecnico:** Gli endpoint `GET /api/v1/academy/courses` e `GET /api/v1/academy/courses/{course_id}` restituiscono anche la risposta corretta (`correct_answer`) di ciascuna domanda del quiz didattico prima che l'utente effettui il submit. *(Nota: i Custom Quiz già omettono `correct_answer` fino al completamento).*
- **Impatto:** Un utente tecnico può leggere le risposte corrette ispezionando la risposta JSON del browser/API.
- **Mitigazione consigliata:** Nascondere `correct_answer` nella serializzazione standard del corso riservandola al ruolo `admin`/`owner` o restituendola solo post-submit.

### B7 — Verifica Path Traversal Mancante nel Fallback Filesystem di `load_document_bundle`
- **Dove:** `src/operator_copilot/knowledge_intelligence/extractor.py` (righe 123–135)
- **Dettaglio tecnico:** Nel fallback su filesystem di `load_document_bundle(doc_ref)`, viene costruito `self.settings.data_dir / doc_ref` (e successivamente `rglob`) senza verificare preventivamente che il percorso risolto (`.resolve().relative_to(data_dir.resolve())`) resti confinato all'interno di `data_dir`.
- **Impatto:** Un parametro `document_source` con sequenze `../` passato da un chiamante Admin autorizzato potrebbe leggere file markdown o testuali fuori dalla cartella `data_dir`.
- **Mitigazione consigliata:** Validare che `doc_ref` non contenga path assoluti o componenti `..` e verificare `candidate.resolve().relative_to(data_dir.resolve())` prima di leggere il file.

---

## 2. Miglioramenti Architetturali Opzionali Rimandati (Sezione D — Non Eseguiti)

### D1 — Assenza di Rate Limiting e Protezione DoS sugli Endpoint LLM
- **Dove:** Endpoint di generazione e query (`POST /api/v1/rag/query`, `POST /api/v1/academy/courses/generate`, `POST /api/v1/customquiz/generate`).
- **Dettaglio:** Non è presente un limitatore di richieste per IP/utente/tenant; richieste ripetute in parallelo possono saturare la quota o i worker LLM/Ollama.
- **Mitigazione post-MVP:** Introdurre rate limiting (es. `slowapi` o a livello di reverse proxy/API Gateway).

### D3 — Partizionamento di ChromaDB e Indice BM25 per Tenant e Ruolo a Livello di Retrieval
- **Dove:** `src/operator_copilot/retrieval/retriever.py` e `src/operator_copilot/retrieval/rag_engine.py`.
- **Dettaglio:** I documenti vettoriali (ChromaDB) e l'indice full-text (BM25) risiedono in un'unica collezione condivisa; il filtro per ruolo avviene tramite metadata/post-filtering anziché su collezioni/namespace isolati per `tenant_id`.
- **Mitigazione post-MVP:** Introdurre `tenant_id` nei metadati di indicizzazione (o collezioni Chroma per tenant) ed estendere il filtro pre-retrieval.

### D4 — Hardening HTTP (CORS, Security Headers, HTTPS)
- **Dove:** `src/operator_copilot/api/main.py` e configurazione runtime Uvicorn.
- **Dettaglio:** Non sono configurati `CORSMiddleware` espliciti né header di sicurezza HTTP (`Content-Security-Policy`, `X-Frame-Options`, `Strict-Transport-Security`) per `/owner` e le API, assumendo che il servizio operi dietro un reverse proxy TLS in produzione.
- **Mitigazione post-MVP:** Configurare una whitelist CORS esplicita via `Settings` e delegare/aggiungere header CSP e HSTS sul proxy o tramite middleware dedicato.
