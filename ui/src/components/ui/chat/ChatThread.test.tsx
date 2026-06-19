import { render, screen } from "@testing-library/react";
import { ChatThread } from "./ChatThread";
import type { ThreadMessage } from "./types";

const dialog: ThreadMessage[] = [
  { id: "1", sender: { kind: "user", name: "Noel" }, kind: "chat", body: "hi", createdAt: "t1" },
  { id: "2", sender: { kind: "agent", id: "tl", name: "Team Lead", role: "lead" }, kind: "chat", body: "hello", createdAt: "t2" },
];

test("renders all message bodies", () => {
  render(<ChatThread messages={dialog} />);
  expect(screen.getByText("hi")).toBeInTheDocument();
  expect(screen.getByText("hello")).toBeInTheDocument();
});

test("shows the typing indicator when processing is set", () => {
  render(<ChatThread messages={dialog} processing={{ name: "Team Lead" }} />);
  expect(screen.getByText(/team lead is working/i)).toBeInTheDocument();
});

test("read-only hides the composer slot and shows a read-only badge", () => {
  render(<ChatThread messages={dialog} readOnly composer={<div>COMPOSER</div>} />);
  expect(screen.queryByText("COMPOSER")).not.toBeInTheDocument();
  expect(screen.getByText(/read-only/i)).toBeInTheDocument();
});

test("renders the composer slot when interactive", () => {
  render(<ChatThread messages={dialog} composer={<div>COMPOSER</div>} />);
  expect(screen.getByText("COMPOSER")).toBeInTheDocument();
});

test("renders an empty state when there are no messages", () => {
  render(<ChatThread messages={[]} />);
  expect(screen.getByText(/no messages yet/i)).toBeInTheDocument();
});
