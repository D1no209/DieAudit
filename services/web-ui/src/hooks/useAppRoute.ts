import { useCallback, useEffect, useState } from "react";
import { appViewFromHash, hashFromAppView, type AppView } from "../navigation";

export function useAppRoute(): [AppView, (view: AppView) => void] {
  const [activeView, setActiveView] = useState<AppView>(() => appViewFromHash(window.location.hash));

  useEffect(() => {
    const canonicalHash = hashFromAppView(appViewFromHash(window.location.hash));
    if (window.location.hash !== canonicalHash) {
      window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}${canonicalHash}`);
    }

    function syncFromHash() {
      setActiveView(appViewFromHash(window.location.hash));
    }

    window.addEventListener("hashchange", syncFromHash);
    return () => window.removeEventListener("hashchange", syncFromHash);
  }, [activeView]);

  const navigate = useCallback((view: AppView) => {
    const nextHash = hashFromAppView(view);
    if (window.location.hash === nextHash) {
      setActiveView(view);
      return;
    }
    window.location.hash = nextHash;
  }, []);

  return [activeView, navigate];
}
