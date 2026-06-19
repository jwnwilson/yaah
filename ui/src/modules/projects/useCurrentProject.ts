import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";

const KEY = "yaah:lastProject";

/** The active project id: taken from the URL on /projects/:id… routes, otherwise the
 * last one visited (persisted), so the sidebar's Board/Backlog links work from anywhere. */
export function useCurrentProjectId(): string | undefined {
  const { pathname } = useLocation();
  const routeId = pathname.match(/^\/projects\/([^/]+)/)?.[1];
  const [stored, setStored] = useState<string | undefined>(() => {
    try {
      return localStorage.getItem(KEY) ?? undefined;
    } catch {
      return undefined;
    }
  });

  useEffect(() => {
    if (routeId && routeId !== stored) {
      try {
        localStorage.setItem(KEY, routeId);
      } catch {
        /* ignore */
      }
      setStored(routeId);
    }
  }, [routeId, stored]);

  return routeId ?? stored;
}
