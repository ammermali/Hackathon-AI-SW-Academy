# AI Software Academy — Complete Frontend Experience (Milestone UI 2)

Interfaccia web unificata React + TypeScript + Vite per **AI Software Academy**, integrata direttamente con il backend Python FastAPI esistente (motore RAG con Qwen, AI Knowledge-to-Course Engine, Adaptive Learning & Custom Quiz Engine e Owner Learning Analytics).

## Architettura e Route della Piattaforma

```text
frontend/
├── src/
│   ├── config/env.ts                       # Configurazione runtime VITE_*
│   ├── context/AuthContext.tsx             # Sessione utente centralizzata + Demo Switcher + stato backend
│   ├── types/
│   │   ├── rag.ts                          # Tipi Conversational RAG
│   │   └── platform.ts                     # Tipi Academy, LessonCompletion, CustomQuiz, Owner, DemoAuth
│   ├── services/
│   │   ├── api.ts                          # Client HTTP base + headers multi-tenant/demo + RAG API
│   │   ├── demoApi.ts                      # /api/v1/demo/*
│   │   ├── academyApi.ts                   # /api/v1/academy/*
│   │   ├── customQuizApi.ts                # /api/v1/custom-quiz/*
│   │   └── ownerApi.ts                     # /api/v1/owner/*
│   ├── utils/courseHelpers.ts              # Helper condivisi per corsi, stati e date it-IT
│   ├── hooks/useConversation.ts            # Hook conversazionale sincronizzato con AuthContext
│   ├── components/
│   │   ├── common/PlatformPrimitives.tsx   # StatCard, ProgressBar, StatusBadge, ErrorBanner, ScoreBarChart
│   │   ├── layout/
│   │   │   ├── AppLayout.tsx               # Shell applicativa unificata + guard redirect su cambio ruolo
│   │   │   ├── PlatformSidebar.tsx         # Navigazione piattaforma + sezione Owner condizionale
│   │   │   ├── TopHeader.tsx               # Profilo attivo, stato RAG e Demo User Switcher
│   │   │   └── DemoUserSwitcher.tsx        # Ricerca utenti reali + switch firmato lato backend
│   │   └── ...                             # Componenti Conversational UI riusati da Milestone UI 1
│   ├── pages/
│   │   ├── HomePage.tsx                    # /
│   │   ├── ChatPage.tsx                    # /assistant (riuso integrale Conversational UI)
│   │   ├── LearningAreaPage.tsx            # /learning
│   │   ├── CourseDetailPage.tsx            # /learning/:courseId (viewer lezioni, completamento, quiz)
│   │   ├── MyLearningPage.tsx              # /my-learning (corsi, quiz tradizionali, runner Custom Quiz 4 opzioni)
│   │   ├── MyProgressPage.tsx              # /my-progress (metriche, chart punteggi, 3 bucket topic)
│   │   └── owner/
│   │       ├── OwnerRoute.tsx              # Guard basato sul ruolo attivo
│   │       ├── OwnerDashboardPage.tsx      # /owner (KPI, timeline, CustomQuiz analytics, Qwen Insights)
│   │       ├── OwnerUsersPage.tsx          # /owner/users (tabella filtri/paginazione + detail drawer)
│   │       └── OwnerTopicsPage.tsx         # /owner/topics (criticità + drilldown operatori coinvolti)
│   └── test/App.test.tsx                   # Suite Vitest + Testing Library
```

## Sicurezza e Demo Mode

- **Nessun segreto nel frontend:** il frontend non contiene mai API key né segreti di firma (`DEMO_SESSION_SECRET`).
- **Switch controllato dal backend:** in ambiente non-produzione con `DEMO_MODE_ENABLED=true`, `/api/v1/demo/switch-user` emette un token HMAC-SHA256 temporaneo (`X-Demo-Token`) verificato ad ogni chiamata dal backend FastAPI (`build_caller_context_dependency` / `build_owner_context_dependency`).
- **Disabilitazione in produzione:** se `APP_ENV=production` o `DEMO_MODE_ENABLED=false`, gli endpoint `/api/v1/demo/*` restituiscono HTTP `403`/`404` e il selettore Demo scompare automaticamente dall'header.

## Comandi di Avvio, Build e Test

### 1. Seeding utenti demo di sviluppo (opzionale, idempotente)

```powershell
# Dalla root del repository
.\.venv\Scripts\python.exe scripts/seed_demo_users.py
```

### 2. Avvio Backend FastAPI (dalla root del repository)

```powershell
.\.venv\Scripts\python.exe -m uvicorn operator_copilot.api.main:app --host 127.0.0.1 --port 8000
```

### 3. Configurazione e Avvio Frontend React (dalla cartella `frontend/`)

```powershell
cd frontend
copy .env.example .env
npm install
npm run dev
```

L'applicazione sarà disponibile su `http://localhost:5173`.

### 4. Verifica Build e Test

```powershell
# Test Frontend (Vitest + TypeScript + Vite build)
cd frontend
npm run build
npm test

# Test Backend Python (dalla root del repository)
.\.venv\Scripts\python.exe -m pytest -v
```
