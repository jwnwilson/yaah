import { render, screen } from "@testing-library/react";
import { TypingIndicator } from "./TypingIndicator";

test("announces which agent is working for screen readers", () => {
  render(<TypingIndicator name="Team Lead" />);
  expect(screen.getByText(/team lead is working/i)).toBeInTheDocument();
});

test("renders three animated dots", () => {
  const { container } = render(<TypingIndicator name="Backend" />);
  expect(container.querySelectorAll("[data-dot]")).toHaveLength(3);
});
