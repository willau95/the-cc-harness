import { Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "@/components/Layout";
import { DashboardPage } from "@/pages/Dashboard";
import { FleetPage } from "@/pages/Fleet";
import { AgentDetailPage } from "@/pages/AgentDetail";
import { EventsPage } from "@/pages/Events";
import { ProjectsPage } from "@/pages/Projects";
import { ProjectDetailPage } from "@/pages/ProjectDetail";
import { ProposalsPage } from "@/pages/Proposals";
import { ArsenalPage, ArsenalDetailPage } from "@/pages/Arsenal";
import { TasksPage } from "@/pages/Tasks";
import { ChatPage } from "@/pages/Chat";
import { NotFoundPage } from "@/pages/NotFound";

export function App() {
  return (
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
        <Route path="/chat/:agentId" element={<ChatPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
