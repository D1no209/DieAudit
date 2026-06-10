import { Layout, Menu } from "antd";
import type { AppView, NavigationGroup } from "../navigation";

const { Sider } = Layout;

type Props = {
  activeView: AppView;
  groups: NavigationGroup[];
  onViewChange: (view: AppView) => void;
};

export function AppNavigation({ activeView, groups, onViewChange }: Props) {
  return (
    <Sider className="app-sider" width={224} breakpoint="lg" collapsedWidth={0}>
      <Menu
        mode="inline"
        selectedKeys={[activeView]}
        onClick={({ key }) => onViewChange(key as AppView)}
        items={groups.map((group) => ({
          key: group.key,
          label: group.label,
          type: "group",
          children: group.items,
        }))}
      />
    </Sider>
  );
}
