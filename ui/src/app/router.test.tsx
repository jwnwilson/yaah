import { render, screen } from "@testing-library/react";
import { AppProviders } from "./App";

test("renders the projects page at the root route", async () => {
  window.history.pushState({}, "", "/");
  render(<AppProviders />);
  expect(await screen.findByRole("heading", { name: /projects/i })).toBeInTheDocument();
});
