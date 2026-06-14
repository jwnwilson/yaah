import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ThemeToggle } from "./ThemeToggle";

beforeEach(() => {
  localStorage.clear();
  document.documentElement.classList.remove("dark");
});

test("toggles theme on click and exposes an accessible label", async () => {
  render(<ThemeToggle />);
  // starts dark -> label offers switching to light
  const button = screen.getByRole("button", { name: /switch to light theme/i });
  await userEvent.click(button);
  expect(screen.getByRole("button", { name: /switch to dark theme/i })).toBeInTheDocument();
});
