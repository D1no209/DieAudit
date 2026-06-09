import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  ApiOutlined,
  BugOutlined,
  CloudServerOutlined,
  DeleteOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
} from "@ant-design/icons";
import {
  Alert,
  Button,
  Card,
  ConfigProvider,
  Flex,
  Layout,
  Space,
  Statistic,
  Table,
  Tag,
  Typography,
  theme,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import "antd/dist/reset.css";
import "./styles.css";

const { Header, Content } = Layout;
const { Title, Text, Paragraph } = Typography;

type ContainerRow = {
  Id: string;
  Image: string;
  Names: string[];
  State: string;
  Status: string;
  Labels: Record<string, string>;
};

async function readJson(path: string, options?: RequestInit) {
  const response = await fetch(path, options);
  const text = await response.text();
  if (!response.ok) {
    throw new Error(text || response.statusText);
  }
  return text ? JSON.parse(text) : {};
}

function App() {
  const [apiHealth, setApiHealth] = useState<any>();
  const [dockerHealth, setDockerHealth] = useState<any>();
  const [containers, setContainers] = useState<ContainerRow[]>([]);
  const [demoResult, setDemoResult] = useState<any>();
  const [error, setError] = useState<string>();
  const [loading, setLoading] = useState(false);

  async function refresh() {
    setError(undefined);
    try {
      const [api, docker, rows] = await Promise.all([
        readJson("/api/health"),
        readJson("/gateway/runtime/docker/health"),
        readJson("/gateway/audit-runs/demo-run/containers"),
      ]);
      setApiHealth(api);
      setDockerHealth(docker);
      setContainers(rows);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function startDemo() {
    setLoading(true);
    setError(undefined);
    try {
      const result = await readJson("/gateway/audit-runs/demo-run/demo", { method: "POST" });
      setDemoResult(result);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  async function cleanup() {
    setLoading(true);
    setError(undefined);
    try {
      setDemoResult(await readJson("/gateway/audit-runs/demo-run/cleanup", { method: "POST" }));
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  const columns: ColumnsType<ContainerRow> = [
    {
      title: "Role",
      dataIndex: ["Labels", "dieaudit.role"],
      render: (value: string) => <Tag color={value === "agent" ? "blue" : "green"}>{value || "unknown"}</Tag>,
    },
    {
      title: "Name",
      dataIndex: "Names",
      render: (names: string[]) => names?.[0]?.replace("/", "") || "-",
    },
    { title: "Image", dataIndex: "Image" },
    { title: "State", dataIndex: "State" },
    { title: "Status", dataIndex: "Status" },
  ];

  return (
    <ConfigProvider theme={{ algorithm: theme.defaultAlgorithm }}>
      <Layout className="app-shell">
        <Header className="app-header">
          <Flex align="center" justify="space-between" gap={16}>
            <Space>
              <BugOutlined className="brand-icon" />
              <div>
                <Title level={3} className="brand-title">DieAudit</Title>
                <Text className="brand-subtitle">多 Agent 代码审计运行台</Text>
              </div>
            </Space>
            <Space wrap>
              <Button icon={<ReloadOutlined />} onClick={refresh}>刷新</Button>
              <Button type="primary" icon={<PlayCircleOutlined />} loading={loading} onClick={startDemo}>启动 Demo Agent</Button>
              <Button danger icon={<DeleteOutlined />} loading={loading} onClick={cleanup}>清理 Demo</Button>
            </Space>
          </Flex>
        </Header>
        <Content className="app-content">
          {error && <Alert type="error" showIcon message="运行错误" description={error} className="section" />}
          <div className="stats-grid section">
            <Card>
              <Statistic
                title="Web API"
                value={apiHealth?.ok ? "Healthy" : "Unknown"}
                prefix={<ApiOutlined />}
              />
            </Card>
            <Card>
              <Statistic
                title="Docker Runtime"
                value={dockerHealth?.ok ? "Ready" : "Unknown"}
                prefix={<CloudServerOutlined />}
              />
            </Card>
            <Card>
              <Statistic title="Demo Containers" value={containers.length} prefix={<BugOutlined />} />
            </Card>
          </div>
          <Card title="Demo AuditRun Containers" className="section">
            <Table rowKey="Id" size="middle" columns={columns} dataSource={containers} pagination={false} />
          </Card>
          <Card title="Last Runtime Response" className="section">
            <Paragraph>
              <pre>{JSON.stringify(demoResult || { hint: "Click Start Demo Agent to launch mock Agent and MCP sidecars." }, null, 2)}</pre>
            </Paragraph>
          </Card>
        </Content>
      </Layout>
    </ConfigProvider>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
