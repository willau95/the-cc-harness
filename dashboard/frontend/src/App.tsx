import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "@/components/Layout";
import { PageSkeleton } from "@/components/PageSkeleton";

// Code-split every page so the initial JS bundle only contains Layout +
// shared primitives. Each route loads its own chunk on first visit.
const DashboardPage      = lazy(() => import("@/pages/Dashboard").then(m => ({ default: m.DashboardPage })));
const FleetPage          = lazy(() => import("@/pages/Fleet").then(m => ({ default: m.FleetPage })));
const AgentDetailPage    = lazy(() => import("@/pages/AgentDetail").then(m => ({ default: m.AgentDetailPage })));
const EventsPage         = lazy(() => import("@/pages/Events").then(m => ({ default: m.EventsPage })));
const ProjectsPage       = lazy(() => import("@/pages/Projects").then(m => ({ default: m.ProjectsPage })));
const ProjectDetailPage  = lazy(() => import("@/pages/ProjectDetail").then(m => ({ default: m.ProjectDetailPage })));
const ProposalsPage      = lazy(() => import("@/pages/Proposals").then(m => ({ default: m.ProposalsPage })));
const ArsenalPage        = lazy(() => import("@/pages/Arsenal").then(m => ({ default: m.ArsenalPage })));
const ArsenalDetailPage  = lazy(() => import("@/pages/Arsenal").then(m => ({ default: m.ArsenalDetailPage })));
const TasksPage          = lazy(() => import("@/pages/Tasks").then(m => ({ default: m.TasksPage })));
const ChatPage           = lazy(() => import("@/pages/Chat").then(m => ({ default: m.ChatPage })));
const ChatIndexPage      = lazy(() => import("@/pages/ChatIndex").then(m => ({ default: m.ChatIndexPage })));
const NotFoundPage       = lazy(() => import("@/pages/NotFound").then(m => ({ default: m.NotFoundPage })));

export function App() {
  return (
    <Suspense fallback={<PageSkeleton variant="list" />}>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/fleet" element={<FleetPage />} />
          <Route path="/fleet/:tab" element={<FleetPage />} />
          <Route path="/agents/:agentId" element={<AgentDetailPage />} />
          <Route path="/events" element={<EventsPage />} />
          <Route path="/projects" element={<ProjectsPage />} />
          <Route path="/projects/:proj" element={<ProjectDetailPage />} />
          <Route path="/proposals" element={<ProposalsPage />} />
          <Route path="/proposals/:tab" element={<ProposalsPage />} />
          <Route path="/arsenal" element={<ArsenalPage />} />
          <Route path="/arsenal/:slug" element={<ArsenalDetailPage />} />
          <Route path="/tasks" element={<TasksPage />} />
          <Route path="/tasks/:tab" element={<TasksPage />} />
          <Route path="/chat" element={<ChatIndexPage />} />
          <Route path="/chat/:agentId" element={<ChatPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Routes>
    </Suspense>
  );
}
