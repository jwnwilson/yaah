import { useParams, useSearchParams, Link } from "react-router-dom";
import { Board } from "./Board";

export default function BoardPage() {
  const { projectId } = useParams();
  const [params, setParams] = useSearchParams();
  if (!projectId) return null;

  const openItem = (id: string) => {
    params.set("item", id);
    setParams(params);
  };

  return (
    <div className="flex h-screen flex-col">
      <header className="flex items-center gap-3 border-b p-3">
        <Link to="/" className="text-sm text-blue-700">← Projects</Link>
        <h1 className="font-semibold">Board</h1>
      </header>
      <Board projectId={projectId} onOpen={openItem} />
    </div>
  );
}
