import { Alert, Button, Card, Form, Input, InputNumber, Space, Switch } from "antd";
import type { AuditRun, SandboxCapabilities, SandboxPocFormValues, SandboxServiceFormValues } from "../../types";

type Props = {
  auditRun?: AuditRun;
  loading: boolean;
  sandboxCapabilities?: SandboxCapabilities;
  sandboxTarget?: { network: string; target_url: string };
  sandboxUnavailableReason: string;
  onRunSandboxPoc: (values: SandboxPocFormValues) => void;
  onRunSandboxTargetPoc: (values: SandboxPocFormValues) => void;
  onStartSandboxService: (values: SandboxServiceFormValues) => void;
};

export function RuntimeSandboxPanel({
  auditRun,
  loading,
  sandboxCapabilities,
  sandboxTarget,
  sandboxUnavailableReason,
  onRunSandboxPoc,
  onRunSandboxTargetPoc,
  onStartSandboxService,
}: Props) {
  const [pocForm] = Form.useForm<SandboxPocFormValues>();
  const [serviceForm] = Form.useForm<SandboxServiceFormValues>();
  const sandboxExecutionAvailable = Boolean(sandboxCapabilities?.sandbox_execution_available);

  return (
    <Space direction="vertical" size={16} className="drawer-stack">
      {!sandboxExecutionAvailable && (
        <Alert type="warning" showIcon message="Sandbox execution is unavailable" description={sandboxUnavailableReason} />
      )}
      {!auditRun && <Alert type="warning" showIcon message="Create or select an AuditRun before starting sandbox execution." />}
      {sandboxTarget && (
        <Alert
          type="info"
          showIcon
          message="Sandbox target is running"
          description={`${sandboxTarget.target_url} on ${sandboxTarget.network}`}
        />
      )}
      <div className="content-grid">
        <Card title="Target Service">
          <Form
            form={serviceForm}
            layout="vertical"
            initialValues={{
              image: "python:3.12-slim",
              service_name: "target",
              port: 8080,
              mount_workspace: true,
              retain_runtime_on_failure: true,
              startup_timeout_seconds: 30,
            }}
            onFinish={onStartSandboxService}
          >
            <Form.Item name="image" label="Image" rules={[{ required: true }]}>
              <Input placeholder="registry.example.com/app-under-test:latest" />
            </Form.Item>
            <Form.Item name="command" label="Command" rules={[{ required: true }]}>
              <Input.TextArea rows={5} placeholder={"python\n-m\nhttp.server\n8080"} />
            </Form.Item>
            <Space wrap>
              <Form.Item name="service_name" label="Service" rules={[{ required: true }]}>
                <Input />
              </Form.Item>
              <Form.Item name="port" label="Port">
                <InputNumber min={1} max={65535} />
              </Form.Item>
              <Form.Item name="startup_timeout_seconds" label="Startup Timeout">
                <InputNumber min={1} max={300} />
              </Form.Item>
            </Space>
            <Form.Item name="healthcheck_path" label="Healthcheck Path">
              <Input placeholder="/health" />
            </Form.Item>
            <Space wrap>
              <Form.Item name="mount_workspace" label="Mount Workspace" valuePropName="checked">
                <Switch />
              </Form.Item>
              <Form.Item name="retain_runtime_on_failure" label="Retain On Failure" valuePropName="checked">
                <Switch />
              </Form.Item>
            </Space>
            <Button type="primary" htmlType="submit" loading={loading} disabled={!auditRun || !sandboxExecutionAvailable}>
              Start Service
            </Button>
          </Form>
        </Card>

        <Card title="PoC Execution">
          <Form
            form={pocForm}
            layout="vertical"
            initialValues={{
              image: "python:3.12-slim",
              expected_exit_code: 0,
              mount_workspace: true,
              retain_runtime_on_failure: false,
              timeout_seconds: 120,
            }}
            onFinish={onRunSandboxPoc}
          >
            <Form.Item name="image" label="Image" rules={[{ required: true }]}>
              <Input placeholder="python:3.12-slim" />
            </Form.Item>
            <Form.Item name="command" label="Command" rules={[{ required: true }]}>
              <Input.TextArea rows={5} placeholder={"python\n-c\nprint('ok')"} />
            </Form.Item>
            <Space wrap>
              <Form.Item name="timeout_seconds" label="Timeout">
                <InputNumber min={1} max={3600} />
              </Form.Item>
              <Form.Item name="expected_exit_code" label="Expected Exit">
                <InputNumber />
              </Form.Item>
            </Space>
            <Form.Item name="target_url" label="Target URL">
              <Input placeholder={sandboxTarget?.target_url || "optional"} />
            </Form.Item>
            <Space wrap>
              <Form.Item name="mount_workspace" label="Mount Workspace" valuePropName="checked">
                <Switch />
              </Form.Item>
              <Form.Item name="retain_runtime_on_failure" label="Retain On Failure" valuePropName="checked">
                <Switch />
              </Form.Item>
            </Space>
            <Space wrap>
              <Button type="primary" htmlType="submit" loading={loading} disabled={!auditRun || !sandboxExecutionAvailable}>
                Run PoC
              </Button>
              <Button
                loading={loading}
                disabled={!auditRun || !sandboxExecutionAvailable || !sandboxTarget}
                onClick={() => pocForm.validateFields().then(onRunSandboxTargetPoc)}
              >
                Run Against Target
              </Button>
            </Space>
          </Form>
        </Card>
      </div>
    </Space>
  );
}
