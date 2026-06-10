import { BugOutlined, ReloadOutlined } from "@ant-design/icons";
import { Button, Flex, Input, Layout, Menu, Space, Typography } from "antd";
import type { AppView } from "../navigation";
import { API_KEY_HEADER } from "../api";

const { Header } = Layout;
const { Title, Text } = Typography;

type Props = {
  activeView: AppView;
  apiKey: string;
  authHeaderName?: string;
  navigationItems: Array<{ key: AppView; icon: React.ReactNode; label: string }>;
  onApiKeyChange: (value: string) => void;
  onRefresh: () => void;
  onSaveApiKey: () => void;
  onViewChange: (view: AppView) => void;
};

export function AppHeader({
  activeView,
  apiKey,
  authHeaderName,
  navigationItems,
  onApiKeyChange,
  onRefresh,
  onSaveApiKey,
  onViewChange,
}: Props) {
  return (
    <Header className="app-header">
      <Flex className="header-main-row" align="center" justify="space-between" gap={16}>
        <Space>
          <BugOutlined className="brand-icon" />
          <div>
            <Title level={3} className="brand-title">DieAudit</Title>
            <Text className="brand-subtitle">多 Agent 代码审计运行台</Text>
          </div>
        </Space>
        <Space wrap className="header-actions">
          <Input.Password
            className="api-key-input"
            placeholder={authHeaderName || API_KEY_HEADER}
            value={apiKey}
            onChange={(event) => onApiKeyChange(event.target.value)}
            onPressEnter={onSaveApiKey}
          />
          <Button onClick={onSaveApiKey}>保存 Key</Button>
          <Button icon={<ReloadOutlined />} onClick={onRefresh}>刷新</Button>
        </Space>
      </Flex>
      <Menu
        className="mobile-nav"
        mode="horizontal"
        selectedKeys={[activeView]}
        onClick={({ key }) => onViewChange(key as AppView)}
        items={navigationItems}
      />
    </Header>
  );
}
