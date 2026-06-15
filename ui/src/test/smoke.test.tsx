import { render, screen } from "@testing-library/react";
import { AppProviders } from "@/app/App";

test("renders app shell", async () => {
  window.history.pushState({}, "", "/");
  render(<AppProviders />);
  expect(await screen.findByRole("heading", { name: /projects/i })).toBeInTheDocument();
});
