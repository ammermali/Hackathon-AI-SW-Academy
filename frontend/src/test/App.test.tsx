import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AppRoutes } from "../App";
import { AuthProvider } from "../context/AuthContext";

function mockJsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function renderAt(route: string) {
  return render(
    <MemoryRouter initialEntries={[route]}>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </MemoryRouter>
  );
}

describe("AI Software Academy — Milestone UI 2 Platform & RAG", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
    vi.restoreAllMocks();
  });

  it("renders welcome state on /assistant, handles Shift+Enter newline vs Enter submit, renders Markdown and Fonti utilizzate", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith("/health")) {
        return mockJsonResponse({ status: "ok", version: "0.1.0", corpus_version: "v1" });
      }
      if (url.includes("/api/v1/rag/history/") && (!init?.method || init.method === "GET")) {
        return mockJsonResponse({ user_id: "operatore_01", total_returned: 0, items: [], topics_summary: {} });
      }
      if (url.endsWith("/api/v1/rag/query")) {
        const payload = JSON.parse(String(init?.body));
        return mockJsonResponse({
          query: payload.query,
          answer:
            "### Procedura IUV\n\n1. Apri **Ragioneria**.\n2. Compila `IUV`.\n\n| Campo | Obbligatorio |\n| --- | --- |\n| Codice IUV | Sì |",
          sources: [
            {
              document: "02 - Ragioneria/2025_c10_siope_pagopa.md",
              section: "Verifica codici IUV",
              page: 3,
              chunk_id: "internal_chunk_999",
              area: "Ragioneria",
              relevance_score: 0.91,
            },
          ],
          cached: false,
          processing_time_ms: 120,
          needs_escalation: false,
          history_id: 77,
        });
      }
      return mockJsonResponse({}, 404);
    });

    renderAt("/assistant");

    expect(await screen.findByText("Come posso aiutarti oggi?")).toBeInTheDocument();
    expect(await screen.findAllByText("RAG Connesso")).toHaveLength(1);

    const textarea = screen.getByPlaceholderText(/Fai una domanda sui manuali/i);

    await user.type(textarea, "Prima riga{Shift>}{Enter}{/Shift}Seconda riga");
    expect(textarea).toHaveValue("Prima riga\nSeconda riga");
    expect(fetchMock).not.toHaveBeenCalledWith(expect.stringContaining("/api/v1/rag/query"), expect.anything());

    await user.keyboard("{Enter}");

    expect(await screen.findByText("Procedura IUV")).toBeInTheDocument();
    expect(screen.getByText("Codice IUV")).toBeInTheDocument();

    const sourcesBtn = screen.getByRole("button", { name: /Fonti utilizzate \(1\)/i });
    expect(sourcesBtn).toHaveAttribute("aria-expanded", "false");
    await user.click(sourcesBtn);

    expect(screen.getByText("2025_c10_siope_pagopa.md")).toBeInTheDocument();
    expect(screen.getByText("Verifica codici IUV")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText(/91%/)).toBeInTheDocument();
    expect(screen.queryByText(/internal_chunk_999/)).not.toBeInTheDocument();

    const copyBtn = screen.getByRole("button", { name: /Copia risposta/i });
    await user.click(copyBtn);
    expect(await screen.findByText("Copiato")).toBeInTheDocument();
  });

  it("loads historical conversations grouped by session_id, preserves session_id on follow-up, and supports retry on error", async () => {
    const user = userEvent.setup();
    let queryAttempts = 0;
    const sentPayloads: Array<{ query: string; session_id: string }> = [];

    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith("/health")) {
        return mockJsonResponse({ status: "ok", version: "0.1.0", corpus_version: "v1" });
      }
      if (url.includes("/api/v1/rag/history/") && (!init?.method || init.method === "GET")) {
        return mockJsonResponse({
          user_id: "operatore_01",
          total_returned: 1,
          items: [
            {
              id: 10,
              user_id: "operatore_01",
              session_id: "conv_existing_42",
              query: "Come aprire ticket OTRS?",
              intent: "procedure",
              topic: "Assistenza",
              answer: "Invia una richiesta via OTRS con oggetto e firma.",
              sources: [],
              cache_hit: false,
              processing_time_ms: 85,
              needs_escalation: false,
              created_at: "2026-11-11T10:00:00Z",
            },
          ],
          topics_summary: { Assistenza: 1 },
        });
      }
      if (url.endsWith("/api/v1/rag/query")) {
        queryAttempts += 1;
        const body = JSON.parse(String(init?.body));
        sentPayloads.push(body);
        if (queryAttempts === 1) {
          return mockJsonResponse({ detail: "Errore temporaneo backend" }, 500);
        }
        return mockJsonResponse({
          query: body.query,
          answer: "Specifica l'ente nella firma.",
          sources: [],
          cached: false,
          processing_time_ms: 60,
          needs_escalation: false,
          history_id: 11,
        });
      }
      return mockJsonResponse({}, 404);
    });

    renderAt("/assistant");

    const convBtn = await screen.findByRole("button", { name: /Come aprire ticket OTRS\?/i });
    await user.click(convBtn);

    expect(await screen.findByText("Invia una richiesta via OTRS con oggetto e firma.")).toBeInTheDocument();

    const textarea = screen.getByPlaceholderText(/Fai una domanda sui manuali/i);
    await user.type(textarea, "Cosa inserire nella firma?{Enter}");

    expect(await screen.findByText("Impossibile completare la richiesta")).toBeInTheDocument();
    const retryBtn = screen.getByRole("button", { name: /Riprova/i });
    await user.click(retryBtn);

    expect(await screen.findByText("Specifica l'ente nella firma.")).toBeInTheDocument();
    await waitFor(() => expect(sentPayloads).toHaveLength(2));
    expect(sentPayloads[0].session_id).toBe("conv_existing_42");
    expect(sentPayloads[1].session_id).toBe("conv_existing_42");
  });

  it("handles HTTP 401/403 errors explicitly and supports full user history clear", async () => {
    const user = userEvent.setup();
    let deleteCalled = false;

    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith("/health")) {
        return mockJsonResponse({ status: "ok", version: "0.1.0", corpus_version: "v1" });
      }
      if (url.includes("/api/v1/rag/history/") && init?.method === "DELETE") {
        deleteCalled = true;
        return mockJsonResponse({ user_id: "operatore_01", deleted_records: 1 });
      }
      if (url.includes("/api/v1/rag/history/")) {
        return mockJsonResponse({
          user_id: "operatore_01",
          total_returned: 1,
          items: [
            {
              id: 1,
              user_id: "operatore_01",
              session_id: "conv_1",
              query: "Domanda salvata",
              intent: null,
              topic: null,
              answer: "Risposta salvata",
              sources: [],
              cache_hit: false,
              processing_time_ms: 40,
              needs_escalation: false,
              created_at: "2026-11-11T10:00:00Z",
            },
          ],
          topics_summary: {},
        });
      }
      if (url.endsWith("/api/v1/rag/query")) {
        return mockJsonResponse({ detail: "Token scaduto" }, 401);
      }
      return mockJsonResponse({}, 404);
    });

    renderAt("/assistant");
    expect(await screen.findByRole("button", { name: /Domanda salvata/i })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Cancella tutta la cronologia/i }));
    await user.click(screen.getByRole("button", { name: /^Conferma$/i }));

    await waitFor(() => expect(deleteCalled).toBe(true));
    expect(screen.getByText(/Nessuna conversazione salvata/i)).toBeInTheDocument();

    const textarea = screen.getByPlaceholderText(/Fai una domanda sui manuali/i);
    await user.type(textarea, "Test auth 401{Enter}");
    expect(await screen.findAllByText("Token scaduto")).not.toHaveLength(0);
    expect(screen.queryByRole("button", { name: /Riprova/i })).not.toBeInTheDocument();
  });

  it("renders legacy numbered source headers as separate headings without merging into step 4", async () => {
    const user = userEvent.setup();
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith("/health")) {
        return mockJsonResponse({ status: "ok", version: "0.1.0", corpus_version: "v1" });
      }
      if (url.includes("/api/v1/rag/history/")) {
        return mockJsonResponse({
          user_id: "operatore_01",
          total_returned: 1,
          items: [
            {
              id: 99,
              user_id: "operatore_01",
              session_id: "conv_legacy",
              query: "Procedura storica rimozione verbale",
              intent: "procedure",
              topic: "Codice della Strada",
              answer:
                "1. **Rimuovere un verbale da un ruolo** (Sezione: *Rimuovere un verbale da un ruolo*)\n1. Step uno\n2. Step due\n3. Step tre\n2. **Aggiungere manualmente un verbale** (Sezione: *Sezione B*)\nTesto B",
              sources: [],
              cache_hit: false,
              processing_time_ms: 40,
              needs_escalation: false,
              created_at: "2026-11-11T10:00:00Z",
            },
          ],
          topics_summary: {},
        });
      }
      return mockJsonResponse({}, 404);
    });

    renderAt("/assistant");
    await user.click(await screen.findByRole("button", { name: /Procedura storica rimozione verbale/i }));

    expect(await screen.findByRole("heading", { name: "1. Rimuovere un verbale da un ruolo" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "2. Aggiungere manualmente un verbale" })).toBeInTheDocument();
  });

  it("gates Owner Area by role and unlocks Owner Dashboard when Demo User Switcher switches to owner_demo", async () => {
    const user = userEvent.setup();

    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith("/health")) {
        return mockJsonResponse({ status: "ok", version: "0.1.0", corpus_version: "v1" });
      }
      if (url.endsWith("/api/v1/demo/status")) {
        return mockJsonResponse({ demo_mode_enabled: true, app_env: "development" });
      }
      if (url.includes("/api/v1/demo/users")) {
        return mockJsonResponse([
          {
            user_id: "operatore_01",
            display_name: "Maria Rossi",
            amministrazione: "Comune di Rimini",
            role: "operatore",
            softwares_used: ["Verbali CDS"],
            has_activity: true,
          },
          {
            user_id: "owner_demo",
            display_name: "Elena Conti (Owner)",
            amministrazione: "Ente Pilota PA",
            role: "owner",
            softwares_used: [],
            has_activity: false,
          },
        ]);
      }
      if (url.endsWith("/api/v1/demo/switch-user")) {
        const body = JSON.parse(String(init?.body));
        if (body.user_id === "owner_demo") {
          return mockJsonResponse({
            token: "signed_owner_token",
            user: {
              user_id: "owner_demo",
              display_name: "Elena Conti (Owner)",
              amministrazione: "Ente Pilota PA",
              role: "owner",
              softwares_used: [],
              has_activity: false,
            },
            tenant_id: "default",
            is_demo: true,
            expires_at: 9999999999,
          });
        }
        return mockJsonResponse({
          token: "signed_op_token",
          user: {
            user_id: "operatore_01",
            display_name: "Maria Rossi",
            amministrazione: "Comune di Rimini",
            role: "operatore",
            softwares_used: ["Verbali CDS"],
            has_activity: true,
          },
          tenant_id: "default",
          is_demo: true,
          expires_at: 9999999999,
        });
      }
      if (url.includes("/api/v1/academy/courses")) {
        return mockJsonResponse([]);
      }
      if (url.includes("/learning-overview")) {
        return mockJsonResponse({
          user_id: "operatore_01",
          tenant_id: "default",
          completed_lesson_ids: [],
          course_progress: [],
          course_quiz_attempts: [],
          custom_quiz_attempts: [],
        });
      }
      if (url.includes("/learning-metrics")) {
        return mockJsonResponse({
          user_id: "operatore_01",
          tenant_id: "default",
          filters: {},
          quiz_accuracy: 0,
          learning_improvement: null,
          knowledge_gap_resolution_rate: 0,
          retention_rate: null,
          repeated_error_rate: 0,
          learning_progress: 0,
          attempts_count: 0,
          gaps_summary: {},
          learning_stages_summary: {},
          per_topic_evolution: [],
        });
      }
      if (url.includes("/learning-profile")) {
        return mockJsonResponse({
          user_id: "operatore_01",
          tenant_id: "default",
          softwares_used: [],
          modules_used: [],
          known_topics: [],
          difficulty_topics: [],
          frequent_questions: [],
          topic_profiles: [],
          open_gaps: [],
        });
      }
      if (url.includes("/api/v1/owner/overview")) {
        return mockJsonResponse({
          tenant_id: "default",
          filters: {},
          total_users: 3,
          active_users_in_period: 2,
          course_completion_rate: 50,
          avg_quiz_score: 78.5,
          avg_learning_improvement: 10,
          knowledge_gap_resolution_rate: 60,
          open_gaps_count: 2,
          users_with_critical_gaps: 1,
          improvement_vs_previous_period: 5,
          available_softwares: ["Verbali CDS"],
          available_modules: ["Ruoli"],
          available_administrations: ["Comune di Rimini"],
          timeline: [],
        });
      }
      if (url.includes("/api/v1/owner/customquiz-analytics")) {
        return mockJsonResponse({
          tenant_id: "default",
          filters: {},
          total_generated: 2,
          total_completed: 2,
          avg_correct_percentage: 80,
          improvement_between_verifications: 12,
          gaps_resolved_via_followup: 1,
          persistent_gaps_count: 1,
          repeated_error_rate: 10,
          retention_rate: 90,
          timeline: [],
        });
      }
      if (url.includes("/api/v1/owner/insights")) {
        return mockJsonResponse({
          tenant_id: "default",
          filters: {},
          model_used: "deterministic",
          insights: [],
        });
      }
      return mockJsonResponse({}, 404);
    });

    renderAt("/");

    expect(await screen.findByText(/Benvenuto, Maria Rossi/i)).toBeInTheDocument();
    // Owner section is NOT visible to operatore
    expect(screen.queryByRole("link", { name: "Owner Dashboard" })).not.toBeInTheDocument();

    // Switch user via Demo User Switcher
    const switcherTrigger = await screen.findByRole("button", { name: /DEMO/i });
    await user.click(switcherTrigger);
    await user.click(await screen.findByRole("option", { name: /Elena Conti \(Owner\)/i }));

    // Owner nav appears cleanly
    const ownerLink = await screen.findByRole("link", { name: "Owner Dashboard" });
    await user.click(ownerLink);

    expect(await screen.findByRole("heading", { name: "Owner Learning Dashboard" })).toBeInTheDocument();
    expect(await screen.findByText("78.5%")).toBeInTheDocument();
  });

  it("supports course lesson completion and 4-option Custom Quiz runner submission", async () => {
    const user = userEvent.setup();
    let completedLessons: string[] = [];

    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith("/health")) {
        return mockJsonResponse({ status: "ok", version: "0.1.0", corpus_version: "v1" });
      }
      if (url.endsWith("/api/v1/academy/courses/crs_1")) {
        return mockJsonResponse({
          id: "crs_1",
          opportunity_id: null,
          tenant_id: "default",
          allowed_roles: ["operatore"],
          title: "Gestione Ruoli CDS",
          description: "Corso sui ruoli",
          course_type: "MICRO_COURSE",
          learning_objectives: ["Rimuovere un verbale"],
          prerequisites: [],
          target_audience: ["operatore"],
          difficulty: "base",
          summary: "Sintesi",
          lifecycle_status: "PUBLISHED",
          current_version: 1,
          corpus_version_at_generation: "v1",
          grounding_status: "VERIFIED",
          model_used: "qwen",
          created_at: "2026-11-11T10:00:00Z",
          updated_at: "2026-11-11T10:00:00Z",
          published_at: "2026-11-11T10:00:00Z",
          modules: [
            {
              id: "mod_1",
              order_index: 1,
              title: "Modulo Ruoli",
              description: "",
              learning_objective: "",
              lessons: [
                {
                  id: "les_1",
                  module_id: "mod_1",
                  order_index: 1,
                  title: "Rimozione Verbale",
                  objective: "Eseguire F7",
                  explanation: "Apri il ruolo e premi **F7**.",
                  procedures: ["Apri Gestione Ruoli", "Premi **F7** per confermare."],
                  practical_examples: [
                    {
                      label: "Esempio chiusura ruolo",
                      is_correct: true,
                      content: "Inserire sempre **numero ruolo** prima di confermare.",
                      section: "Ruoli",
                    },
                  ],
                  frequent_errors: [
                    {
                      error_or_antipattern: "Rimozione senza verifica verbale",
                      consequence_or_fix: "Controllare sempre lo stato prima di **F7**.",
                      section: "Ruoli",
                    },
                  ],
                  exercises: [
                    {
                      title: "Esercitazione guidata F7",
                      scenario: "Simula lo sblocco di un verbale.",
                      expected_steps: ["Seleziona il ruolo", "Premi **F7**"],
                    },
                  ],
                  summary: "F7 rimuove il verbale.",
                  is_grounded: true,
                  grounding_warnings: [],
                  sources: [],
                },
              ],
            },
          ],
          quizzes: [],
        });
      }
      if (url.endsWith("/api/v1/academy/courses/crs_1/lessons/les_1/complete") && init?.method === "POST") {
        completedLessons = ["les_1"];
        return mockJsonResponse({
          lesson_id: "les_1",
          course_id: "crs_1",
          user_id: "operatore_01",
          completed: true,
          completed_at: "2026-11-11T11:00:00Z",
        });
      }
      if (url.endsWith("/api/v1/academy/courses")) {
        return mockJsonResponse([]);
      }
      if (url.includes("/learning-overview")) {
        return mockJsonResponse({
          user_id: "operatore_01",
          tenant_id: "default",
          completed_lesson_ids: completedLessons,
          course_progress: [
            {
              course_id: "crs_1",
              completed_lessons: completedLessons.length,
              total_lessons: 1,
              completion_percentage: completedLessons.length * 100,
              status: completedLessons.length ? "COMPLETED" : "NOT_STARTED",
              best_quiz_percentage: null,
              last_activity_at: null,
            },
          ],
          course_quiz_attempts: [],
          custom_quiz_attempts: [],
        });
      }
      if (url.endsWith("/api/v1/customquiz/user/operatore_01")) {
        return mockJsonResponse([
          {
            id: "cq_1",
            tenant_id: "default",
            user_id: "operatore_01",
            software: "Verbali CDS",
            module_name: "Ruoli",
            status: "READY",
            num_questions: 1,
            topics_verified: ["Rimozione Verbale"],
            gap_ids: [],
            model_used: "qwen",
            prompt_version: "v1",
            error_message: null,
            generated_at: "2026-11-11T10:00:00Z",
            completed_at: null,
            questions: [],
          },
        ]);
      }
      if (url.endsWith("/api/v1/customquiz/cq_1")) {
        return mockJsonResponse({
          id: "cq_1",
          tenant_id: "default",
          user_id: "operatore_01",
          software: "Verbali CDS",
          module_name: "Ruoli",
          status: "READY",
          num_questions: 1,
          topics_verified: ["Rimozione Verbale"],
          gap_ids: [],
          model_used: "qwen",
          prompt_version: "v1",
          error_message: null,
          generated_at: "2026-11-11T10:00:00Z",
          completed_at: null,
          questions: [
            {
              id: "q_1",
              order_index: 1,
              question_text: "Quale tasto funzione rimuove il verbale dal ruolo?",
              options: [
                { id: "A", text: "F2" },
                { id: "B", text: "F7" },
                { id: "C", text: "F9" },
                { id: "D", text: "F12" },
              ],
              topic: "Rimozione Verbale",
              difficulty: "base",
              gap_id: null,
              sources: [],
            },
          ],
        });
      }
      if (url.endsWith("/api/v1/customquiz/cq_1/submit")) {
        return mockJsonResponse({
          attempt_id: "att_1",
          quiz_id: "cq_1",
          user_id: "operatore_01",
          correct_count: 1,
          total_questions: 1,
          score: 1,
          percentage: 100,
          duration_seconds: 5,
          outcome: "LEARNED",
          topics_understood: ["Rimozione Verbale"],
          topics_to_improve: [],
          question_feedback: [
            {
              question_id: "q_1",
              topic: "Rimozione Verbale",
              user_answer: "B",
              is_correct: true,
              correct_option_id: "B",
              correct_answer: "F7",
              explanation: "Nel manuale è indicato il tasto F7 - Cancella.",
              sources: [],
            },
          ],
          recommended_lessons: [],
          updated_gaps: [],
          completed_at: "2026-11-11T11:05:00Z",
        });
      }
      return mockJsonResponse({}, 404);
    });

    // 1. Test Lesson rich sections & Completion
    renderAt("/learning/crs_1");
    expect(await screen.findByText("Esempio chiusura ruolo")).toBeInTheDocument();
    expect(screen.getByText("Esempio corretto")).toBeInTheDocument();
    expect(screen.getByText("Rimozione senza verifica verbale")).toBeInTheDocument();
    expect(screen.getByText("Simula lo sblocco di un verbale.")).toBeInTheDocument();
    expect(screen.queryByText(/\*\*F7\*\*/)).not.toBeInTheDocument();
    const completeBtn = await screen.findByRole("button", { name: /Segna lezione come completata/i });
    await user.click(completeBtn);
    expect(await screen.findByRole("button", { name: /Lezione completata/i })).toBeInTheDocument();

    // 2. Navigate to My Learning -> Custom Quizzes -> Run 4-option quiz
    await user.click(screen.getByRole("link", { name: "My Learning" }));
    await user.click(await screen.findByRole("tab", { name: /My Custom Quizzes/i }));
    await user.click(await screen.findByRole("button", { name: /Svolgi quiz/i }));

    expect(
      await screen.findByText("Quale tasto funzione rimuove il verbale dal ruolo?")
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /B\.\s*F7/i }));
    await user.click(screen.getByRole("button", { name: /Completa e valuta/i }));

    expect(await screen.findByText(/Risultato: 100\.0%/i)).toBeInTheDocument();
    expect(screen.getByText(/tasto F7 - Cancella/i)).toBeInTheDocument();
  });

  it("exposes RAG course generation and editing controls strictly to Owner role", async () => {
    const user = userEvent.setup();
    const generatedCourse = {
      id: "crs_gen_1",
      opportunity_id: null,
      tenant_id: "default",
      allowed_roles: ["operatore", "owner", "admin"],
      title: "Corso Assistenza Clienti RAG",
      description: "Corso generato automaticamente da manuale.",
      course_type: "documental",
      learning_objectives: ["Aprire correttamente un ticket"],
      prerequisites: [],
      target_audience: ["Operatore PA"],
      difficulty: "base",
      summary: "Sintesi corso",
      lifecycle_status: "GENERATED",
      current_version: 1,
      corpus_version_at_generation: "v1",
      grounding_status: "VERIFIED",
      grounding_report: {},
      model_used: "qwen2.5",
      modules: [
        {
          id: "mod_gen_1",
          order_index: 1,
          title: "Modulo 1",
          description: "Introduzione",
          learning_objective: "Comprendere la procedura",
          lessons: [
            {
              id: "les_gen_1",
              module_id: "mod_gen_1",
              order_index: 1,
              title: "Apertura Ticket",
              objective: "Inviare segnalazione completa",
              explanation: "Indicare oggetto ed ente.",
              procedures: ["Invia email al supporto"],
              practical_examples: [],
              frequent_errors: [],
              exercises: [],
              summary: "Sintesi lezione",
              is_grounded: true,
              grounding_warnings: [],
              sources: [],
            },
          ],
        },
      ],
      quizzes: [],
      created_at: "2026-11-11T10:00:00Z",
      updated_at: "2026-11-11T10:00:00Z",
      published_at: null,
    };

    let currentCourses: typeof generatedCourse[] = [generatedCourse];

    vi.spyOn(window, "fetch").mockImplementation(async (input, init) => {
      const url = typeof input === "string" ? input : input.toString();
      const method = (init?.method ?? "GET").toUpperCase();

      if (url.endsWith("/health")) {
        return mockJsonResponse({ status: "ok", version: "0.1.0", corpus_version: "v1" });
      }
      if (url.endsWith("/api/v1/demo/status")) {
        return mockJsonResponse({ demo_mode_enabled: true });
      }
      if (url.endsWith("/api/v1/demo/users")) {
        return mockJsonResponse([
          {
            user_id: "operatore_01",
            display_name: "Maria Rossi",
            amministrazione: "Comune di Rimini",
            role: "operatore",
            softwares_used: [],
            has_activity: true,
          },
          {
            user_id: "owner_demo",
            display_name: "Elena Conti (Owner)",
            amministrazione: "Ente Pilota PA",
            role: "owner",
            softwares_used: [],
            has_activity: false,
          },
        ]);
      }
      if (url.endsWith("/api/v1/demo/switch-user")) {
        const body = JSON.parse(String(init?.body ?? "{}"));
        if (body.user_id === "owner_demo") {
          return mockJsonResponse({
            token: "signed_owner_token",
            user: {
              user_id: "owner_demo",
              display_name: "Elena Conti (Owner)",
              amministrazione: "Ente Pilota PA",
              role: "owner",
              softwares_used: [],
              has_activity: false,
            },
            tenant_id: "default",
            is_demo: true,
            expires_at: 9999999999,
          });
        }
        return mockJsonResponse({
          token: "signed_op_token",
          user: {
            user_id: "operatore_01",
            display_name: "Maria Rossi",
            amministrazione: "Comune di Rimini",
            role: "operatore",
            softwares_used: [],
            has_activity: true,
          },
          tenant_id: "default",
          is_demo: true,
          expires_at: 9999999999,
        });
      }
      if (url.includes("/api/v1/rag/documents")) {
        return mockJsonResponse([
          {
            document_id: "doc_1",
            source: "manuale_assistenza.md",
            document_type: "markdown",
            area_name: "Info",
            file_hash: "h1",
            chunk_count: 4,
            status: "indexed",
            indexed_at: "2026-11-11T10:00:00Z",
            updated_at: "2026-11-11T10:00:00Z",
          },
        ]);
      }
      if (url.includes("/api/v1/academy/opportunities")) {
        return mockJsonResponse([]);
      }
      if (url.endsWith("/api/v1/academy/courses/generate") && method === "POST") {
        currentCourses = [generatedCourse];
        return mockJsonResponse(generatedCourse);
      }
      if (url.endsWith("/api/v1/academy/courses/crs_gen_1") && method === "PATCH") {
        const body = JSON.parse(String(init?.body ?? "{}"));
        const updated = { ...generatedCourse, title: body.title ?? generatedCourse.title, current_version: 2 };
        currentCourses = [updated];
        return mockJsonResponse(updated);
      }
      if (url.endsWith("/api/v1/academy/courses")) {
        return mockJsonResponse(currentCourses);
      }
      if (url.endsWith("/api/v1/academy/courses/crs_gen_1")) {
        return mockJsonResponse(currentCourses[0]);
      }
      if (url.includes("/learning-overview")) {
        return mockJsonResponse({
          user_id: "operatore_01",
          tenant_id: "default",
          completed_lesson_ids: [],
          course_progress: [],
          course_quiz_attempts: [],
          custom_quiz_attempts: [],
        });
      }
      return mockJsonResponse({}, 404);
    });

    // Operatore does NOT see RAG course generation or course editing controls
    renderAt("/learning");
    expect(await screen.findByText("Corso Assistenza Clienti RAG")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Genera corso con RAG/i })).not.toBeInTheDocument();

    // Switch to Owner -> sees "Genera corso con RAG" button
    await user.click(await screen.findByRole("button", { name: /DEMO/i }));
    await user.click(await screen.findByRole("option", { name: /Elena Conti \(Owner\)/i }));

    const openGenBtn = await screen.findByRole("button", { name: /Genera corso con RAG/i });
    await user.click(openGenBtn);
    await user.click(await screen.findByRole("button", { name: /Avvia generazione RAG/i }));

    // Lands on CourseDetailPage with Owner editing controls
    expect(await screen.findByRole("button", { name: /Modifica corso/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Modifica lezione/i })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Modifica corso/i }));
    const titleInput = await screen.findByLabelText(/Titolo corso/i);
    await user.clear(titleInput);
    await user.type(titleInput, "Corso Ticket Aggiornato");
    await user.click(screen.getByRole("button", { name: /Salva modifiche corso/i }));
    expect(await screen.findByRole("heading", { name: "Corso Ticket Aggiornato" })).toBeInTheDocument();
  });
});
