import { createBrowserRouter, Navigate, type RouteObject } from "react-router-dom";
import BoardPage from "@/modules/board/BoardPage";
import { InboxPage } from "@/modules/inbox/InboxPage";
import { AgentsPage } from "@/modules/manage/AgentsPage";
import { AuditPage } from "@/modules/manage/AuditPage";
import { BudgetPage } from "@/modules/manage/BudgetPage";
import { ManageLayout } from "@/modules/manage/ManageLayout";
import { McpServersPage } from "@/modules/manage/McpServersPage";
import { MemoryPage } from "@/modules/manage/MemoryPage";
import { SecretsPage } from "@/modules/manage/SecretsPage";
import { SkillsPage } from "@/modules/manage/SkillsPage";
import ProjectsPage from "@/modules/projects/ProjectsPage";
import { RunInspectorPage } from "@/modules/runs/RunInspectorPage";
import { AgentDetailPage } from "@/modules/team/AgentDetailPage";
import { TeamPage } from "@/modules/team/TeamPage";
import { AppLayout } from "./AppLayout";

export const routes: RouteObject[] = [
  {
    element: <AppLayout />,
    children: [
      { path: "/", element: <ProjectsPage /> },
      { path: "/projects/:projectId", element: <BoardPage /> },
      { path: "/runs/:runId", element: <RunInspectorPage /> },
      { path: "/team", element: <TeamPage /> },
      { path: "/team/:agentId", element: <AgentDetailPage /> },
      { path: "/inbox", element: <InboxPage /> },
      {
        path: "/manage",
        element: <ManageLayout />,
        children: [
          { index: true, element: <Navigate to="secrets" replace /> },
          { path: "secrets", element: <SecretsPage /> },
          { path: "skills", element: <SkillsPage /> },
          { path: "mcp-servers", element: <McpServersPage /> },
          { path: "usage", element: <BudgetPage /> },
          { path: "agents", element: <AgentsPage /> },
          { path: "audit", element: <AuditPage /> },
          { path: "memory", element: <MemoryPage /> },
        ],
      },
    ],
  },
];

export const router = createBrowserRouter(routes);
