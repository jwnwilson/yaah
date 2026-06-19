import { render, screen } from "@testing-library/react";
import { StatusChip } from "./StatusChip";

test("renders its label centered as a status pill", () => {
  render(<StatusChip>Gate opened · PR review needed</StatusChip>);
  expect(screen.getByText(/gate opened/i)).toBeInTheDocument();
});
