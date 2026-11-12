/** TypeScript contracts for AI Software Academy Milestone UI 2 (Auth/Demo, Academy, CustomQuiz, Owner). */

export type UserRole = "operatore" | "learning_manager" | "owner" | "knowledge_manager" | "admin";

export function formatRoleLabel(role: string): string {
  const normalized = role.trim().toLowerCase();
  if (normalized === "owner" || normalized === "learning_manager") {
    return "learning manager";
  }
  if (normalized === "knowledge_manager") {
    return "knowledge manager";
  }
  return role;
}

export interface DemoUserItem {
  user_id: string;
  display_name: string;
  amministrazione: string;
  role: string;
  softwares_used: string[];
  has_activity: boolean;
}

export interface DemoStatusResponse {
  demo_mode_enabled: boolean;
  app_env: string;
}

export interface DemoSwitchResponse {
  token: string;
  user: DemoUserItem;
  tenant_id: string;
  is_demo: boolean;
  expires_at: number;
}

export interface RequestAuthContext {
  tenantId: string;
  userId: string;
  role: string;
  demoToken: string | null;
}

export interface LessonSource {
  document_id: string;
  document_title: string;
  document_version: string;
  chunk_id: string;
  page: number | null;
  section: string;
  source: string;
  updated_at: string;
  excerpt: string;
}

export interface PracticalExample {
  label?: string;
  is_correct?: boolean;
  content?: string;
  section?: string;
  scenario?: string;
  steps?: string[];
  expected_result?: string;
  [key: string]: unknown;
}

export interface FrequentErrorItem {
  error_or_antipattern?: string;
  consequence_or_fix?: string;
  section?: string;
  error?: string;
  cause?: string;
  solution?: string;
  [key: string]: unknown;
}

export interface ExerciseItem {
  title?: string;
  scenario?: string;
  expected_steps?: string[];
  source_section?: string;
  instruction?: string;
  expected_outcome?: string;
  [key: string]: unknown;
}

export interface Lesson {
  id: string;
  module_id: string;
  order_index: number;
  title: string;
  objective: string;
  explanation: string;
  procedures: string[];
  practical_examples: PracticalExample[];
  frequent_errors: FrequentErrorItem[];
  exercises: ExerciseItem[];
  summary: string;
  is_grounded: boolean;
  grounding_warnings: string[];
  sources: LessonSource[];
}

export interface CourseModule {
  id: string;
  order_index: number;
  title: string;
  description: string;
  learning_objective: string;
  lessons: Lesson[];
}

export interface CourseQuizQuestion {
  id: string;
  order_index: number;
  question_type: string;
  question_text: string;
  options: string[];
  correct_answer: string;
  explanation: string;
  source_document_id: string;
  source_chunk_id: string;
  source_section: string;
}

export interface CourseQuiz {
  id: string;
  course_id: string;
  lesson_id: string | null;
  title: string;
  passing_score: number;
  questions: CourseQuizQuestion[];
}

export interface Course {
  id: string;
  opportunity_id: string | null;
  tenant_id: string;
  allowed_roles: string[];
  title: string;
  description: string;
  course_type: string;
  learning_objectives: string[];
  prerequisites: string[];
  target_audience: string[];
  difficulty: string;
  summary: string;
  lifecycle_status: string;
  current_version: number;
  corpus_version_at_generation: string;
  grounding_status: string;
  model_used: string;
  modules: CourseModule[];
  quizzes: CourseQuiz[];
  created_at: string;
  updated_at: string;
  published_at: string | null;
}

export interface LessonCompletionResponse {
  lesson_id: string;
  course_id: string;
  user_id: string;
  completed: boolean;
  completed_at: string;
}

export interface CourseProgressOverviewItem {
  course_id: string;
  completed_lessons: number;
  total_lessons: number;
  completion_percentage: number;
  status: "NOT_STARTED" | "IN_PROGRESS" | "COMPLETED";
  best_quiz_percentage: number | null;
  last_activity_at: string | null;
}

export interface CourseQuizAttemptSummary {
  attempt_id: string;
  quiz_id: string;
  quiz_title: string;
  course_id: string;
  course_title: string;
  lesson_id: string | null;
  percentage: number;
  passed: boolean;
  wrong_topics: string[];
  completed_at: string;
}

export interface CustomQuizAttemptSummary {
  attempt_id: string;
  quiz_id: string;
  software: string;
  module_name: string;
  topics_verified: string[];
  correct_count: number;
  total_questions: number;
  percentage: number;
  outcome: string;
  duration_seconds: number;
  completed_at: string;
}

export interface UserLearningOverview {
  user_id: string;
  tenant_id: string;
  completed_lesson_ids: string[];
  course_progress: CourseProgressOverviewItem[];
  course_quiz_attempts: CourseQuizAttemptSummary[];
  custom_quiz_attempts: CustomQuizAttemptSummary[];
}

export interface CourseQuizQuestionFeedback {
  question_id: string;
  question_text: string;
  user_answer: string;
  is_correct: boolean;
  correct_answer: string;
  explanation: string;
  source_section: string;
}

export interface CourseQuizSubmitResponse {
  attempt_id: string;
  quiz_id: string;
  course_id: string;
  user_id: string;
  correct_count: number;
  total_questions: number;
  percentage: number;
  passed: boolean;
  wrong_topics: string[];
  question_feedback?: CourseQuizQuestionFeedback[];
  gaps_updated: number;
  completed_at: string;
}

export interface QuizOptionPublic {
  id: "A" | "B" | "C" | "D";
  text: string;
}

export interface CustomQuizQuestionPublic {
  id: string;
  order_index: number;
  question_text: string;
  options: QuizOptionPublic[];
  topic: string;
  difficulty: string;
  gap_id: string | null;
  sources: Array<Record<string, unknown>>;
}

export interface CustomQuiz {
  id: string;
  tenant_id: string;
  user_id: string;
  software: string;
  module_name: string;
  status: string;
  num_questions: number;
  topics_verified: string[];
  gap_ids: string[];
  model_used: string;
  prompt_version: string;
  error_message: string | null;
  generated_at: string;
  completed_at: string | null;
  questions: CustomQuizQuestionPublic[];
}

export interface QuestionFeedbackItem {
  question_id: string;
  topic: string;
  user_answer: string;
  is_correct: boolean;
  correct_option_id: string;
  correct_answer: string;
  explanation: string;
  sources: Array<Record<string, unknown>>;
}

export interface RecommendedLessonItem {
  course_id: string;
  course_title: string;
  lesson_id: string | null;
  lesson_title: string | null;
  topic: string;
  reason: string;
}

export interface CustomQuizResult {
  attempt_id: string;
  quiz_id: string;
  user_id: string;
  correct_count: number;
  total_questions: number;
  score: number;
  percentage: number;
  duration_seconds: number;
  outcome: string;
  topics_understood: string[];
  topics_to_improve: string[];
  question_feedback: QuestionFeedbackItem[];
  recommended_lessons: RecommendedLessonItem[];
  updated_gaps: Array<Record<string, unknown>>;
  completed_at: string;
}

export interface LearningGap {
  id: string;
  user_id: string;
  topic: string;
  software: string;
  module_name: string;
  evidences: Array<Record<string, unknown>>;
  evidence_sources: string[];
  priority: string;
  confidence: number;
  status: string;
  positive_verifications: number;
  repeated_error_count: number;
  detected_at: string;
  last_verified_at: string | null;
  resolved_at: string | null;
}

export interface TopicProfileItem {
  topic: string;
  software: string;
  module_name: string;
  estimated_level: number;
  learning_stage: string;
  rag_query_count: number;
  troubleshooting_count: number;
  verification_count: number;
  correct_count: number;
  error_count: number;
  frequent_questions: string[];
  last_verified_at: string | null;
}

export interface UserLearningProfile {
  user_id: string;
  tenant_id: string;
  softwares_used: string[];
  modules_used: string[];
  known_topics: string[];
  difficulty_topics: string[];
  frequent_questions: string[];
  topic_profiles: TopicProfileItem[];
  open_gaps: LearningGap[];
}

export interface LearningMetrics {
  user_id: string;
  tenant_id: string;
  filters: Record<string, unknown>;
  quiz_accuracy: number;
  learning_improvement: number | null;
  knowledge_gap_resolution_rate: number;
  retention_rate: number | null;
  repeated_error_rate: number;
  learning_progress: number;
  attempts_count: number;
  gaps_summary: Record<string, number>;
  learning_stages_summary: Record<string, number>;
  per_topic_evolution: Array<Record<string, unknown>>;
}

export interface TrendPoint {
  period: string;
  attempts: number;
  avg_score: number;
  gaps_opened: number;
  gaps_resolved: number;
}

export interface OwnerOverview {
  tenant_id: string;
  filters: Record<string, unknown>;
  total_users: number;
  active_users_in_period: number;
  course_completion_rate: number;
  avg_quiz_score: number;
  avg_learning_improvement: number | null;
  knowledge_gap_resolution_rate: number;
  open_gaps_count: number;
  users_with_critical_gaps: number;
  improvement_vs_previous_period: number | null;
  available_softwares: string[];
  available_modules: string[];
  available_administrations: string[];
  timeline: TrendPoint[];
}

export interface OwnerUserOverviewItem {
  user_id: string;
  display_name: string;
  amministrazione: string;
  softwares_used: string[];
  courses_completed: number;
  quiz_success_rate: number;
  custom_quizzes_count: number;
  learning_improvement: number | null;
  open_gaps_count: number;
  critical_gaps_count: number;
  last_activity_at: string | null;
  overall_status: string;
}

export interface OwnerUsersPage {
  tenant_id: string;
  total: number;
  page: number;
  page_size: number;
  items: OwnerUserOverviewItem[];
}

export interface OwnerUserDetail {
  tenant_id: string;
  user_id: string;
  display_name: string;
  amministrazione: string;
  overall_status: string;
  learning_performance: {
    course_quiz_evolution: Array<{
      attempt_id: string;
      quiz_id: string;
      quiz_type: string;
      title: string;
      percentage: number;
      passed_or_outcome: string;
      completed_at: string;
    }>;
    custom_quiz_evolution: Array<{
      attempt_id: string;
      quiz_id: string;
      quiz_type: string;
      title: string;
      percentage: number;
      passed_or_outcome: string;
      completed_at: string;
    }>;
    competence_over_time: TrendPoint[];
    courses_completed: Array<{
      course_id: string;
      title: string;
      course_type: string;
      status: string;
      best_percentage: number | null;
      last_attempt_at: string | null;
    }>;
    courses_to_complete: Array<{
      course_id: string;
      title: string;
      course_type: string;
      status: string;
      best_percentage: number | null;
      last_attempt_at: string | null;
    }>;
    retention_rate: number | null;
  };
  knowledge_gaps: Array<{
    gap_id: string;
    topic: string;
    software: string;
    module_name: string;
    criticality: "CRITICAL" | "HIGH" | "MEDIUM" | "LOW";
    error_count: number;
    last_difficulty_at: string | null;
    verifications_count: number;
    status: string;
    last_result_percentage: number | null;
  }>;
  learning_history: Array<{
    event_type: string;
    title: string;
    topic: string | null;
    result_summary: string;
    percentage: number | null;
    occurred_at: string;
  }>;
}

export interface OwnerTopicReviewItem {
  topic: string;
  software: string;
  module_name: string;
  affected_users_count: number;
  total_gaps_count: number;
  open_gaps_count: number;
  avg_error_rate: number;
  criticality: "CRITICAL" | "HIGH" | "MEDIUM" | "LOW";
  evolution_vs_previous_period: number | null;
}

export interface OwnerTopicDrilldown {
  tenant_id: string;
  topic_summary: OwnerTopicReviewItem;
  affected_users: Array<{
    user_id: string;
    display_name: string;
    amministrazione: string;
    gap_status: string;
    priority: string;
    repeated_error_count: number;
    last_verified_at: string | null;
  }>;
}

export interface OwnerCustomQuizAnalytics {
  tenant_id: string;
  filters: Record<string, unknown>;
  total_generated: number;
  total_completed: number;
  avg_correct_percentage: number;
  improvement_between_verifications: number | null;
  gaps_resolved_via_followup: number;
  persistent_gaps_count: number;
  repeated_error_rate: number;
  retention_rate: number | null;
  timeline: TrendPoint[];
}

export interface OwnerInsightItem {
  category: string;
  severity: string;
  message: string;
  recommended_action: string;
  evidence_metrics: Record<string, unknown>;
  source_engine: "deterministic" | "qwen_synthesized";
}

export interface OwnerInsightsResponse {
  tenant_id: string;
  filters: Record<string, unknown>;
  model_used: string;
  insights: OwnerInsightItem[];
}

export interface KnowledgeDocumentInfo {
  document_id: string;
  source: string;
  document_type: string;
  area_name: string | null;
  file_hash: string;
  chunk_count: number;
  status: string;
  indexed_at: string;
  updated_at: string;
}

export interface TrainingOpportunityItem {
  id: string;
  tenant_id: string;
  title: string;
  description: string;
  learning_objective: string;
  course_type: "documental" | "applicative" | string;
  topics: string[];
  difficulty: string;
  relevance_score: number;
  status: string;
}

export interface CourseGeneratePayload {
  opportunity_id?: string;
  document_source?: string;
  course_type?: "documental" | "applicative";
  allowed_roles?: string[];
}

export interface CourseUpdatePayload {
  title?: string;
  description?: string;
  summary?: string;
  difficulty?: string;
  allowed_roles?: string[];
  change_summary?: string;
}

export interface LessonUpdatePayload {
  title?: string;
  objective?: string;
  explanation?: string;
  procedures?: string[];
  summary?: string;
  change_summary?: string;
}

export interface KnowledgeDocumentListItem {
  document_id: string;
  filename: string;
  relative_path: string;
  area: string;
  extension: string;
  size_bytes: number;
  status: string;
  chunk_count: number;
  updated_at: string;
  indexed_at: string | null;
}

export interface KnowledgeDocumentsPage {
  total: number;
  page: number;
  page_size: number;
  indexed_total: number;
  total_chunks: number;
  areas: string[];
  extensions: string[];
  supported_extensions: string[];
  items: KnowledgeDocumentListItem[];
}

export interface KnowledgeDocumentContent {
  document_id: string;
  filename: string;
  relative_path: string;
  area: string;
  extension: string;
  size_bytes: number;
  content: string;
  truncated: boolean;
}

export interface KnowledgeUploadFileOutcome {
  filename: string;
  relative_path: string;
  status: "uploaded" | "overwritten" | "skipped_exists" | "rejected";
  detail: string;
  size_bytes: number;
}

export interface KnowledgeIngestSummary {
  status: string;
  corpus_version: string;
  files_scanned: number;
  files_indexed: number;
  files_skipped_unchanged: number;
  files_skipped_duplicate: number;
  files_failed: number;
  chunks_created: number;
  processing_time_ms: number;
}

export interface KnowledgeUploadResponse {
  uploaded_count: number;
  skipped_count: number;
  rejected_count: number;
  results: KnowledgeUploadFileOutcome[];
  ingest: KnowledgeIngestSummary | null;
}
