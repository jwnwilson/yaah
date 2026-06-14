import { render, screen } from "@testing-library/react";
import { Button } from "./Button";

test("renders children and forwards type", () => {
  render(<Button type="submit">Save</Button>);
  const btn = screen.getByRole("button", { name: "Save" });
  expect(btn).toHaveAttribute("type", "submit");
});

test("is disabled and shows a spinner when loading", () => {
  render(<Button loading>Save</Button>);
  expect(screen.getByRole("button", { name: /save/i })).toBeDisabled();
  expect(screen.getByRole("status", { name: /loading/i })).toBeInTheDocument();
});
