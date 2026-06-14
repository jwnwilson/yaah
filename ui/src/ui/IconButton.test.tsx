import { render, screen } from "@testing-library/react";
import { IconButton } from "./IconButton";

test("exposes its label as the accessible name", () => {
  render(<IconButton label="Notifications"><span aria-hidden>🔔</span></IconButton>);
  expect(screen.getByRole("button", { name: "Notifications" })).toBeInTheDocument();
});
