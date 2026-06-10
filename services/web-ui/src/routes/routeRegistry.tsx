import type { ReactNode } from "react";
import type { DashboardController } from "../hooks/useDashboardController";
import type { AppView } from "../navigation";
import { routeRenderers } from "./routeRenderers";

type RouteDefinition = {
  render: (dashboard: DashboardController) => ReactNode;
};

export const routeRegistry: Record<AppView, RouteDefinition> = {
  overview: { render: routeRenderers.overview },
  projects: { render: routeRenderers.projects },
  "audit-runs": { render: routeRenderers["audit-runs"] },
  "agent-runs": { render: routeRenderers["agent-runs"] },
  findings: { render: routeRenderers.findings },
  dependencies: { render: routeRenderers.dependencies },
  reports: { render: routeRenderers.reports },
  runtime: { render: routeRenderers.runtime },
  knowledge: { render: routeRenderers.knowledge },
  admin: { render: routeRenderers.admin },
};
