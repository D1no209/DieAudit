import {
  ApiOutlined,
  BugOutlined,
  CloudServerOutlined,
  FolderOpenOutlined,
  SafetyCertificateOutlined,
} from "@ant-design/icons";
import { Card, Statistic, Typography } from "antd";
import type {
  AuthStatus,
  ManagedRuntime,
  RuntimeReadiness,
  SandboxCapabilities,
} from "../types";
import { PageHeader } from "../components/PageHeader";

const { Text } = Typography;

type Props = {
  apiHealth?: any;
  authStatus?: AuthStatus;
  dockerHealth?: any;
  findingsCount: number;
  managedRuntime?: ManagedRuntime;
  projectsCount: number;
  runtimeReadiness?: RuntimeReadiness;
  sandboxCapabilities?: SandboxCapabilities;
};

export function OverviewPage({
  apiHealth,
  authStatus,
  dockerHealth,
  findingsCount,
  managedRuntime,
  projectsCount,
  runtimeReadiness,
  sandboxCapabilities,
}: Props) {
  const firstReadinessFailure = runtimeReadiness?.checks?.find((item) => item.status === "fail");

  return (
    <>
      <PageHeader title="Overview" />
      <div className="stats-grid section">
        <Card><Statistic title="Web API" value={apiHealth?.ok ? "Healthy" : "Unknown"} prefix={<ApiOutlined />} /></Card>
        <Card>
          <Statistic title="API Auth" value={authStatus?.enabled ? "Enabled" : "Disabled"} prefix={<SafetyCertificateOutlined />} />
          {!authStatus?.enabled && <Text type="danger">Set DIEAUDIT_API_KEY before production use.</Text>}
        </Card>
        <Card>
          <Statistic
            title="Production Readiness"
            value={runtimeReadiness?.ok ? "Ready" : "Not Ready"}
            prefix={<SafetyCertificateOutlined />}
          />
          <Text type={runtimeReadiness?.ok ? "success" : "danger"}>
            fail {runtimeReadiness?.summary?.fail ?? "-"} / warn {runtimeReadiness?.summary?.warn ?? "-"} / pass {runtimeReadiness?.summary?.pass ?? "-"}
          </Text>
          {!runtimeReadiness?.ok && firstReadinessFailure && (
            <Text type="secondary">{firstReadinessFailure.title}</Text>
          )}
        </Card>
        <Card><Statistic title="Docker Runtime" value={dockerHealth?.ok ? "Ready" : "Unknown"} prefix={<CloudServerOutlined />} /></Card>
        <Card><Statistic title="Projects" value={projectsCount} prefix={<FolderOpenOutlined />} /></Card>
        <Card><Statistic title="Findings" value={findingsCount} prefix={<BugOutlined />} /></Card>
        <Card><Statistic title="Runtime Containers" value={managedRuntime?.summary?.container_count ?? 0} prefix={<CloudServerOutlined />} /></Card>
        <Card>
          <Statistic
            title={`Sandbox ${sandboxCapabilities?.requested_runtime || ""}`}
            value={sandboxCapabilities?.sandbox_execution_available ? "Ready" : "Unavailable"}
            prefix={<SafetyCertificateOutlined />}
          />
          {sandboxCapabilities?.requested_runtime === "runc" && !sandboxCapabilities?.strong_isolation_available && (
            <Text type={sandboxCapabilities?.allow_runc_sandbox ? "warning" : "danger"}>
              {sandboxCapabilities?.allow_runc_sandbox ? "Weak runc isolation enabled" : "Strong isolation unavailable"}
            </Text>
          )}
          {sandboxCapabilities?.warnings?.[0] && <Text type="secondary">{sandboxCapabilities.warnings[0]}</Text>}
        </Card>
      </div>
    </>
  );
}
