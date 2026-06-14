import { cn } from "./cn";

test("joins truthy class names and drops falsy ones", () => {
  expect(cn("a", false, null, undefined, "b")).toBe("a b");
});

test("returns empty string when nothing truthy", () => {
  expect(cn(false, null, undefined)).toBe("");
});
