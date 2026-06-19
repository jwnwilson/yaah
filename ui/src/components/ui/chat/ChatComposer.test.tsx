import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { ChatComposer } from "./ChatComposer";

test("submitting calls onSubmit with the trimmed text", async () => {
  const onSubmit = vi.fn();
  render(
    <ChatComposer value="  hello  " onChange={vi.fn()} onSubmit={onSubmit} placeholder="Message…" />,
  );
  await userEvent.click(screen.getByRole("button", { name: /send/i }));
  expect(onSubmit).toHaveBeenCalledWith("hello");
});

test("does not submit empty text", async () => {
  const onSubmit = vi.fn();
  render(<ChatComposer value="   " onChange={vi.fn()} onSubmit={onSubmit} placeholder="Message…" />);
  await userEvent.click(screen.getByRole("button", { name: /send/i }));
  expect(onSubmit).not.toHaveBeenCalled();
});

test("shows the mic only when dictation is supported", () => {
  const { rerender } = render(
    <ChatComposer value="" onChange={vi.fn()} onSubmit={vi.fn()} placeholder="m" micSupported />,
  );
  expect(screen.getByLabelText(/dictate|voice/i)).toBeInTheDocument();
  rerender(<ChatComposer value="" onChange={vi.fn()} onSubmit={vi.fn()} placeholder="m" />);
  expect(screen.queryByLabelText(/dictate|voice/i)).not.toBeInTheDocument();
});
