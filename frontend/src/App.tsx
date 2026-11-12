import { Suspense, lazy } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { LoadingState } from "./components/common/PlatformPrimitives";
import { AppLayout } from "./components/layout/AppLayout";
import { AuthProvider } from "./context/AuthContext";
import { ChatPage } from "./pages/ChatPage";
import { KnowledgeManagerRoute } from "./pages/knowledge/KnowledgeManagerRoute";
import { OwnerRoute } from "./pages/owner/OwnerRoute";

const KnowledgeBasePage = lazy(() =>
  import("./pages/knowledge/KnowledgeBasePage").then((m) => ({ default: m.KnowledgeBasePage }))
);

const HomePage = lazy(() => import("./pages/HomePage").then((m) => ({ default: m.HomePage })));
const LearningAreaPage = lazy(() =>
  import("./pages/LearningAreaPage").then((m) => ({ default: m.LearningAreaPage }))
);
const CourseDetailPage = lazy(() =>
  import("./pages/CourseDetailPage").then((m) => ({ default: m.CourseDetailPage }))
);
const MyLearningPage = lazy(() =>
  import("./pages/MyLearningPage").then((m) => ({ default: m.MyLearningPage }))
);
const MyProgressPage = lazy(() =>
  import("./pages/MyProgressPage").then((m) => ({ default: m.MyProgressPage }))
);
const OwnerDashboardPage = lazy(() =>
  import("./pages/owner/OwnerDashboardPage").then((m) => ({ default: m.OwnerDashboardPage }))
);
const OwnerUsersPage = lazy(() =>
  import("./pages/owner/OwnerUsersPage").then((m) => ({ default: m.OwnerUsersPage }))
);
const OwnerTopicsPage = lazy(() =>
  import("./pages/owner/OwnerTopicsPage").then((m) => ({ default: m.OwnerTopicsPage }))
);

function RouteFallback() {
  return (
    <div className="page-container">
      <LoadingState label="Caricamento sezione..." />
    </div>
  );
}

export function AppRoutes() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route
          index
          element={
            <Suspense fallback={<RouteFallback />}>
              <HomePage />
            </Suspense>
          }
        />
        <Route path="assistant" element={<ChatPage embedded />} />
        <Route
          path="learning"
          element={
            <Suspense fallback={<RouteFallback />}>
              <LearningAreaPage />
            </Suspense>
          }
        />
        <Route
          path="learning/:courseId"
          element={
            <Suspense fallback={<RouteFallback />}>
              <CourseDetailPage />
            </Suspense>
          }
        />
        <Route
          path="my-learning"
          element={
            <Suspense fallback={<RouteFallback />}>
              <MyLearningPage />
            </Suspense>
          }
        />
        <Route
          path="my-progress"
          element={
            <Suspense fallback={<RouteFallback />}>
              <MyProgressPage />
            </Suspense>
          }
        />
        <Route
          path="owner"
          element={
            <OwnerRoute>
              <Suspense fallback={<RouteFallback />}>
                <OwnerDashboardPage />
              </Suspense>
            </OwnerRoute>
          }
        />
        <Route
          path="owner/users"
          element={
            <OwnerRoute>
              <Suspense fallback={<RouteFallback />}>
                <OwnerUsersPage />
              </Suspense>
            </OwnerRoute>
          }
        />
        <Route
          path="owner/topics"
          element={
            <OwnerRoute>
              <Suspense fallback={<RouteFallback />}>
                <OwnerTopicsPage />
              </Suspense>
            </OwnerRoute>
          }
        />
        <Route
          path="knowledge-base"
          element={
            <KnowledgeManagerRoute>
              <Suspense fallback={<RouteFallback />}>
                <KnowledgeBasePage />
              </Suspense>
            </KnowledgeManagerRoute>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}

export function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </BrowserRouter>
  );
}

export default App;
