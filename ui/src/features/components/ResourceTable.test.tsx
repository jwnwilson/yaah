import { render, screen } from "@testing-library/react";
import { ResourceTable } from "./ResourceTable";

test("renders rows via column renderers, and an empty message when no rows", () => {
  const { rerender } = render(
    <ResourceTable
      rows={[{ id: "a", name: "Alpha" }]}
      rowKey={(r) => r.id}
      columns={[{ header: "Name", render: (r) => r.name }]}
      actions={(r) => <button>edit {r.name}</button>}
    />,
  );
  expect(screen.getByText("Alpha")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "edit Alpha" })).toBeInTheDocument();

  rerender(
    <ResourceTable rows={[]} rowKey={(r: { id: string }) => r.id} columns={[{ header: "Name", render: () => null }]} empty="Nothing yet" />,
  );
  expect(screen.getByText("Nothing yet")).toBeInTheDocument();
});
