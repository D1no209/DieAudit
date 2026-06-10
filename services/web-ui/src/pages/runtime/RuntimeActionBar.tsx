import { CloudServerOutlined, DeleteOutlined, SafetyCertificateOutlined } from "@ant-design/icons";
import { Button } from "antd";

type Props = {
  loading: boolean;
  sandboxExecutionAvailable: boolean;
  sandboxTarget?: { network: string; target_url: string };
  onCleanup: () => void;
  onCleanupExpiredRuntime: () => void;
  onRunPocSmoke: () => void;
  onRunSandboxTargetPoc: () => void;
  onStartSandboxService: () => void;
};

export function RuntimeActionBar({
  loading,
  sandboxExecutionAvailable,
  sandboxTarget,
  onCleanup,
  onCleanupExpiredRuntime,
  onRunPocSmoke,
  onRunSandboxTargetPoc,
  onStartSandboxService,
}: Props) {
  return (
    <div className="action-bar">
      <Button icon={<CloudServerOutlined />} loading={loading} disabled={!sandboxExecutionAvailable} onClick={onStartSandboxService}>
        Sandbox Service
      </Button>
      <Button
        icon={<SafetyCertificateOutlined />}
        loading={loading}
        disabled={!sandboxExecutionAvailable || !sandboxTarget}
        onClick={onRunSandboxTargetPoc}
      >
        Target PoC
      </Button>
      <Button icon={<SafetyCertificateOutlined />} loading={loading} disabled={!sandboxExecutionAvailable} onClick={onRunPocSmoke}>
        PoC Smoke
      </Button>
      <Button icon={<DeleteOutlined />} loading={loading} onClick={onCleanupExpiredRuntime}>
        清理过期运行时
      </Button>
      <Button danger icon={<DeleteOutlined />} loading={loading} onClick={onCleanup}>
        清理当前运行时
      </Button>
    </div>
  );
}
