import type { DashboardController } from "../hooks/useDashboardController";
import type { AppView } from "../navigation";
import { DEFAULT_VIEW } from "../navigation";
import { routeRegistry } from "./routeRegistry";

type Props = {
  activeView: AppView;
  dashboard: DashboardController;
  onViewChange: (view: AppView) => void;
};

export function AppRoutes({ activeView, dashboard, onViewChange }: Props) {
  const route = routeRegistry[activeView] || routeRegistry[DEFAULT_VIEW];
  return <>{route.render(dashboard, onViewChange)}</>;
}
