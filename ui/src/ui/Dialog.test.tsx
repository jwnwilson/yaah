import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Dialog } from "./Dialog";

test("Escape and overlay click close; inside click does not", async () => {
  const onClose = vi.fn();
  render(
    <Dialog title="Edit" onClose={onClose}>
      <button>Inside</button>
    </Dialog>,
  );
  const dialog = screen.getByRole("dialog", { name: "Edit" });
  await userEvent.click(screen.getByRole("button", { name: "Inside" }));
  expect(onClose).not.toHaveBeenCalled();
  await userEvent.keyboard("{Escape}");
  expect(onClose).toHaveBeenCalledTimes(1);
  expect(dialog).toHaveAttribute("aria-modal", "true");
});
