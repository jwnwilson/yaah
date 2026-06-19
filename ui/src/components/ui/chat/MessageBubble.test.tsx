import { render, screen } from "@testing-library/react";
import { MessageBubble } from "./MessageBubble";
import type { ThreadMessage } from "./types";

const userMsg: ThreadMessage = {
  id: "m1",
  sender: { kind: "user", name: "Noel" },
  kind: "chat",
  body: "Break the epic into tasks.",
  createdAt: "2026-06-19T10:00:00Z",
};

const agentMsg: ThreadMessage = {
  id: "m2",
  sender: { kind: "agent", id: "be", name: "Backend", role: "backend" },
  recipient: { kind: "agent", id: "tl", name: "Team Lead", role: "lead" },
  kind: "report",
  body: "Opened PR #88.",
  createdAt: "2026-06-19T10:01:00Z",
};

test("dialog layout right-aligns the user's own message", () => {
  const { container } = render(<MessageBubble message={userMsg} multi={false} />);
  expect(container.firstChild).toHaveClass("flex-row-reverse");
  expect(screen.getByText("Break the epic into tasks.")).toBeInTheDocument();
});

test("multi layout shows a sender → recipient line and a kind tag", () => {
  render(<MessageBubble message={agentMsg} multi={true} />);
  expect(screen.getByText(/backend\s*→\s*team lead/i)).toBeInTheDocument();
  expect(screen.getByText("report")).toBeInTheDocument();
});

test("dialog layout shows no kind tag", () => {
  render(<MessageBubble message={userMsg} multi={false} />);
  expect(screen.queryByText("chat")).not.toBeInTheDocument();
});
