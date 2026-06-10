import type { DashboardController } from "../hooks/useDashboardController";
import type { AppView } from "../navigation";
import { DEFAULT_VIEW } from "../navigation";
import { routeRegistry } from "./routeRegistry";

type Props = {
  activeView: AppView;
  dashboard: DashboardController;
};

export function AppRoutes({ activeView, dashboard }: Props) {
  const route = routeRegistry[activeView] || routeRegistry[DEFAULT_VIEW];
  return <>{route.render(dashboard)}</>;
}
