import { render, screen } from "@testing-library/react";
import { EmptyState } from "./EmptyState";

test("renders title and description", () => {
  render(<EmptyState title="No projects" description="Create one to start." />);
  expect(screen.getByText("No projects")).toBeInTheDocument();
  expect(screen.getByText("Create one to start.")).toBeInTheDocument();
});
