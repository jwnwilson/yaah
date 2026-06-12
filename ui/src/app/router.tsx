import { createBrowserRouter } from "react-router-dom";
import ProjectsPage from "../features/projects/ProjectsPage";
import BoardPage from "../features/board/BoardPage";

export const router = createBrowserRouter([
  { path: "/", element: <ProjectsPage /> },
  { path: "/projects/:projectId", element: <BoardPage /> },
]);
