import { render, screen } from "@testing-library/react";
import { Spinner } from "./Spinner";

test("renders an accessible loading status", () => {
  render(<Spinner />);
  expect(screen.getByRole("status", { name: /loading/i })).toBeInTheDocument();
});
