import { Settings } from "lucide-react";
import type { AgentModelOverride, AgentRuntimeAdapter, CreateAuditRunPayload } from "../../types";
import { Accordion, Button, CheckboxGroup, Dialog, Field, Input, NumberInput, SwitchField, Textarea, checkedFieldValue, fieldValue, numberFieldValue } from "../../ui";

const agentOptions = [
  { label: "Orchestrator", value: "orchestrator" },
  { label: "Code Auditor", value: "code-auditor" },
  { label: "Trace Worker", value: "source-sink-finder" },
  { label: "Validation-Judgement", value: "validator" },
  { label: "PoC Writer", value: "poc-writer" },
  { label: "PoC Verifier", value: "poc-verifier" },
];

const defaultGoal = "Run an initial security audit. Inspect the mounted source and report vulnerability candidates with file paths.";
const modelRoles = [
  { key: "orchestrator", label: "Orchestrator" },
  { key: "code-auditor", label: "Code Auditor" },
  { key: "source-sink-finder", label: "Trace Worker" },
  { key: "validator", label: "Validator" },
  { key: "judger", label: "Judger" },
  { key: "poc-writer", label: "PoC Writer" },
  { key: "poc-verifier", label: "PoC Verifier" },
];

const defaultPayload: Omit<CreateAuditRunPayload, "input_payload"> = {
  agent_name: "kimi-orchestrator",
  enabled_agents: agentOptions.map((item) => String(item.value)),
  preflight_prompt:
    "Run a practical security audit. Prioritize reachable code vulnerabilities, source-to-sink chains, concrete evidence, and per-finding markdown updates.",
  validator_rounds: 1,
  max_parallel_validators: 2,
  validator_agent_name: "kimi-validator",
  enable_validation_judgement: true,
  validation_judgement_agent_name: "kimi-validator",
  enable_feedback_loop: true,
  max_feedback_rounds: 2,
  enable_code_batch_analysis: true,
  enable_batch_internal_semgrep: true,
  enable_batch_internal_sca: true,
  max_code_audit_tasks: 8,
  max_files_per_code_audit_task: 25,
  max_parallel_code_auditors: 1,
  code_auditor_agent_name: "kimi-code-auditor",
  enable_source_sink_analysis: true,
  source_sink_finder_agent_name: "kimi-source-sink-finder",
  max_parallel_source_sink_finders: 1,
  max_source_sink_findings: 50,
  enable_validators: true,
  enable_judgement: true,
  judger_agent_name: "kimi-judger",
  max_parallel_judgers: 1,
  enable_poc_writing: true,
  poc_writer_agent_name: "kimi-poc-writer",
  max_parallel_poc_writers: 1,
  max_poc_findings: 25,
  enable_poc_verification: true,
  poc_verifier_agent_name: "kimi-poc-verifier",
  max_parallel_poc_verifiers: 1,
  enable_decompilation: true,
  decompiled_source_dir: ".dieaudit/decompiled",
  decompile_max_artifact_size_mb: 200,
  decompile_timeout_seconds: 300,
  decompile_max_artifacts: 50,
  allow_external_network: false,
  retain_runtime_on_failure: false,
  start_agent: false,
};

type Props = {
  agentRuntimes: AgentRuntimeAdapter[];
  loading: boolean;
  open: boolean;
  onCancel: () => void;
  onSubmit: (values: CreateAuditRunPayload) => void;
};

export function AuditRunConfigModal({ agentRuntimes, loading, open, onCancel, onSubmit }: Props) {
  const defaultRuntime = agentRuntimes[0];
  const runtimeId = defaultRuntime?.runtime_id || "default-agent-runtime";
  const defaultProvider = runtimeId;
  const defaultModel = defaultRuntime?.default_model_profile || "default";
  const defaultApiKeyEnv = `${runtimeId.replace(/[^a-zA-Z0-9]/g, "_").toUpperCase()}_API_KEY`;
  return (
    <Dialog open={open} onOpenChange={(nextOpen) => !nextOpen && onCancel()} title={<span className="inline-flex items-center gap-2"><Settings className="h-4 w-4" />审计任务配置</span>}>
      <form
        className="grid gap-5"
        onSubmit={(event) => {
          event.preventDefault();
          const formData = new FormData(event.currentTarget);
          const preflight = fieldValue(formData, "preflight_prompt")?.trim();
          const modelOverrides = buildModelOverrides(formData, runtimeId);
          onSubmit({
            agent_name: fieldValue(formData, "agent_name"),
            enabled_agents: formData.getAll("enabled_agents").map(String),
            preflight_prompt: preflight,
            validator_rounds: numberFieldValue(formData, "validator_rounds"),
            max_parallel_validators: numberFieldValue(formData, "max_parallel_validators"),
            validator_agent_name: fieldValue(formData, "validator_agent_name"),
            enable_validation_judgement: checkedFieldValue(formData, "enable_validation_judgement"),
            validation_judgement_agent_name: fieldValue(formData, "validation_judgement_agent_name"),
            enable_feedback_loop: checkedFieldValue(formData, "enable_feedback_loop"),
            max_feedback_rounds: numberFieldValue(formData, "max_feedback_rounds"),
            enable_code_batch_analysis: checkedFieldValue(formData, "enable_code_batch_analysis"),
            enable_batch_internal_semgrep: checkedFieldValue(formData, "enable_batch_internal_semgrep"),
            enable_batch_internal_sca: checkedFieldValue(formData, "enable_batch_internal_sca"),
            max_code_audit_tasks: numberFieldValue(formData, "max_code_audit_tasks"),
            max_files_per_code_audit_task: numberFieldValue(formData, "max_files_per_code_audit_task"),
            max_parallel_code_auditors: numberFieldValue(formData, "max_parallel_code_auditors"),
            code_auditor_agent_name: fieldValue(formData, "code_auditor_agent_name"),
            enable_source_sink_analysis: checkedFieldValue(formData, "enable_source_sink_analysis"),
            source_sink_finder_agent_name: fieldValue(formData, "source_sink_finder_agent_name"),
            max_parallel_source_sink_finders: numberFieldValue(formData, "max_parallel_source_sink_finders"),
            max_source_sink_findings: numberFieldValue(formData, "max_source_sink_findings"),
            enable_validators: checkedFieldValue(formData, "enable_validators"),
            enable_judgement: checkedFieldValue(formData, "enable_judgement"),
            judger_agent_name: fieldValue(formData, "judger_agent_name"),
            max_parallel_judgers: numberFieldValue(formData, "max_parallel_judgers"),
            enable_poc_writing: checkedFieldValue(formData, "enable_poc_writing"),
            poc_writer_agent_name: fieldValue(formData, "poc_writer_agent_name"),
            max_parallel_poc_writers: numberFieldValue(formData, "max_parallel_poc_writers"),
            max_poc_findings: numberFieldValue(formData, "max_poc_findings"),
            enable_poc_verification: checkedFieldValue(formData, "enable_poc_verification"),
            poc_verifier_agent_name: fieldValue(formData, "poc_verifier_agent_name"),
            max_parallel_poc_verifiers: numberFieldValue(formData, "max_parallel_poc_verifiers"),
            enable_decompilation: checkedFieldValue(formData, "enable_decompilation"),
            decompiled_source_dir: fieldValue(formData, "decompiled_source_dir"),
            decompile_max_artifact_size_mb: numberFieldValue(formData, "decompile_max_artifact_size_mb"),
            decompile_timeout_seconds: numberFieldValue(formData, "decompile_timeout_seconds"),
            decompile_max_artifacts: numberFieldValue(formData, "decompile_max_artifacts"),
            allow_external_network: checkedFieldValue(formData, "allow_external_network"),
            retain_runtime_on_failure: checkedFieldValue(formData, "retain_runtime_on_failure"),
            start_agent: checkedFieldValue(formData, "start_agent"),
            input_payload: { goal: preflight || defaultGoal },
            config: {
              agent_runtime: { default_runtime_id: runtimeId },
              model_overrides: modelOverrides,
            },
          });
        }}
      >
        <Field label="预引导提示词">
          <Textarea name="preflight_prompt" defaultValue={defaultPayload.preflight_prompt} rows={4} />
        </Field>

        <Accordion
          items={[
            {
              key: "agents",
              title: "Agent Swarm",
              children: (
                <div className="grid gap-4">
                  <Field label="启用 Agent">
                    <CheckboxGroup name="enabled_agents" defaultValue={defaultPayload.enabled_agents} options={agentOptions} />
                  </Field>
                  <div className="grid gap-3 md:grid-cols-2">
                    <TextField name="agent_name" label="Orchestrator 模板" />
                    <TextField name="code_auditor_agent_name" label="Code Auditor 模板" />
                    <TextField name="source_sink_finder_agent_name" label="Trace Worker 模板" />
                    <TextField name="validation_judgement_agent_name" label="Validation-Judgement 模板" />
                    <TextField name="poc_writer_agent_name" label="PoC Writer 模板" />
                    <TextField name="poc_verifier_agent_name" label="PoC Verifier 模板" />
                  </div>
                </div>
              ),
            },
            {
              key: "models",
              title: "Models",
              children: (
                <div className="grid gap-4">
                  <Field label="Runtime Adapter" hint="由 BFF runtime registry 提供；新增 runtime adapter 后会复用同一配置结构。">
                    <Input name="default_runtime_id" value={runtimeId} readOnly />
                  </Field>
                  <div className="grid gap-3">
                    {modelRoles.map((role) => (
                      <div key={role.key} className="rounded-lg border border-slate-200 bg-slate-50 p-3">
                        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                          <div className="font-medium text-slate-900">{role.label}</div>
                          <span className="text-xs text-slate-500">{role.key}</span>
                        </div>
                        <div className="grid gap-3 md:grid-cols-3">
                          <ModelInput role={role.key} field="provider" label="Provider" defaultValue={defaultProvider} />
                          <ModelInput role={role.key} field="model" label="Model" defaultValue={defaultModel} />
                          <ModelInput role={role.key} field="api_key_env" label="API key env" defaultValue={defaultApiKeyEnv} />
                          <ModelInput role={role.key} field="temperature" label="Temperature" defaultValue="0.1" type="number" step="0.1" />
                          <ModelInput role={role.key} field="max_output_tokens" label="Max tokens" defaultValue="8192" type="number" />
                          <ModelInput role={role.key} field="context_window" label="Context window" defaultValue="128000" type="number" />
                          <div className="md:col-span-3">
                            <ModelInput role={role.key} field="base_url" label="Base URL override" defaultValue="" placeholder="Optional" />
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ),
            },
            {
              key: "parallel",
              title: "并发与轮次",
              children: (
                <div className="grid gap-3 md:grid-cols-3">
                  <NumberField name="validator_rounds" label="确认轮次" min={1} max={20} />
                  <NumberField name="max_parallel_validators" label="确认并发" min={1} max={20} />
                  <NumberField name="max_parallel_code_auditors" label="Code Auditor 并发" min={1} max={20} />
                  <NumberField name="max_parallel_source_sink_finders" label="Trace Worker 并发" min={1} max={20} />
                  <NumberField name="max_feedback_rounds" label="反馈轮数" min={0} max={10} />
                  <NumberField name="max_parallel_poc_writers" label="PoC Writer 并发" min={1} max={20} />
                  <NumberField name="max_parallel_poc_verifiers" label="PoC Verifier 并发" min={1} max={20} />
                  <NumberField name="max_code_audit_tasks" label="代码分析任务数" min={1} max={100} />
                  <NumberField name="max_files_per_code_audit_task" label="每任务文件数" min={1} max={200} />
                  <NumberField name="max_source_sink_findings" label="Trace Candidate 上限" min={1} max={500} />
                  <NumberField name="max_poc_findings" label="PoC Finding 上限" min={1} max={500} />
                </div>
              ),
            },
            {
              key: "stages",
              title: "阶段开关",
              children: (
                <div className="grid gap-2 md:grid-cols-2">
                  <SwitchField name="enable_code_batch_analysis" label="代码批量分析" defaultChecked={defaultPayload.enable_code_batch_analysis} />
                  <SwitchField name="enable_batch_internal_semgrep" label="Batch 内置 Semgrep" defaultChecked={defaultPayload.enable_batch_internal_semgrep} />
                  <SwitchField name="enable_batch_internal_sca" label="Batch 内置 SCA" defaultChecked={defaultPayload.enable_batch_internal_sca} />
                  <SwitchField name="enable_validation_judgement" label="Validation-Judgement" defaultChecked={defaultPayload.enable_validation_judgement} />
                  <SwitchField name="enable_feedback_loop" label="反馈调节" defaultChecked={defaultPayload.enable_feedback_loop} />
                  <SwitchField name="enable_poc_writing" label="PoC Writer" defaultChecked={defaultPayload.enable_poc_writing} />
                  <SwitchField name="enable_poc_verification" label="PoC Verifier" defaultChecked={defaultPayload.enable_poc_verification} />
                  <SwitchField name="start_agent" label="创建后立即跑 Orchestrator" defaultChecked={defaultPayload.start_agent} />
                </div>
              ),
            },
            {
              key: "runtime",
              title: "源码准备与运行策略",
              children: (
                <div className="grid gap-4">
                  <div className="grid gap-2 md:grid-cols-3">
                    <SwitchField name="enable_decompilation" label="自动反编译" defaultChecked={defaultPayload.enable_decompilation} />
                    <SwitchField name="allow_external_network" label="允许外网" defaultChecked={defaultPayload.allow_external_network} />
                    <SwitchField name="retain_runtime_on_failure" label="失败保留运行现场" defaultChecked={defaultPayload.retain_runtime_on_failure} />
                  </div>
                  <div className="grid gap-3 md:grid-cols-2">
                    <TextField name="decompiled_source_dir" label="反编译输出目录" />
                    <NumberField name="decompile_max_artifact_size_mb" label="单包大小 MB" min={1} max={4096} />
                    <NumberField name="decompile_timeout_seconds" label="反编译超时秒数" min={1} max={7200} />
                    <NumberField name="decompile_max_artifacts" label="反编译包数量" min={1} max={500} />
                  </div>
                </div>
              ),
            },
          ]}
        />

        <p className="text-sm text-slate-500">创建后可在 Audit Runs 页面点击“一键闭环”，按上述配置执行多 Agent 审计流程。</p>
        <div className="flex justify-end gap-2">
          <Button onClick={onCancel}>取消</Button>
          <Button type="submit" variant="primary" loading={loading}>创建 AuditRun</Button>
        </div>
      </form>
    </Dialog>
  );
}

function TextField({ label, name }: { label: string; name: keyof typeof defaultPayload }) {
  return (
    <Field label={label}>
      <Input name={name} defaultValue={String(defaultPayload[name] || "")} />
    </Field>
  );
}

function NumberField({ label, max, min, name }: { label: string; max: number; min: number; name: keyof typeof defaultPayload }) {
  return (
    <Field label={label}>
      <NumberInput name={name} min={min} max={max} defaultValue={Number(defaultPayload[name] || 0)} />
    </Field>
  );
}

function ModelInput({
  defaultValue,
  field,
  label,
  placeholder,
  role,
  step,
  type = "text",
}: {
  defaultValue: string;
  field: keyof AgentModelOverride;
  label: string;
  placeholder?: string;
  role: string;
  step?: string;
  type?: string;
}) {
  return (
    <Field label={label}>
      <Input name={`model_overrides.${role}.${field}`} defaultValue={defaultValue} placeholder={placeholder} step={step} type={type} />
    </Field>
  );
}

function buildModelOverrides(formData: FormData, runtimeId: string): Record<string, AgentModelOverride> {
  const defaultApiKeyEnv = `${runtimeId.replace(/[^a-zA-Z0-9]/g, "_").toUpperCase()}_API_KEY`;
  return Object.fromEntries(
    modelRoles.map((role) => {
      const prefix = `model_overrides.${role.key}.`;
      const provider = fieldValue(formData, `${prefix}provider`) || runtimeId;
      const model = fieldValue(formData, `${prefix}model`) || "default";
      const baseUrl = fieldValue(formData, `${prefix}base_url`)?.trim();
      const override: AgentModelOverride = {
        runtime_id: runtimeId,
        provider,
        model,
        temperature: numberFieldValue(formData, `${prefix}temperature`),
        max_output_tokens: numberFieldValue(formData, `${prefix}max_output_tokens`),
        context_window: numberFieldValue(formData, `${prefix}context_window`),
        api_key_env: fieldValue(formData, `${prefix}api_key_env`) || defaultApiKeyEnv,
      };
      if (baseUrl) {
        override.base_url = baseUrl;
      }
      return [role.key, override];
    }),
  );
}
