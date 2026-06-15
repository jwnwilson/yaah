import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryDiff } from "./MemoryDiff";

test("hidden by default, toggles diff open", async () => {
  render(<MemoryDiff diff={"--- a\n+++ b\n+added line"} />);
  expect(screen.queryByText(/added line/)).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: /show diff/i }));
  expect(screen.getByText(/added line/)).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: /hide diff/i }));
  expect(screen.queryByText(/added line/)).not.toBeInTheDocument();
});
