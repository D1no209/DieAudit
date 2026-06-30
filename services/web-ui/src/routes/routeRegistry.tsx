import type { ReactNode } from "react";
import type { DashboardController } from "../hooks/useDashboardController";
import type { AppView } from "../navigation";
import { routeRenderers } from "./routeRenderers";

type RouteDefinition = {
  render: (dashboard: DashboardController, onViewChange: (view: AppView) => void) => ReactNode;
};

export const routeRegistry: Record<AppView, RouteDefinition> = {
  projects: { render: routeRenderers.projects },
  "project-overview": { render: routeRenderers.projects },
  "project-audit-runs": { render: routeRenderers["project-audit-runs"] },
  "project-agents": { render: routeRenderers["project-agents"] },
  "project-messages": { render: routeRenderers["project-messages"] },
  "project-findings": { render: routeRenderers["project-findings"] },
  "project-finding-review": { render: routeRenderers["project-finding-review"] },
  "project-dependencies": { render: routeRenderers["project-dependencies"] },
  "project-whiteboard": { render: routeRenderers["project-whiteboard"] },
  "project-swarm": { render: routeRenderers["project-swarm"] },
  "project-reports": { render: routeRenderers["project-reports"] },
  runtime: { render: routeRenderers.runtime },
  "runtime-readiness": { render: routeRenderers["runtime-readiness"] },
  "runtime-containers": { render: routeRenderers["runtime-containers"] },
  "runtime-sandbox": { render: routeRenderers["runtime-sandbox"] },
  knowledge: { render: routeRenderers.knowledge },
  admin: { render: routeRenderers.admin },
};
