import { useParams } from "react-router-dom";

export default function BoardPage() {
  const { projectId } = useParams();
  return (
    <div className="p-6">
      <h1 className="text-xl font-semibold">Board</h1>
      <p className="text-sm text-gray-500">Project {projectId}</p>
    </div>
  );
}
