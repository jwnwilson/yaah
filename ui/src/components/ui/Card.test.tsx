import { render, screen } from "@testing-library/react";
import { Card } from "./Card";

test("renders children inside a surface container", () => {
  render(<Card>contents</Card>);
  const el = screen.getByText("contents");
  expect(el.className).toContain("bg-surface");
  expect(el.className).toContain("border-line");
});
