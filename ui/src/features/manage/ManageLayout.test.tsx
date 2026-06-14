import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { ManageLayout } from "./ManageLayout";

test("sidebar lists all manage sections", () => {
  render(<MemoryRouter><ManageLayout /></MemoryRouter>);
  for (const label of ["Secrets", "Skills", "MCP servers", "Budget", "Models", "Audit", "Memory"]) {
    expect(screen.getByRole("link", { name: label })).toBeInTheDocument();
  }
});
