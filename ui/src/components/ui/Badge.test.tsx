import { render, screen } from "@testing-library/react";
import { Badge } from "./Badge";

test("renders its label with the tone classes", () => {
  render(<Badge tone="danger">failed</Badge>);
  const badge = screen.getByText("failed");
  expect(badge.className).toContain("text-danger");
  expect(badge.className).toContain("bg-danger-subtle");
});
