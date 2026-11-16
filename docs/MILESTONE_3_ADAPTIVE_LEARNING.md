# Operator Copilot — Milestone 3: Adaptive Learning & Custom Quiz Engine

**Estensione di:** [ARCHITECTURE.md](ARCHITECTURE.md) (Milestone 1 — RAG Engine) e [MILESTONE_2_KNOWLEDGE_TO_COURSE.md](MILESTONE_2_KNOWLEDGE_TO_COURSE.md) (Milestone 2 — AI Knowledge-to-Course Engine)

La **Milestone 3** integra nella piattaforma esistente il motore **Adaptive Learning & Custom Quiz Engine**, accessibile tramite l'entry point logico e HTTP dedicato **`customquiz`** (`CustomQuizEngine` e `/api/v1/customquiz/*`), riutilizzando integralmente `RAGEngine`, `HybridRetriever`, `AnswerGenerator` (Qwen), `QueryHistory`/`QueryFeedback`, i corsi/lezioni Academy e SQLite.

---

## 1. Integrazione nell'Architettura Esistente (Zero Duplicazione)

```mermaid
flowchart TD
    subgraph API["FastAPI App Unica (api/main.py)"]
        RagEp["/api/v1/rag/* (Milestone 1)"]
        AcadEp["/api/v1/academy/* (Milestone 2 + Course Quiz Submit)"]
        CqEp["/api/v1/customquiz/* (Milestone 3 - customquiz_router.py)"]
    end

    subgraph CORE["Componenti Riusati"]
        RAGEng["RAGEngine & HybridRetriever"]
        LLM["AnswerGenerator (Qwen + Anti-Injection + PII Redact)"]
        DB[("SQLite (SQLAlchemy 2.0)")]
    end

    subgraph AL["Adaptive Learning Engine (src/operator_copilot/adaptive_learning/)"]
        Entry["CustomQuizEngine (customquiz/__init__.py)"]
        Svc["AdaptiveLearningService"]
        Prof["UserKnowledgeProfiler"]
        Gap["LearningGapDetector"]
        Pers["PersonalizationEngine"]
        QGen["CustomQuizGenerator\n(4 opzioni A-D + idempotenza + ThreadPoolExecutor)"]
        Met["LearningMetricsService"]
    end

    CqEp --> Entry
    AcadEp -->|submit_course_quiz| Entry
    Entry --> Svc
    Svc --> Prof & Gap & Pers & QGen & Met
    QGen -->|Passaggi ufficiali| RAGEng
    QGen -->|Structured JSON (CUSTOM_QUIZ_PROMPT) / Fallback| LLM
    Prof & Gap & Pers & QGen & Met --> DB
```

---

## 2. Entry Point Dedicato: `customquiz`

- **Entry point Python:** [`CustomQuizEngine`](../src/operator_copilot/customquiz/__init__.py) — riceve un'istanza di `RAGEngine` già inizializzata e coordina:
  - `analyze_gaps(...)`
  - `generate(...)`
  - `get_quiz(...)` / `list_user_quizzes(...)`
  - `submit(...)` / `submit_course_quiz(...)`
  - `get_results(...)`
  - `get_learning_profile(...)`
  - `get_learning_metrics(...)`
  - `delete_user_data(...)`
- **Entry point HTTP REST (`/api/v1/customquiz/*`)** definito in [`create_customquiz_router`](../src/operator_copilot/api/customquiz_router.py) e montato in [`create_app`](../src/operator_copilot/api/main.py):
  - `POST /api/v1/customquiz/user/{user_id}/analyze-gaps`
  - `POST /api/v1/customquiz/generate`
  - `GET /api/v1/customquiz/{quiz_id}` *(non espone `correct_option_id` / `correct_answer` prima della consegna)*
  - `GET /api/v1/customquiz/user/{user_id}`
  - `POST /api/v1/customquiz/{quiz_id}/submit`
  - `GET /api/v1/customquiz/{quiz_id}/results`
  - `GET /api/v1/customquiz/user/{user_id}/learning-profile`
  - `GET /api/v1/customquiz/user/{user_id}/learning-metrics` *(filtri `topic`, `software`, `module_name`, `date_from`, `date_to`)*
  - `DELETE /api/v1/customquiz/user/{user_id}/data` *(cancellazione GDPR dati di apprendimento + storico RAG utente)*
- **Estensione Quiz tradizionali Academy** in [`academy_router.py`](../src/operator_copilot/api/academy_router.py):
  - `POST /api/v1/academy/courses/{course_id}/quizzes/{quiz_id}/submit` registra il tentativo in `course_quiz_attempts` e aggiorna automaticamente lacune e profilo utente.

---

## 3. Persistenza Database (SQLite / SQLAlchemy)

Modelli aggiunti in [`src/operator_copilot/db/models.py`](../src/operator_copilot/db/models.py):
- **`CourseQuizAttempt` (`course_quiz_attempts`)**: risposte, domande sbagliate, `wrong_topics`, punteggio e superamento dei quiz tradizionali dei corsi.
- **`UserKnowledgeProfile` (`user_knowledge_profiles`)**: profilo per `(tenant_id, user_id, topic)` con `software`, `module_name`, `estimated_level`, `learning_stage`, contatori RAG/quiz, `frequent_questions`, storico errori.
- **`LearningGap` (`learning_gaps`)**: lacune per `(tenant_id, user_id, topic)` con `evidences`, `evidence_sources`, `priority`, `confidence`, `status` (`OPEN`, `IN_PROGRESS`, `IMPROVING`, `RESOLVED`), `positive_verifications`, `repeated_error_count`, `asked_question_hashes`.
- **`CustomQuiz` (`custom_quizzes`)**: test personalizzati per utente con `status` (`GENERATING`, `READY`, `COMPLETED`, `FAILED`), `topics_verified`, `gap_ids`, `idempotency_key`, `model_used`, `prompt_version`.
- **`CustomQuizQuestion` (`custom_quiz_questions`)**: domande con **esattamente 4 opzioni (`A`, `B`, `C`, `D`)**, `correct_option_id`, `correct_answer`, `question_hash`, `explanation`, `difficulty`, `gap_id`, `sources`.
- **`CustomQuizAttempt` (`custom_quiz_attempts`)**: esito completo (`correct_count`, `total_questions`, `percentage`, `duration_seconds`, `outcome`), `feedback` JSON (feedback per domanda con citazioni, lezioni Academy consigliate, transizioni delle lacune).

---

## 4. Logica di Rilevazione Lacune, Personalizzazione e Metriche

- **Distinzione uso normale vs difficoltà ([`profiler.py`](../src/operator_copilot/adaptive_learning/profiler.py), [`gap_detector.py`](../src/operator_copilot/adaptive_learning/gap_detector.py))**:
  - Query RAG isolate con intent informativo normale non aprono lacune e non penalizzano il profilo.
  - Segnali di difficoltà: `intent == "troubleshooting"`, marker di chiarimento (`"non riesco"`, `"aiuto"`, `"errore"`, ecc.), `needs_escalation`, `QueryFeedback.rating <= 2`, ricerche ripetute sullo stesso topic (`>= 3`), oppure errori in `CourseQuizAttempt` / `CustomQuizAttempt`.
- **Risoluzione progressiva e anti-falsi positivi**:
  - Un singolo quiz superato non chiude la lacuna (`OPEN` -> `IMPROVING`).
  - Il passaggio a **`RESOLVED`** richiede `positive_verifications >= 2`, `accuracy >= 70%`, domande varianti (`question_hash` non già chiesto) e intervallo minimo configurabile (`learning_retention_min_hours`, default `24.0` ore).
- **Metriche longitudinali ([`metrics.py`](../src/operator_copilot/adaptive_learning/metrics.py))**:
  - `quiz_accuracy`, `learning_improvement`, `knowledge_gap_resolution_rate`, `retention_rate`, `repeated_error_rate`, `learning_progress`, `gaps_summary`, `learning_stages_summary`, `per_topic_evolution`.

---

## 5. Sicurezza, Privacy e Configurazione

- Isolamento stretto per utente e tenant tramite [`build_caller_context_dependency`](../src/operator_copilot/api/dependencies.py) e [`assert_user_access`](../src/operator_copilot/api/dependencies.py) (anti-spoofing su `X-User-Role: admin` che richiede `X-Admin-Key` valida).
- Prompt dedicato `CUSTOM_QUIZ_PROMPT` in [`prompts.py`](../src/operator_copilot/course_generator/prompts.py) con isolamento `<retrieved_context>...</retrieved_context>` contro indirect prompt injection.
- Variabili di configurazione in [`settings.py`](../src/operator_copilot/config/settings.py) e [`.env.example`](../.env.example): `CUSTOM_QUIZ_PROMPT_VERSION`, `CUSTOM_QUIZ_DEFAULT_QUESTIONS`, `LEARNING_RETENTION_MIN_HOURS`, `CUSTOM_QUIZ_REUSE_HOURS`.
