import { Layout, Menu } from "antd";
import type { AppView } from "../navigation";

const { Sider } = Layout;

type Props = {
  activeView: AppView;
  items: Array<{ key: AppView; icon: React.ReactNode; label: string }>;
  onViewChange: (view: AppView) => void;
};

export function AppNavigation({ activeView, items, onViewChange }: Props) {
  return (
    <Sider className="app-sider" width={224} breakpoint="lg" collapsedWidth={0}>
      <Menu
        mode="inline"
        selectedKeys={[activeView]}
        onClick={({ key }) => onViewChange(key as AppView)}
        items={items}
      />
    </Sider>
  );
}
