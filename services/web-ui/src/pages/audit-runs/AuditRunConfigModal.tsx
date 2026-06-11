import { CheckSquareOutlined, SettingOutlined } from "@ant-design/icons";
import { Checkbox, Collapse, Form, Input, InputNumber, Modal, Select, Space, Switch, Typography } from "antd";
import type { CreateAuditRunPayload } from "../../types";

const agentOptions = [
  { label: "Orchestrator", value: "orchestrator" },
  { label: "Code Auditor", value: "code-auditor" },
  { label: "Source-Sink Finder", value: "source-sink-finder" },
  { label: "Validator", value: "validator" },
  { label: "Judger", value: "judger" },
  { label: "PoC Writer", value: "poc-writer" },
  { label: "PoC Verifier", value: "poc-verifier" },
];

const defaultGoal = "Run an initial security audit. Inspect the mounted source and report vulnerability candidates with file paths.";

const defaultPayload: Omit<CreateAuditRunPayload, "input_payload"> = {
  agent_name: "opencode-orchestrator",
  enabled_agents: agentOptions.map((item) => String(item.value)),
  preflight_prompt:
    "Run a practical security audit. Prioritize reachable code vulnerabilities, source-to-sink chains, concrete evidence, and per-finding markdown updates.",
  validator_rounds: 1,
  max_parallel_validators: 2,
  validator_agent_name: "opencode-validator",
  enable_code_batch_analysis: true,
  max_code_audit_tasks: 8,
  max_files_per_code_audit_task: 25,
  max_parallel_code_auditors: 2,
  code_auditor_agent_name: "opencode-code-auditor",
  enable_source_sink_analysis: true,
  source_sink_finder_agent_name: "opencode-source-sink-finder",
  max_parallel_source_sink_finders: 2,
  max_source_sink_findings: 50,
  enable_validators: true,
  enable_judgement: true,
  judger_agent_name: "opencode-judger",
  max_parallel_judgers: 2,
  enable_poc_writing: true,
  poc_writer_agent_name: "opencode-poc-writer",
  max_parallel_poc_writers: 2,
  max_poc_findings: 25,
  enable_poc_verification: true,
  poc_verifier_agent_name: "opencode-poc-verifier",
  max_parallel_poc_verifiers: 2,
  enable_joern: true,
  joern_required: true,
  allow_joern_unavailable: false,
  joern_timeout_seconds: 900,
  joern_query_packs: ["entrypoints", "authz", "injection", "file-io", "network", "secrets"],
  allow_external_network: false,
  retain_runtime_on_failure: false,
  start_agent: false,
};

type Props = {
  loading: boolean;
  open: boolean;
  onCancel: () => void;
  onSubmit: (values: CreateAuditRunPayload) => void;
};

export function AuditRunConfigModal({ loading, open, onCancel, onSubmit }: Props) {
  const [form] = Form.useForm<CreateAuditRunPayload>();

  function submit() {
    form
      .validateFields()
      .then((values) => {
        const preflight = values.preflight_prompt?.trim();
        onSubmit({
          ...values,
          preflight_prompt: preflight,
          input_payload: {
            goal: preflight || defaultGoal,
          },
        });
      })
      .catch(() => undefined);
  }

  return (
    <Modal
      title={
        <Space>
          <SettingOutlined />
          <span>审计任务配置</span>
        </Space>
      }
      open={open}
      width={900}
      confirmLoading={loading}
      okText="创建 AuditRun"
      cancelText="取消"
      onCancel={onCancel}
      onOk={submit}
      afterOpenChange={(visible) => {
        if (visible) {
          form.setFieldsValue(defaultPayload);
        }
      }}
    >
      <Form form={form} layout="vertical" initialValues={defaultPayload}>
        <Form.Item name="preflight_prompt" label="预引导提示词">
          <Input.TextArea rows={4} />
        </Form.Item>

        <Collapse
          defaultActiveKey={["agents", "parallel"]}
          items={[
            {
              key: "agents",
              label: "Agent Swarm",
              children: (
                <>
                  <Form.Item name="enabled_agents" label="启用 Agent">
                    <Checkbox.Group options={agentOptions} />
                  </Form.Item>
                  <div className="form-grid">
                    <Form.Item name="agent_name" label="Orchestrator 模板">
                      <Input />
                    </Form.Item>
                    <Form.Item name="code_auditor_agent_name" label="Code Auditor 模板">
                      <Input />
                    </Form.Item>
                    <Form.Item name="source_sink_finder_agent_name" label="Source-Sink Finder 模板">
                      <Input />
                    </Form.Item>
                    <Form.Item name="validator_agent_name" label="Validator 模板">
                      <Input />
                    </Form.Item>
                    <Form.Item name="judger_agent_name" label="Judger 模板">
                      <Input />
                    </Form.Item>
                    <Form.Item name="poc_writer_agent_name" label="PoC Writer 模板">
                      <Input />
                    </Form.Item>
                    <Form.Item name="poc_verifier_agent_name" label="PoC Verifier 模板">
                      <Input />
                    </Form.Item>
                  </div>
                </>
              ),
            },
            {
              key: "parallel",
              label: "并发与轮次",
              children: (
                <div className="form-grid">
                  <Form.Item name="validator_rounds" label="Validator 轮次">
                    <InputNumber min={1} max={20} />
                  </Form.Item>
                  <Form.Item name="max_parallel_validators" label="Validator 并发">
                    <InputNumber min={1} max={20} />
                  </Form.Item>
                  <Form.Item name="max_parallel_code_auditors" label="Code Auditor 并发">
                    <InputNumber min={1} max={20} />
                  </Form.Item>
                  <Form.Item name="max_parallel_source_sink_finders" label="Source-Sink 并发">
                    <InputNumber min={1} max={20} />
                  </Form.Item>
                  <Form.Item name="max_parallel_judgers" label="Judger 并发">
                    <InputNumber min={1} max={20} />
                  </Form.Item>
                  <Form.Item name="max_parallel_poc_writers" label="PoC Writer 并发">
                    <InputNumber min={1} max={20} />
                  </Form.Item>
                  <Form.Item name="max_parallel_poc_verifiers" label="PoC Verifier 并发">
                    <InputNumber min={1} max={20} />
                  </Form.Item>
                  <Form.Item name="max_code_audit_tasks" label="代码分析任务数">
                    <InputNumber min={1} max={100} />
                  </Form.Item>
                  <Form.Item name="max_files_per_code_audit_task" label="每任务文件数">
                    <InputNumber min={1} max={200} />
                  </Form.Item>
                  <Form.Item name="max_source_sink_findings" label="Source-Sink Finding 上限">
                    <InputNumber min={1} max={500} />
                  </Form.Item>
                  <Form.Item name="max_poc_findings" label="PoC Finding 上限">
                    <InputNumber min={1} max={500} />
                  </Form.Item>
                </div>
              ),
            },
            {
              key: "stages",
              label: "阶段开关",
              children: (
                <div className="switch-grid">
                  <Form.Item name="enable_code_batch_analysis" label="代码批量分析" valuePropName="checked">
                    <Switch />
                  </Form.Item>
                  <Form.Item name="enable_source_sink_analysis" label="Source-Sink 链路分析" valuePropName="checked">
                    <Switch />
                  </Form.Item>
                  <Form.Item name="enable_validators" label="Validator" valuePropName="checked">
                    <Switch />
                  </Form.Item>
                  <Form.Item name="enable_judgement" label="Judger" valuePropName="checked">
                    <Switch />
                  </Form.Item>
                  <Form.Item name="enable_poc_writing" label="PoC Writer" valuePropName="checked">
                    <Switch />
                  </Form.Item>
                  <Form.Item name="enable_poc_verification" label="PoC Verifier" valuePropName="checked">
                    <Switch />
                  </Form.Item>
                  <Form.Item name="start_agent" label="创建后立即跑 Orchestrator" valuePropName="checked">
                    <Switch />
                  </Form.Item>
                </div>
              ),
            },
            {
              key: "joern",
              label: "Joern 与运行策略",
              children: (
                <>
                  <div className="switch-grid">
                    <Form.Item name="enable_joern" label="启用 Joern CPG" valuePropName="checked">
                      <Switch />
                    </Form.Item>
                    <Form.Item name="joern_required" label="Joern 必需" valuePropName="checked">
                      <Switch />
                    </Form.Item>
                    <Form.Item name="allow_joern_unavailable" label="允许 Joern 降级" valuePropName="checked">
                      <Switch />
                    </Form.Item>
                    <Form.Item name="allow_external_network" label="允许外网" valuePropName="checked">
                      <Switch />
                    </Form.Item>
                    <Form.Item name="retain_runtime_on_failure" label="失败保留运行现场" valuePropName="checked">
                      <Switch />
                    </Form.Item>
                  </div>
                  <div className="form-grid">
                    <Form.Item name="joern_timeout_seconds" label="Joern 超时秒数">
                      <InputNumber min={30} max={7200} />
                    </Form.Item>
                    <Form.Item name="joern_query_packs" label="Joern Query Packs">
                      <Select mode="tags" tokenSeparators={[","]} />
                    </Form.Item>
                  </div>
                </>
              ),
            },
          ]}
        />

        <Typography.Paragraph className="muted-note">
          <CheckSquareOutlined /> 创建后可在 Audit Runs 页面点击“一键闭环”，按上述配置执行多 Agent 审计流程。
        </Typography.Paragraph>
      </Form>
    </Modal>
  );
}
