# Operator Copilot — Reference Completo degli Entry Point

Questo documento elenca tutti gli entry point attualmente presenti nel repository (server HTTP, script CLI, endpoint REST FastAPI e facciate Python programmatiche), con relativi **parametri**, **cosa fanno** e **cosa richiedono** (header, permessi, payload e prerequisiti).

---

## 1. Header HTTP comuni, Autenticazione e Isolamento

### Operazioni amministrative (`verify_admin_key`)
- **Header richiesto**: `X-Admin-Key: <ADMIN_API_KEY>` (definito in `.env` / `Settings.admin_api_key`).
- Se mancante o errato, l'endpoint restituisce `403 Forbidden`.

### Contesto Multi-Tenant, RBAC e Isolamento Utente (`build_caller_context_dependency` / `assert_user_access`)
Usato su tutti gli endpoint `/api/v1/academy/*` e `/api/v1/customquiz/*`:
- `X-Tenant-ID` *(header, opzionale, default `"default"`)*: isola tutti i dati per tenant.
- `X-User-Role` *(header, opzionale, default `"operatore"`)*: ruolo dichiarativo dell'utente (`operatore`, `admin`, ecc.). **Nota anti-spoofing**: se `X-User-Role: admin`, è obbligatorio fornire anche `X-Admin-Key` valido, altrimenti viene restituito `403 Forbidden`.
- `X-User-ID` *(header, opzionale su alcune route Academy, **obbligatorio e corrispondente** su Custom Quiz — default `"anonymous"`)*: su `/api/v1/customquiz/*` e `/api/v1/academy/.../quizzes/.../submit`, `assert_user_access` blocca `anonymous` e blocca l'accesso ai dati di altri utenti (`403 Forbidden`), salvo `admin` autenticato con `X-Admin-Key`.

### Contesto Owner Dashboard & Ambito (`build_owner_context_dependency`)
Usato su tutti gli endpoint `/api/v1/owner/*`:
- `X-User-Role` *(obbligatorio)*: deve essere `"owner"` (case-insensitive). Qualsiasi altro ruolo (incluso `operatore`, `anonymous` o `admin` privo di credenziali Owner) riceve `403 Forbidden`.
- `X-Owner-Key` *(obbligatorio)*: confrontato in tempo costante con `Settings.owner_api_key` (`OWNER_API_KEY`). Se mancante o errato, restituisce `403 Forbidden`.
- `X-User-ID` *(obbligatorio)*: identificativo non `"anonymous"` dell'Owner (registrato in `OwnerAuditLog`).
- `X-Tenant-ID` *(opzionale, default `"default"`)*: isola rigorosamente tutte le viste, aggregazioni e log di audit per tenant.
- `X-Owner-Scope` *(opzionale)*: elenco CSV di `amministrazione` consentite (es. `Comune Alfa,Comune Beta`) per limitare ulteriormente la visibilità dell'Owner.

---

## 2. Entry Point Server & Script CLI

| Entry Point | Comando / Utilizzo | Parametri / Flag | Cosa fa | Cosa richiede |
| :--- | :--- | :--- | :--- | :--- |
| **FastAPI App** (`src/operator_copilot/api/main.py`) | `uvicorn operator_copilot.api.main:app --host 127.0.0.1 --port 8000` | `--host`, `--port`, `--reload` (standard Uvicorn) | Avvia il server REST unico esponendo `/health`, `/owner`, `/api/v1/rag/*`, `/api/v1/academy/*`, `/api/v1/customquiz/*`, `/api/v1/owner/*` e Swagger UI su `/docs`. | Dipendenze installate nel `.venv`, `.env` configurato (opzionale, usa default `Settings`). |
| **Ingestion CLI** (`scripts/ingest_documents.py`) | `python scripts/ingest_documents.py [--rebuild] [--max-files N]` | `--rebuild` *(bool flag, default `False`)*: ricostruisce l'indice da zero.<br>`--max-files` *(int, opzionale)*: limita il numero di file processati. | Scansiona `DATA_DIR`, estrae e normalizza chunk con metadati, indicizza in ChromaDB e traccia lo stato in SQLite (`DocumentMetadata`). | Cartella `DATA_DIR` esistente e leggibile; provider embedding configurato. |
| **Data Analysis CLI** (`scripts/analyze_data.py`) | `python scripts/analyze_data.py` | Nessuno (legge `DATA_DIR = Path("data")` hardcoded nello script). | Analizza statisticamente i file in `data/` (estensioni, duplicati, dimensioni, tabelle, PII mascherate, anni, breadcrumb) stampando un report JSON. | Presenza della directory `data/` nella working directory corrente. |
| **RAG Evaluation CLI** (`scripts/evaluate_rag.py`) | `python scripts/evaluate_rag.py` | Nessuno (usa `EVAL_DATASET` interno di 10 query: 8 in-domain + 2 out-of-domain). | Pulisce la cache, esegue le 10 query di benchmark su `RAGEngine`, misura cold/warm latency, Recall@k, citazioni reali, term grounding e astensione. | Vector store già indicizzato su `data/` tramite `ingest_documents.py`. |

---

## 3. Endpoint HTTP — Sistema & RAG (Milestone 1)

Definiti in [`src/operator_copilot/api/main.py`](../src/operator_copilot/api/main.py).

| Metodo & Path | Parametri (Path / Query / Body) | Cosa fa | Cosa richiede |
| :--- | :--- | :--- | :--- |
| `GET /health` | Nessuno. | Restituisce stato servizio (`status: "ok"`), versione package (`version`) e versione corrente della knowledge base (`corpus_version`). | Nessun header richiesto. |
| `POST /api/v1/rag/query` | **Body (`RAGQueryRequest`)**:<br>- `query` *(str, obbl., 2..2000 char)*: domanda in linguaggio naturale<br>- `user_id` *(str, default `"anonymous"`)*<br>- `session_id` *(str, default `"default_session"`)*<br>- `top_k` *(int \| None, 1..20, opz.)*<br>- `filters` *(dict \| None, opz.)*: filtri metadata (`area_name`, `document_type`, `doc_year`, ecc.; ignora placeholder Swagger)<br>- `user_scope` *(`"public"` \| `"private"`, default `"public"`)*: isolamento cache | Esegue lookup nella Smart Cache, retrieval ibrido (Vector + BM25 + reranking), generazione risposta ancorata alle fonti (Qwen / extractive fallback), anti-injection e salvataggio in `QueryHistory`. | Corpus indicizzato in ChromaDB per ottenere risposte grounded (altrimenti attiva astensione `needs_escalation=True`). |
| `GET /api/v1/rag/history/{user_id}` | **Path**: `user_id` *(str)*<br>**Query**: `limit` *(int, 1..200, default `20`)* | Recupera le ultime `N` interrogazioni dell'utente `user_id`, raggruppate per argomento (`topics_summary`). | Nessun header obbligatorio. |
| `DELETE /api/v1/rag/history/{user_id}` | **Path**: `user_id` *(str)* | Elimina lo storico ricerche e feedback associati all'utente `user_id` in `QueryHistory`. | Nessun header obbligatorio. |
| `GET /api/v1/rag/metrics` | Nessuno. | Restituisce statistiche aggregate RAG (query totali, cache hit rate, latenze medie, distribuzione intent, top topic, stato documenti e `learning_readiness`). | Nessun header obbligatorio. |
| `GET /api/v1/rag/documents` | **Query**:<br>- `status` *(str \| None, opz.)*: filtro stato indicizzazione<br>- `limit` *(int, 1..2000, default `200`)* | Elenca i documenti tracciati in `DocumentMetadata` con metadati, hash, anno e stato. | Nessun header obbligatorio. |
| `POST /api/v1/rag/feedback` | **Body (`FeedbackRequest`)**:<br>- `query_history_id` *(int, >= 1, obbl.)*<br>- `user_id` *(str, default `"anonymous"`)*<br>- `rating` *(int, 1..5, obbl.)*: valori `<= 2` alimentano segnali di difficoltà in Milestone 3<br>- `comment` *(str \| None, max 1000, opz.)* | Registra il feedback dell'operatore su una precedente risposta RAG in `QueryFeedback`. | Esistenza del record `query_history_id` in `QueryHistory` (altrimenti `404`). |
| `POST /api/v1/rag/ingest` | **Body (`IngestRequest`)**:<br>- `rebuild` *(bool, default `False`)*<br>- `max_files` *(int \| None, >= 1, opz.)* | Avvia l'ingestion controllata dei documenti da `DATA_DIR` a ChromaDB/SQLite. | **Header obbligatorio**: `X-Admin-Key`. |

---

## 4. Endpoint HTTP — AI Knowledge-to-Course & Academy (Milestone 2 + estensione Quiz)

Definiti in [`src/operator_copilot/api/academy_router.py`](../src/operator_copilot/api/academy_router.py). Tutti gli endpoint accettano gli header contestuali `X-Tenant-ID`, `X-User-Role`, `X-User-ID`.

### Diagnostica LLM & Knowledge Intelligence

| Metodo & Path | Parametri (Path / Query / Body) | Cosa fa | Cosa richiede |
| :--- | :--- | :--- | :--- |
| `GET /api/v1/academy/llm-status` | Nessuno. | Restituisce configurazione LLM attiva (`provider`, `configured_model`, `expected_model_family`, `llm_runtime_active`, stato validazione Qwen). | Nessun header obbligatorio. |
| `POST /api/v1/academy/analysis/jobs` | **Body (`AnalysisJobRequest`)**:<br>- `scope_type` *(`"full"` \| `"document"` \| `"category"` \| `"area"`, default `"full"`)*<br>- `scope_value` *(str \| None, opz.)*: nome/id documento, categoria o area<br>- `max_documents` *(int \| None, 1..5000, opz.)*<br>- `force_reanalyze` *(bool, default `False`)*<br>- `allowed_roles` *(list[str], default `["operatore", "admin"]`)*<br>- `run_async` *(bool, default `True`)* | Avvia l'analisi incrementale della KB: estrazione conoscenze, classificazione topic, scoring multi-fattore, gap nella KB e proposte formative (`TrainingOpportunity`). | **Header obbligatorio**: `X-Admin-Key`. Documenti indicizzati o presenti in `DATA_DIR`. |
| `POST /api/v1/academy/analysis/jobs/{job_id}/resume` | **Path**: `job_id` *(str)*<br>**Query**: `run_async` *(bool, default `False`)* | Riprende un job di analisi interrotto/fallito dall'ultimo documento completato. | **Header obbligatorio**: `X-Admin-Key`. `job_id` appartenente al tenant chiamante (`404` se assente). |
| `GET /api/v1/academy/analysis/jobs/{job_id}` | **Path**: `job_id` *(str)* | Restituisce avanzamento (`processed_documents`, `skipped_unchanged`, `failed_documents`) e stato del job. | `X-Tenant-ID` corrispondente al job (`404` se assente). |
| `GET /api/v1/academy/topics` | **Query**:<br>- `category` *(str \| None, opz.)*<br>- `area_name` *(str \| None, opz.)*<br>- `limit` *(int, 1..500, default `100`)* | Elenca gli argomenti estratti dalla KB visibili al ruolo/tenant corrente. | Nessun header admin richiesto; filtra per `X-Tenant-ID` e `allowed_roles`. |
| `GET /api/v1/academy/topics/{topic_id}/score` | **Path**: `topic_id` *(str)* | Restituisce il punteggio di rilevanza didattica dettagliato (score algoritmico, eventuale score LLM, fattori e `unverifiable_factors`). | `topic_id` accessibile a tenant e ruolo correnti (`404` se assente). |
| `GET /api/v1/academy/gaps` | **Query**:<br>- `gap_type` *(str \| None, opz.)*: es. `insufficient`, `outdated`, `contradictory`<br>- `limit` *(int, 1..500, default `100`)* | Elenca i knowledge gap rilevati nella documentazione aziendale. | Filtra per `X-Tenant-ID` e `allowed_roles`. |
| `GET /api/v1/academy/opportunities` | **Query**: `limit` *(int, 1..500, default `100`)* | Elenca le proposte di corso (`TrainingOpportunity`) ordinate per `relevance_score`. | Filtra per `X-Tenant-ID` e `allowed_roles`. |
| `POST /api/v1/academy/opportunities/build` | **Body (`OpportunityBuildRequest`)**:<br>- `document_source` *(str \| None, opz.)*<br>- `area_name` *(str \| None, opz.)*<br>- `allowed_roles` *(list[str], default `["operatore", "admin"]`)* | Aggrega argomenti correlati (o analizza un singolo documento) per creare proposte formative (`TrainingOpportunity`). | **Header obbligatorio**: `X-Admin-Key`. Se non passa `document_source`, richiede almeno un `ExtractedTopic` già estratto (`404` altrimenti). |

### AI Course Generator, Quiz Didattici & Lifecycle

| Metodo & Path | Parametri (Path / Query / Body) | Cosa fa | Cosa richiede |
| :--- | :--- | :--- | :--- |
| `POST /api/v1/academy/courses/generate` | **Body (`CourseGenerateRequest`)**:<br>- `opportunity_id` *(str \| None, opz.)*<br>- `document_source` *(str \| None, opz.)*<br>- `course_type` *(`"documental"` \| `"applicative"` \| `None`, opz.)*<br>- `allowed_roles` *(list[str], default `["operatore", "admin"]`)* | Genera un corso strutturato completo (curriculum, moduli, lezioni, esercizi, fonti tracciate) in stato `GENERATED` (mai pubblicato automaticamente). | **Header obbligatorio**: `X-Admin-Key`. Richiede almeno uno tra `opportunity_id` o `document_source` (`400` se entrambi assenti/placeholder `"string"`, `404` se non trovato). |
| `GET /api/v1/academy/courses` | **Query**: `lifecycle_status` *(str \| None, opz.)*: es. `GENERATED`, `UNDER_REVIEW`, `APPROVED`, `PUBLISHED` | Elenca tutti i corsi completi (inclusi moduli, lezioni e quiz) accessibili al ruolo e al tenant corrente. | Filtra per `X-Tenant-ID` e `allowed_roles`. |
| `GET /api/v1/academy/courses/impact-check` | **Query**: `mark_needs_update` *(bool, default `True`)* | Verifica se i documenti sorgente dei corsi hanno subito aggiornamenti rispetto a `corpus_version_at_generation` e marca i corsi impattati. | Nessun header admin richiesto; opera su `X-Tenant-ID`. |
| `GET /api/v1/academy/courses/{course_id}` | **Path**: `course_id` *(str)* | Restituisce il dettaglio completo di un corso (curriculum, moduli, lezioni, fonti e quiz). | Corso esistente nel tenant e compatibile con `X-User-Role`. |
| `PATCH /api/v1/academy/courses/{course_id}/lessons/{lesson_id}` | **Path**: `course_id`, `lesson_id` *(str)*<br>**Body (`LessonUpdateRequest`)**:<br>- `title`, `objective`, `explanation`, `summary` *(str \| None, opz.)*<br>- `procedures` *(list[str] \| None, opz.)*<br>- `change_summary` *(str, default `"Modifica manuale contenuti lezione"`)* | Modifica manualmente una lezione, riesegue il grounding check (`GroundingVerifier`) e registra una nuova `CourseRevision`. | **Header obbligatorio**: `X-Admin-Key`. Corso e lezione esistenti nel tenant. |
| `POST /api/v1/academy/courses/{course_id}/lessons/{lesson_id}/regenerate` | **Path**: `course_id`, `lesson_id` *(str)* | Rigenera i contenuti della lezione a partire dalle fonti documentali originali creando una nuova revisione. | **Header obbligatorio**: `X-Admin-Key`. Corso e lezione esistenti nel tenant. |
| `POST /api/v1/academy/courses/{course_id}/quizzes/generate` | **Path**: `course_id` *(str)*<br>**Body (`QuizGenerateRequest`)**:<br>- `lesson_id` *(str \| None, opz.)*<br>- `num_questions` *(int, 1..20, default `5`)* | Genera e persiste un **quiz didattico tradizionale** grounded sulle `LessonSource` del corso o della singola lezione. | **Header obbligatorio**: `X-Admin-Key`. Corso esistente nel tenant. |
| `POST /api/v1/academy/courses/{course_id}/quizzes/{quiz_id}/submit` | **Path**: `course_id`, `quiz_id` *(str)*<br>**Body (`CourseQuizSubmitRequest`)**:<br>- `user_id` *(str, 1..128 char, obbl.)*<br>- `answers` *(dict[str, str], obbl.)*: mappa `{question_id: risposta}` | Valuta e salva il tentativo dell'utente (`CourseQuizAttempt`) su un quiz tradizionale del corso e aggiorna automaticamente `LearningGap` e `UserKnowledgeProfile`. | **Isolamento utente** (`assert_user_access`): `X-User-ID` deve coincidere con `payload.user_id` (oppure `admin` autenticato con `X-Admin-Key`). Corso e quiz esistenti. |
| `POST /api/v1/academy/courses/{course_id}/validate` | **Path**: `course_id` *(str)* | Esegue la verifica di grounding, fonti reali, documenti obsoleti e contraddizioni sul corso. | Corso esistente nel tenant. |
| `POST /api/v1/academy/courses/{course_id}/lifecycle` | **Path**: `course_id` *(str)*<br>**Body (`LifecycleActionRequest`)**:<br>- `target_status` *(`"UNDER_REVIEW"` \| `"APPROVED"` \| `"REJECTED"` \| `"PUBLISHED"`)*<br>- `notes` *(str, default `""`)* | Gestisce le transizioni di stato del corso registrando eventi di approvazione (`CourseApprovalEvent`). Blocca la pubblicazione se il grounding fallisce. | **Header obbligatorio**: `X-Admin-Key`. Transizione valida secondo le regole di `CourseLifecycleManager`. |
| `GET /api/v1/academy/courses/{course_id}/sources` | **Path**: `course_id` *(str)* | Mostra tutte le fonti originali (`document_id`, `chunk_id`, `section`, `updated_at`) per ogni lezione del corso. | Corso accessibile al tenant e al ruolo chiamante. |
| `GET /api/v1/academy/courses/{course_id}/revisions` | **Path**: `course_id` *(str)* | Restituisce lo storico delle revisioni (`CourseRevision`) e degli eventi di workflow (`CourseApprovalEvent`). | Corso accessibile al tenant e al ruolo chiamante. |

---

## 5. Endpoint HTTP — Adaptive Learning & Custom Quiz (`customquiz` — Milestone 3)

Definiti in [`src/operator_copilot/api/customquiz_router.py`](../src/operator_copilot/api/customquiz_router.py).  
**Requisito comune di sicurezza**: su tutti questi endpoint è attivo `assert_user_access` (`X-User-ID` obbligatorio non `"anonymous"` e coincidente con l'utente target, oppure `X-User-Role: admin` con `X-Admin-Key` valido) + isolamento `X-Tenant-ID`.

| Metodo & Path | Parametri (Path / Query / Body) | Cosa fa | Cosa richiede |
| :--- | :--- | :--- | :--- |
| `POST /api/v1/customquiz/user/{user_id}/analyze-gaps` | **Path**: `user_id` *(str)*<br>**Body (`AnalyzeGapsRequest`, opz.)**:<br>- `software` *(str \| None, opz.)*<br>- `module_name` *(str \| None, opz.)* | Analizza lo storico RAG (`QueryHistory` + `QueryFeedback`) e gli errori nei quiz (`CourseQuizAttempt`, `CustomQuizAttempt`) dell'utente, creando/aggiornando i `LearningGap` e il `UserKnowledgeProfile`. | `X-User-ID == user_id` (o admin autenticato). |
| `POST /api/v1/customquiz/generate` | **Body (`CustomQuizGenerateRequest`)**:<br>- `user_id` *(str, obbl.)*<br>- `num_questions` *(int, 1..20, default `4`)*<br>- `software` *(str \| None, opz.)*<br>- `module_name` *(str \| None, opz.)*<br>- `focus_topic` *(str \| None, opz.)*<br>- `force_new` *(bool, default `False`)*<br>- `run_async` *(bool, default `False`)* | Genera (o riusa se idempotente entro `custom_quiz_reuse_hours`) un **Custom Quiz personalizzato** con **esattamente 4 opzioni (`A`, `B`, `C`, `D`)** per domanda, mirato alle lacune e alle domande passate dell'utente, senza domande identiche già poste. | `X-User-ID == payload.user_id` (o admin autenticato). Richiede almeno un'evidenza/topic nello storico/lacune/profilo o `focus_topic` valorizzato (`404` se l'utente ha storico completamente vuoto e nessun `focus_topic`). |
| `GET /api/v1/customquiz/user/{user_id}` | **Path**: `user_id` *(str)* | Elenca tutti i Custom Quiz generati per `user_id` nel tenant corrente (ordinati dal più recente). | `X-User-ID == user_id` (o admin autenticato). |
| `GET /api/v1/customquiz/{quiz_id}` | **Path**: `quiz_id` *(str)* | Recupera il dettaglio di un Custom Quiz (`CustomQuizResponse`) per la compilazione da parte dell'utente. **Non espone** `correct_option_id` né `correct_answer`. | Quiz esistente nel tenant (`404` se assente) e `X-User-ID == quiz.user_id` (o admin autenticato). |
| `POST /api/v1/customquiz/{quiz_id}/submit` | **Path**: `quiz_id` *(str)*<br>**Body (`CustomQuizSubmitRequest`)**:<br>- `user_id` *(str, obbl.)*<br>- `answers` *(dict[str, str], obbl.)*: `{question_id: "A"|"B"|"C"|"D" o testo opzione}`<br>- `duration_seconds` *(int, 0..86400, default `60`)* | Valuta le risposte, salva `CustomQuizAttempt`, aggiorna lo stato delle lacune (`OPEN`/`IN_PROGRESS`/`IMPROVING`/`RESOLVED`), ricalcola `UserKnowledgeProfile` e restituisce feedback per domanda, fonti e lezioni Academy consigliate. | `X-User-ID == payload.user_id` (o admin autenticato). Quiz esistente e in stato `READY` o `COMPLETED` (`404` altrimenti). |
| `GET /api/v1/customquiz/{quiz_id}/results` | **Path**: `quiz_id` *(str)*<br>**Query**: `user_id` *(str \| None, opz., default `X-User-ID`)* | Restituisce l'esito completo dell'ultimo tentativo completato su `quiz_id` (punteggio, spiegazioni, fonti e lezioni suggerite). | `X-User-ID == target_uid` (o admin autenticato) e almeno un `CustomQuizAttempt` completato (`404` altrimenti). |
| `GET /api/v1/customquiz/user/{user_id}/learning-profile` | **Path**: `user_id` *(str)* | Aggiorna e restituisce il profilo conoscitivo individuale dell'utente (`softwares_used`, `modules_used`, `known_topics`, `difficulty_topics`, `topic_profiles`, `open_gaps`). | `X-User-ID == user_id` (o admin autenticato). |
| `GET /api/v1/customquiz/user/{user_id}/learning-metrics` | **Path**: `user_id` *(str)*<br>**Query**:<br>- `topic` *(str \| None, opz.)*<br>- `software` *(str \| None, opz.)*<br>- `module_name` *(str \| None, opz.)*<br>- `date_from` *(datetime ISO, opz.)*<br>- `date_to` *(datetime ISO, opz.)* | Calcola le 6 metriche longitudinali (`quiz_accuracy`, `learning_improvement`, `knowledge_gap_resolution_rate`, `retention_rate`, `repeated_error_rate`, `learning_progress`) e l'evoluzione per argomento. | `X-User-ID == user_id` (o admin autenticato). |
| `DELETE /api/v1/customquiz/user/{user_id}/data` | **Path**: `user_id` *(str)* | Cancellazione GDPR di tutti i dati individuali di apprendimento e storico RAG dell'utente (`CustomQuizAttempt`, `CustomQuiz`, `LearningGap`, `UserKnowledgeProfile`, `CourseQuizAttempt`, `QueryHistory`). | `X-User-ID == user_id` (o admin autenticato). |

---

## 6. Endpoint HTTP — Owner Learning Dashboard (`owner` — Milestone 4)

Definiti in [`src/operator_copilot/api/owner_router.py`](../src/operator_copilot/api/owner_router.py).  
**Requisito comune di sicurezza**: tutti gli endpoint REST `/api/v1/owner/*` richiedono `X-User-Role: owner`, `X-Owner-Key` valido e `X-User-ID` non `"anonymous"` (isolati per `X-Tenant-ID` e opzionalmente `X-Owner-Scope`).

| Metodo & Path | Parametri (Path / Query / Body) | Cosa fa | Cosa richiede |
| :--- | :--- | :--- | :--- |
| `GET /owner` | Nessuno (pagina HTML). | Serve la **Owner Learning Dashboard UI** con le viste *Overview*, *Utenti*, *Topic da ripassare*, *Learning Analytics* e *Custom Quiz Performance*. | Le chiamate ai dati eseguite dall'interfaccia richiedono credenziali Owner (`X-Owner-Key`, `X-Tenant-ID`, `X-User-ID`). |
| `GET /api/v1/owner/overview` | **Query**: `date_from`, `date_to` *(datetime ISO, opz.)*, `software`, `module_name`, `amministrazione` *(str, opz.)*, `refresh` *(bool, default `False`)* | Restituisce i KPI aggregati reali (utenti totali, utenti attivi nel periodo, completamento corsi, punteggio medio quiz, learning improvement medio, gap resolution rate, lacune aperte, utenti critici, variazione rispetto al periodo precedente e serie temporale). | Credenziali Owner valide; utilizza `OwnerMetricsCache` (`refresh=true` bypassa cache). |
| `GET /api/v1/owner/users` | **Query**: `search`, `amministrazione`, `software`, `learning_status`, `sort_by`, `sort_dir` *(`asc` \| `desc`)*, `page` *(int >= 1)*, `page_size` *(int 1..200)* | Elenca gli utenti visibili nell'ambito dell'Owner con metriche aggregate per utente, ordinamento e paginazione (inclusi utenti a storico zero). | Credenziali Owner valide. |
| `POST /api/v1/owner/users` | **Body (`OrganizationUserUpsertRequest`)**: `user_id`, `display_name`, `amministrazione`, `role` *(default `"operatore"`)* | Registra o aggiorna anagrafica ed ente dell'utente in `organization_users` invalidando la cache dashboard del tenant. | Credenziali Owner valide; se `X-Owner-Scope` è attivo, l'ente deve rientrare nello scope (`403` altrimenti). |
| `GET /api/v1/owner/users/{user_id}` | **Path**: `user_id` *(str)* | Restituisce il profilo completo dell'utente: performance (`learning_performance`), corsi completati/da completare, lacune dettagliate e timeline unificata. | Credenziali Owner valide e `user_id` nell'ambito autorizzato (`404` altrimenti). |
| `GET /api/v1/owner/users/{user_id}/gaps` | **Path**: `user_id` *(str)* | Restituisce il dettaglio delle sole lacune formative (`LearningGap`) dell'utente. | Credenziali Owner valide e `user_id` autorizzato (`404` altrimenti). |
| `GET /api/v1/owner/topics-to-review` | **Query**: `software`, `module_name`, `amministrazione`, `criticality` *(`CRITICAL` \| `HIGH` \| `MEDIUM` \| `LOW`)*, `date_from`, `date_to` | Aggrega gli argomenti con tasso d'errore o lacune aperte e ne classifica la criticità con soglie configurabili. | Credenziali Owner valide. |
| `GET /api/v1/owner/topics-to-review/{topic}/users` | **Path**: `topic` *(str)*<br>**Query**: `amministrazione` *(str \| None, opz.)* | Drill-down con riepilogo del topic e lista degli operatori impattati. | Credenziali Owner valide (`404` se topic non presente nell'ambito). |
| `GET /api/v1/owner/customquiz-analytics` | **Query**: `date_from`, `date_to`, `software`, `module_name`, `amministrazione` | Analizza l'efficacia longitudinale dei Custom Quiz: generati, completati, accuratezza media, delta tra verifiche, lacune risolte (`>= 2` verifiche positive distanziate), persistenti, errori ripetuti e retention rate. | Credenziali Owner valide. |
| `GET /api/v1/owner/insights` | **Query**: `software`, `module_name`, `amministrazione`, `use_llm_synthesis` *(bool, default `False`)* | Genera suggerimenti operativi ancorati alle metriche reali SQLite (e opzionalmente rielaborati via **Qwen** se runtime attivo e `use_llm_synthesis=true`). | Credenziali Owner valide. |
| `GET /api/v1/owner/audit-logs` | **Query**: `limit` *(int 1..500, default `100`)* | Restituisce lo storico delle consultazioni e operazioni effettuate dagli Owner (`owner_audit_logs`). | Credenziali Owner valide. |

---

## 7. Entry Point Python Programmatici

Utilizzabili direttamente in codice Python o test senza passare da HTTP:

1. **`RAGEngine`** ([`src/operator_copilot/retrieval/rag_engine.py`](../src/operator_copilot/retrieval/rag_engine.py#L28-L169)):
   - Costruttore: `RAGEngine(settings=None, db_manager=None, llm=None)`
   - Metodo principale: `answer_query(request: RAGQueryRequest) -> RAGResponse`
2. **`CustomQuizEngine`** ([`src/operator_copilot/customquiz/__init__.py`](../src/operator_copilot/customquiz/__init__.py#L20-L143)):
   - Costruttore: `CustomQuizEngine(rag_engine: RAGEngine)` (riusa configurazione, DB, `HybridRetriever` e `AnswerGenerator` di `RAGEngine`)
   - Metodi esposti:
     - `analyze_gaps(user_id, tenant_id="default", software=None, module_name=None)`
     - `generate(user_id, tenant_id="default", num_questions=4, software=None, module_name=None, focus_topic=None, force_new=False, run_async=False)`
     - `get_quiz(quiz_id, tenant_id="default", user_id=None)`
     - `list_user_quizzes(user_id, tenant_id="default")`
     - `submit(quiz_id, user_id, answers, tenant_id="default", duration_seconds=60, completed_at=None)`
     - `submit_course_quiz(course_id, quiz_id, user_id, answers, tenant_id="default")`
     - `get_results(quiz_id, user_id, tenant_id="default")`
     - `get_learning_profile(user_id, tenant_id="default")`
     - `get_learning_metrics(user_id, tenant_id="default", topic=None, software=None, module_name=None, date_from=None, date_to=None)`
     - `delete_user_data(user_id, tenant_id="default")`
3. **`OwnerDashboardService`** ([`src/operator_copilot/owner_dashboard/service.py`](../src/operator_copilot/owner_dashboard/service.py#L76)):
   - Costruttore: `OwnerDashboardService(settings=None, db_manager=None, generator=None, cache=None)`
   - Metodi esposti: `get_overview(...)`, `list_users(...)`, `upsert_organization_user(...)`, `get_user_detail(...)`, `list_topics_to_review(...)`, `get_topic_users_drilldown(...)`, `get_custom_quiz_analytics(...)`, `get_insights(...)`, `record_audit(...)`, `list_audit_logs(...)`.
4. **Orchestratori Knowledge-to-Course**:
   - [`KnowledgeJobRunner`](../src/operator_copilot/knowledge_intelligence/job_runner.py): `create_and_start_job(...)`, `resume_job(...)`
   - [`AICourseGenerator`](../src/operator_copilot/course_generator/generator.py): `generate_from_opportunity(...)`, `generate_from_document(...)`, `regenerate_lesson(...)`, `generate_quiz(...)`
   - [`CourseLifecycleManager`](../src/operator_copilot/course_generator/lifecycle.py): `transition(...)`, `detect_impacted_courses(...)`, `record_revision(...)`
