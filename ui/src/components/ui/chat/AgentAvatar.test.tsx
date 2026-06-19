import { render, screen } from "@testing-library/react";
import { AgentAvatar } from "./AgentAvatar";

test("renders the first two initials of the participant name", () => {
  render(<AgentAvatar participant={{ kind: "agent", name: "Team Lead", role: "lead" }} />);
  expect(screen.getByText("TL")).toBeInTheDocument();
});

test("uses a single initial for a one-word name", () => {
  render(<AgentAvatar participant={{ kind: "user", name: "Noel" }} />);
  expect(screen.getByText("N")).toBeInTheDocument();
});

test("exposes the full name as a title for hover/accessibility", () => {
  render(<AgentAvatar participant={{ kind: "agent", name: "Backend", role: "backend" }} />);
  expect(screen.getByTitle("Backend")).toBeInTheDocument();
});
