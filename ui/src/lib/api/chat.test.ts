import { toThreadMessages } from "./chat";

test("maps refinement messages to ThreadMessages with the right participants", () => {
  const out = toThreadMessages(
    [
      { id: "a", role: "user", content: "hi" },
      { id: "b", role: "assistant", content: "hello" },
    ],
    { kind: "agent", id: "tl", name: "Team Lead", role: "lead" },
  );
  expect(out[0].sender).toEqual({ kind: "user", name: "You" });
  expect(out[0]).toMatchObject({ id: "a", kind: "chat", body: "hi" });
  expect(out[1].sender).toEqual({ kind: "agent", id: "tl", name: "Team Lead", role: "lead" });
  expect(out[1].body).toBe("hello");
});
