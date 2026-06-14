import { render, screen } from "@testing-library/react";
import { Field, Input } from "./Field";

test("associates a label with its control", () => {
  render(
    <Field label="Name">
      <Input value="" onChange={() => {}} />
    </Field>,
  );
  expect(screen.getByRole("textbox", { name: "Name" })).toBeInTheDocument();
});
