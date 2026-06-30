import { useCallback, useEffect, useState } from "react";
import { appViewFromHash, hashFromAppView, projectRouteFromHash, type AppView } from "../navigation";

export function useAppRoute(): [AppView, (view: AppView) => void] {
  const [activeView, setActiveView] = useState<AppView>(() => appViewFromHash(window.location.hash));

  useEffect(() => {
    const projectRoute = projectRouteFromHash(window.location.hash);
    const canonicalHash = projectRoute.projectId ? window.location.hash : hashFromAppView(appViewFromHash(window.location.hash));
    if (!projectRoute.projectId && window.location.hash !== canonicalHash) {
      window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}${canonicalHash}`);
    }

    function syncFromHash() {
      setActiveView(appViewFromHash(window.location.hash));
      window.dispatchEvent(new Event("dieaudit-routechange"));
    }

    window.addEventListener("hashchange", syncFromHash);
    return () => window.removeEventListener("hashchange", syncFromHash);
  }, [activeView]);

  const navigate = useCallback((view: AppView) => {
    const nextHash = hashFromAppView(view);
    if (window.location.hash === nextHash) {
      setActiveView(view);
      window.dispatchEvent(new Event("dieaudit-routechange"));
      return;
    }
    window.location.hash = nextHash;
  }, []);

  return [activeView, navigate];
}
