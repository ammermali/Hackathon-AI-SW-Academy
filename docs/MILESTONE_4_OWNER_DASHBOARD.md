# Milestone 4 – Owner Learning Dashboard & Analytics

Questo documento descrive l'architettura, la sicurezza, il modello dati e le API della **Milestone 4 – Owner Learning Dashboard**, integrata nell'architettura Python + FastAPI + SQLite + Adaptive Learning esistente (`AI Software Academy`).

---

## 1. Obiettivo e Principi Architetturali

La **Owner Dashboard – Learning Analytics** offre un'area riservata esclusivamente al ruolo **`owner`** per:
- Monitorare lo stato generale dell'apprendimento nell'ente/organizzazione di competenza (`Overview`).
- Consultare le metriche per singolo operatore e il relativo profilo conoscitivo completo (`Utenti` + `Detail Drawer`).
- Individuare gli argomenti con criticità formativa (`Topic da ripassare`) e gli utenti impattati (`Drill-down`).
- Analizzare l'andamento storico e i suggerimenti formativi azionabili (`Learning Analytics`, con eventuale sintesi **Qwen** verificabile).
- Misurare l'efficacia longitudinale dei **Custom Quiz** rispetto alle lacune formative (`Custom Quiz Performance`).

### Vincoli rispettati
- **Nessuna duplicazione**: riutilizza `DatabaseManager` (SQLite), `RAGEngine`, `AnswerGenerator` (Qwen/extractive), `CustomQuiz`, `CustomQuizAttempt`, `CourseQuizAttempt`, `LearningGap`, `UserKnowledgeProfile`, `Course`.
- **Nessun dato simulato**: ogni KPI, media, serie temporale, tasso di risoluzione e suggerimento deriva esclusivamente da query aggregate reali sul database SQLite.
- **Isolamento Multi-Tenant e Ambito**: ogni richiesta è strettamente isolata per `X-Tenant-ID` e per l'eventuale ambito amministrativo `X-Owner-Scope`.

---

## 2. Sicurezza, Autenticazione e Audit Trail

Definiti in [`src/operator_copilot/api/dependencies.py`](../src/operator_copilot/api/dependencies.py) e [`src/operator_copilot/db/models.py`](../src/operator_copilot/db/models.py):

- **Dipendenza dedicata `build_owner_context_dependency`**:
  - Richiede **`X-User-Role: owner`** (case-insensitive). Operatori (`operatore`), `anonymous` e anche utenti `admin` privi delle credenziali Owner ricevono **`403 Forbidden`**.
  - Richiede **`X-Owner-Key`** confrontato in tempo costante (`secrets.compare_digest`) con `Settings.owner_api_key` (variabile env `OWNER_API_KEY`).
  - Richiede **`X-User-ID`** valido e non `"anonymous"`.
  - Supporta **`X-Tenant-ID`** (isolamento rigoroso per tenant) e **`X-Owner-Scope`** (lista CSV opzionale di `amministrazione` autorizzate, es. `Comune Alfa,Comune Beta`).
- **Audit Logging (`OwnerAuditLog`, tabella `owner_audit_logs`)**:
  - Ogni consultazione su dashboard, profili utente, topic drill-down, analytics o insights viene registrata con `tenant_id`, `owner_id`, `owner_role`, `action`, `resource`, `target_user_id`, `filters` e `created_at`.

---

## 3. Estensioni Data Model e Configurazione

### Nuove tabelle SQLite ([`src/operator_copilot/db/models.py`](../src/operator_copilot/db/models.py))
1. **`organization_users` (`OrganizationUser`)**: mappa anagrafica `(tenant_id, user_id)` -> `display_name`, `amministrazione`, `role`, garantendo la visibilità in dashboard anche per utenti con storico formativo ancora a zero (`0` quiz / `0` gap).
2. **`owner_audit_logs` (`OwnerAuditLog`)**: tracciamento persistente delle consultazioni e operazioni effettuate dagli Owner.

### Configurazione ([`src/operator_copilot/config/settings.py`](../src/operator_copilot/config/settings.py))
- `OWNER_API_KEY` (`owner_api_key`): chiave segreta per l'autenticazione Owner.
- `OWNER_DASHBOARD_CACHE_TTL_SECONDS` (`owner_dashboard_cache_ttl_seconds`, default `30`): TTL della cache in-memory per tenant/filtri su `/overview`.
- `TOPIC_CRITICAL_ERROR_RATE` (`45.0`), `TOPIC_CRITICAL_MIN_GAPS` (`3`), `TOPIC_HIGH_ERROR_RATE` (`25.0`), `TOPIC_MEDIUM_ERROR_RATE` (`10.0`): soglie configurabili per classificare la criticità dei topic in `CRITICAL` / `HIGH` / `MEDIUM` / `LOW`.

---

## 4. Componenti Implementati

| Modulo | Responsabilità |
| :--- | :--- |
| [`src/operator_copilot/schemas/owner.py`](../src/operator_copilot/schemas/owner.py) | Schemi Pydantic v2 per Overview, lista paginata Utenti, Dettaglio Utente, Topic da ripassare + Drill-down, Custom Quiz Analytics, Insights (inclusi schemi strutturati LLM `OwnerInsightsLLMOutput`) e Audit Log. |
| [`src/operator_copilot/owner_dashboard/cache.py`](../src/operator_copilot/owner_dashboard/cache.py) | `OwnerMetricsCache` thread-safe con TTL configurabile e invalidazione immediata per tenant (`invalidate_tenant`). |
| [`src/operator_copilot/owner_dashboard/service.py`](../src/operator_copilot/owner_dashboard/service.py) | `OwnerDashboardService`: aggregazioni SQLite reali, filtri temporali / software / modulo / amministrazione, confronto con il periodo precedente (`improvement_vs_previous_period`), gestione sicura utenti a storico zero, insights deterministici + sintesi **Qwen** verificabile (`OWNER_INSIGHTS_PROMPT`). |
| [`src/operator_copilot/api/owner_router.py`](../src/operator_copilot/api/owner_router.py) | Router FastAPI con `GET /owner` (UI) e API REST `/api/v1/owner/*`. |
| [`src/operator_copilot/owner_dashboard/ui.py`](../src/operator_copilot/owner_dashboard/ui.py) | Interfaccia web responsive integrata su `/owner` con le 5 viste (*Overview*, *Utenti* + pannello dettaglio, *Topic da ripassare* + drill-down utenti, *Learning Analytics* + Audit Trail, *Custom Quiz Performance*) e grafici SVG nativi alimentati dalle API reali. |

---

## 5. Endpoint Principali

- **UI Web**: `GET /owner` (richiede autenticazione inserendo nell'header bar gli header `X-Owner-Key`, `X-User-ID`, `X-Tenant-ID`, eventuale `X-Owner-Scope`).
- **API REST (`/api/v1/owner/*`)**:
  - `GET /api/v1/owner/overview` — KPI generali, filtri disponibili, trend temporale e variazione rispetto al periodo precedente.
  - `GET /api/v1/owner/users` / `POST /api/v1/owner/users` — Elenco utenti paginato, filtrabile/ordinabile, e registrazione anagrafica (`display_name`, `amministrazione`).
  - `GET /api/v1/owner/users/{user_id}` / `GET /api/v1/owner/users/{user_id}/gaps` — Profilo di apprendimento individuale, corsi completati/da completare, lacune dettagliate e timeline storica unificata.
  - `GET /api/v1/owner/topics-to-review` / `GET /api/v1/owner/topics-to-review/{topic}/users` — Classificazione topic critici e drill-down sugli operatori coinvolti.
  - `GET /api/v1/owner/customquiz-analytics` — Efficacia dei Custom Quiz, miglioramento medio tra verifiche e risoluzione reale dopo verifiche distanziate.
  - `GET /api/v1/owner/insights` — Suggerimenti operativi ancorati alle metriche reali (con `use_llm_synthesis=true` opzionale tramite **Qwen**).
  - `GET /api/v1/owner/audit-logs` — Consultazione dello storico audit per tenant.

---

## 6. Note e Limiti Noti

- La generazione LLM opzionale degli insight (`use_llm_synthesis=true`) utilizza `AnswerGenerator` (**Qwen** via Ollama): in assenza di un'istanza Ollama attiva (o con `LLM_PROVIDER=extractive`), il sistema restituisce automaticamente gli insight deterministici basati sulle metriche SQLite reali.
- Il controllo accessi si basa sugli header contestuali verificati (`X-User-Role: owner`, `X-Owner-Key`, `X-Tenant-ID`, `X-Owner-Scope`); in produzione va affiancato a un gateway OAuth2/OIDC che popoli/validi tali claim a monte.
