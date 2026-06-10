import type { ReactNode } from "react";
import type { DashboardController } from "../hooks/useDashboardController";
import type { AppView } from "../navigation";
import { routeRenderers } from "./routeRenderers";

type RouteDefinition = {
  render: (dashboard: DashboardController, onViewChange: (view: AppView) => void) => ReactNode;
};

export const routeRegistry: Record<AppView, RouteDefinition> = {
  overview: { render: routeRenderers.overview },
  projects: { render: routeRenderers.projects },
  "audit-runs": { render: routeRenderers["audit-runs"] },
  "agent-runs": { render: routeRenderers["agent-runs"] },
  findings: { render: routeRenderers.findings },
  "finding-review": { render: routeRenderers["finding-review"] },
  dependencies: { render: routeRenderers.dependencies },
  reports: { render: routeRenderers.reports },
  runtime: { render: routeRenderers.runtime },
  "runtime-readiness": { render: routeRenderers["runtime-readiness"] },
  "runtime-containers": { render: routeRenderers["runtime-containers"] },
  "runtime-sandbox": { render: routeRenderers["runtime-sandbox"] },
  knowledge: { render: routeRenderers.knowledge },
  admin: { render: routeRenderers.admin },
};
