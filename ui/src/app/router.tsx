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

export const routes: RouteObject[] = [
  {
    element: <AppLayout />,
    children: [
      { path: "/", element: <ProjectsPage /> },
      { path: "/projects/:projectId", element: <BoardPage /> },
      {
        path: "/manage",
        element: <ManageLayout />,
        children: [
          { index: true, element: <Navigate to="secrets" replace /> },
          { path: "secrets", element: <SecretsPage /> },
          { path: "skills", element: <SkillsPage /> },
          { path: "mcp-servers", element: <McpServersPage /> },
          { path: "usage", element: <BudgetPage /> },
          { path: "audit", element: <AuditPage /> },
        ],
      },
    ],
  },
];

export const router = createBrowserRouter(routes);
