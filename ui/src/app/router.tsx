import { createBrowserRouter, Navigate, type RouteObject } from "react-router-dom";
import { AppLayout } from "./AppLayout";
import ProjectsPage from "../features/projects/ProjectsPage";
import BoardPage from "../features/board/BoardPage";
import { ManageLayout } from "../features/manage/ManageLayout";
import { SecretsPage } from "../features/manage/SecretsPage";
import { SkillsPage } from "../features/manage/SkillsPage";
import { McpServersPage } from "../features/manage/McpServersPage";
import { BudgetPage } from "../features/manage/BudgetPage";
import { AuditPage } from "../features/manage/AuditPage";
import { AgentsPage } from "../features/manage/AgentsPage";
import { MemoryPage } from "../features/manage/MemoryPage";
import { TeamPage } from "../features/team/TeamPage";
import { AgentDetailPage } from "../features/team/AgentDetailPage";
import { InboxPage } from "../features/inbox/InboxPage";

export const routes: RouteObject[] = [
  {
    element: <AppLayout />,
    children: [
      { path: "/", element: <ProjectsPage /> },
      { path: "/projects/:projectId", element: <BoardPage /> },
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
