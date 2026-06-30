import { useState } from "react";
import { CheckCircle2, Gauge, Microscope, Settings, ShieldCheck } from "lucide-react";
import type { AgentModelOverride, AgentRuntimeAdapter, CreateAuditRunPayload } from "../../types";
import { Accordion, Badge, Button, Dialog, Field, Input, NumberInput, SwitchField, Tabs, Textarea, checkedFieldValue, fieldValue, numberFieldValue } from "../../ui";
import { cn } from "../../ui/utils";

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

const pipelineStages = [
  { key: "snapshot-ready", label: "Snapshot", locked: true },
  { key: "structure-discovery", label: "Structure", locked: true },
  { key: "agent-audit", label: "Orchestrator", locked: true },
  { key: "code-analysis", label: "Code Analysis", field: "enable_code_batch_analysis" },
  { key: "value-triage", label: "Value Triage", locked: true },
  { key: "whiteboard-swarm", label: "Whiteboard Swarm", field: "enable_whiteboard_swarm" },
  { key: "validation-judgement", label: "Validation", field: "enable_validation_judgement" },
  { key: "feedback-loop", label: "Feedback", field: "enable_feedback_loop" },
  { key: "poc-writing", label: "PoC Writing", field: "enable_poc_writing" },
  { key: "poc-verification", label: "PoC Verification", field: "enable_poc_verification" },
  { key: "report", label: "Report", locked: true },
  { key: "runtime-cleanup", label: "Cleanup", locked: true },
] as const;

type LocalDefaults = Omit<CreateAuditRunPayload, "input_payload"> & {
  enable_whiteboard_swarm?: boolean;
};

const presets = {
  deep: {
    label: "深度审计",
    description: "完整闭环，适合默认生产审计。",
    icon: ShieldCheck,
    values: {
      enable_code_batch_analysis: true,
      enable_batch_internal_semgrep: true,
      enable_batch_internal_sca: true,
      enable_whiteboard_swarm: true,
      enable_validation_judgement: true,
      enable_feedback_loop: true,
      enable_poc_writing: true,
      enable_poc_verification: true,
      max_parallel_code_auditors: 1,
      validator_rounds: 1,
      max_parallel_validators: 2,
    },
  },
  quick: {
    label: "快速审计",
    description: "较少 Agent 和 PoC 工作，先拿候选结果。",
    icon: Gauge,
    values: {
      enable_code_batch_analysis: true,
      enable_batch_internal_semgrep: true,
      enable_batch_internal_sca: true,
      enable_whiteboard_swarm: false,
      enable_validation_judgement: true,
      enable_feedback_loop: false,
      enable_poc_writing: false,
      enable_poc_verification: false,
      max_parallel_code_auditors: 1,
      validator_rounds: 1,
      max_parallel_validators: 1,
    },
  },
  poc: {
    label: "PoC 验证",
    description: "保留验证和 PoC 阶段，适合已有候选漏洞。",
    icon: Microscope,
    values: {
      enable_code_batch_analysis: false,
      enable_batch_internal_semgrep: false,
      enable_batch_internal_sca: false,
      enable_whiteboard_swarm: true,
      enable_validation_judgement: true,
      enable_feedback_loop: true,
      enable_poc_writing: true,
      enable_poc_verification: true,
      max_parallel_code_auditors: 1,
      validator_rounds: 1,
      max_parallel_validators: 2,
    },
  },
  custom: {
    label: "自定义",
    description: "展开所有 Agent、模型和运行参数。",
    icon: Settings,
    values: {},
  },
} as const;

type PresetKey = keyof typeof presets;

const defaultPayload: LocalDefaults = {
  agent_name: "kimi-orchestrator",
  enabled_agents: ["orchestrator", "code-auditor", "validator", "poc-writer", "poc-verifier"],
  preflight_prompt:
    "Run a practical security audit. Prioritize reachable code vulnerabilities, concrete evidence, Whiteboard Swarm coordination, and per-finding markdown updates.",
  validator_rounds: 1,
  max_parallel_validators: 2,
  validator_agent_name: "kimi-validator",
  enable_validation_judgement: true,
  validation_judgement_agent_name: "kimi-validator",
  enable_feedback_loop: true,
  enable_whiteboard_swarm: true,
  max_feedback_rounds: 2,
  enable_code_batch_analysis: true,
  enable_batch_internal_semgrep: true,
  enable_batch_internal_sca: true,
  max_code_audit_tasks: 8,
  max_files_per_code_audit_task: 25,
  max_parallel_code_auditors: 1,
  code_auditor_agent_name: "kimi-code-auditor",
  enable_source_sink_analysis: false,
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
  const [preset, setPreset] = useState<PresetKey>("deep");
  const defaultRuntime = agentRuntimes[0];
  const runtimeId = defaultRuntime?.runtime_id || "default-agent-runtime";
  const defaultProvider = runtimeId;
  const defaultModel = defaultRuntime?.default_model_profile || "default";
  const defaultApiKeyEnv = `${runtimeId.replace(/[^a-zA-Z0-9]/g, "_").toUpperCase()}_API_KEY`;
  const presetValues = presets[preset].values;
  const defaults = { ...defaultPayload, ...presetValues };
  const customMode = preset === "custom";

  return (
    <Dialog open={open} onOpenChange={(nextOpen) => !nextOpen && onCancel()} title={<span className="inline-flex items-center gap-2"><Settings className="h-4 w-4" />审计任务配置</span>}>
      <form
        className="grid gap-5"
        onSubmit={(event) => {
          event.preventDefault();
          const formData = new FormData(event.currentTarget);
          const preflight = fieldValue(formData, "preflight_prompt")?.trim();
          const modelOverrides = buildModelOverrides(formData, runtimeId);
          const whiteboardSwarm = {
            trace_worker: {
              enabled: checkedFieldValue(formData, "trace_worker_enabled"),
              agent_name: fieldValue(formData, "source_sink_finder_agent_name") || defaultPayload.source_sink_finder_agent_name,
              max_parallel: numberFieldValue(formData, "max_parallel_source_sink_finders"),
              max_findings: numberFieldValue(formData, "max_source_sink_findings"),
            },
          };
          const enableWhiteboardSwarm = checkedFieldValue(formData, "enable_whiteboard_swarm");
          const enablePocWriting = checkedFieldValue(formData, "enable_poc_writing");
          const enablePocVerification = checkedFieldValue(formData, "enable_poc_verification");
          const enabledAgents = buildEnabledAgents({
            codeAnalysis: checkedFieldValue(formData, "enable_code_batch_analysis"),
            validation: checkedFieldValue(formData, "enable_validation_judgement"),
            pocWriting: enablePocWriting,
            pocVerification: enablePocVerification,
          });
          onSubmit({
            agent_name: fieldValue(formData, "agent_name"),
            enabled_agents: enabledAgents,
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
            enable_source_sink_analysis: false,
            source_sink_finder_agent_name: fieldValue(formData, "source_sink_finder_agent_name"),
            max_parallel_source_sink_finders: numberFieldValue(formData, "max_parallel_source_sink_finders"),
            max_source_sink_findings: numberFieldValue(formData, "max_source_sink_findings"),
            enable_validators: checkedFieldValue(formData, "enable_validation_judgement"),
            enable_judgement: false,
            judger_agent_name: fieldValue(formData, "judger_agent_name"),
            max_parallel_judgers: numberFieldValue(formData, "max_parallel_judgers"),
            enable_poc_writing: enablePocWriting,
            poc_writer_agent_name: fieldValue(formData, "poc_writer_agent_name"),
            max_parallel_poc_writers: numberFieldValue(formData, "max_parallel_poc_writers"),
            max_poc_findings: numberFieldValue(formData, "max_poc_findings"),
            enable_poc_verification: enablePocVerification,
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
              preset,
              enable_whiteboard_swarm: enableWhiteboardSwarm,
              agent_runtime: { default_runtime_id: runtimeId },
              model_overrides: modelOverrides,
              whiteboard_swarm: whiteboardSwarm,
            },
          });
        }}
      >
        <Tabs
          defaultValue="preset"
          items={[
            {
              key: "preset",
              label: "Preset",
              children: (
                <div className="grid gap-4">
                  <div className="grid gap-3 md:grid-cols-2">
                    {(Object.keys(presets) as PresetKey[]).map((key) => {
                      const option = presets[key];
                      const Icon = option.icon;
                      return (
                        <button
                          key={key}
                          type="button"
                          onClick={() => setPreset(key)}
                          className={cn(
                            "flex min-h-28 items-start gap-3 rounded-lg border p-4 text-left transition hover:border-blue-300 hover:bg-blue-50/40",
                            preset === key ? "border-blue-600 bg-blue-50 ring-2 ring-blue-100" : "border-slate-200 bg-white",
                          )}
                        >
                          <Icon className="mt-0.5 h-5 w-5 text-blue-700" />
                          <span className="grid gap-1">
                            <span className="font-semibold text-slate-950">{option.label}</span>
                            <span className="text-sm leading-5 text-slate-600">{option.description}</span>
                          </span>
                        </button>
                      );
                    })}
                  </div>
                  <Field label="预引导提示词">
                    <Textarea name="preflight_prompt" defaultValue={defaults.preflight_prompt} rows={4} />
                  </Field>
                </div>
              ),
            },
            {
              key: "stages",
              label: "Stages",
              children: (
                <div className="grid gap-4">
                  <div className="grid gap-2 md:grid-cols-2">
                    {pipelineStages.map((stage, index) => (
                      <div key={stage.key} className="flex items-center gap-3 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
                        <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-slate-300 bg-white text-xs font-semibold text-slate-600">
                          {index + 1}
                        </span>
                        <div className="min-w-0 flex-1">
                          <div className="truncate text-sm font-medium text-slate-900">{stage.label}</div>
                          <div className="truncate text-xs text-slate-500">{stage.key}</div>
                        </div>
                        {"locked" in stage && stage.locked ? (
                          <Badge>required</Badge>
                        ) : (
                          <SwitchField
                            name={"field" in stage ? stage.field : ""}
                            label="启用"
                            defaultChecked={Boolean("field" in stage ? defaults[stage.field as keyof typeof defaults] : false)}
                          />
                        )}
                      </div>
                    ))}
                  </div>
                  <div className="grid gap-2 md:grid-cols-2">
                    <SwitchField name="enable_batch_internal_semgrep" label="Code Analysis 内置 Semgrep" defaultChecked={defaults.enable_batch_internal_semgrep} />
                    <SwitchField name="enable_batch_internal_sca" label="Code Analysis 内置 SCA" defaultChecked={defaults.enable_batch_internal_sca} />
                    <SwitchField name="start_agent" label="创建后立即跑 Orchestrator" defaultChecked={defaults.start_agent} />
                  </div>
                </div>
              ),
            },
            {
              key: "runtime",
              label: "Runtime",
              children: (
                <div className="grid gap-4">
                  <div className="grid gap-2 md:grid-cols-3">
                    <SwitchField name="enable_decompilation" label="自动反编译" defaultChecked={defaults.enable_decompilation} />
                    <SwitchField name="allow_external_network" label="允许 Agent 外网" defaultChecked={defaults.allow_external_network} />
                    <SwitchField name="retain_runtime_on_failure" label="失败保留运行现场" defaultChecked={defaults.retain_runtime_on_failure} />
                  </div>
                  <div className="grid gap-3 md:grid-cols-2">
                    <TextField defaults={defaults} name="decompiled_source_dir" label="反编译输出目录" />
                    <NumberField defaults={defaults} name="decompile_max_artifact_size_mb" label="单包大小 MB" min={1} max={4096} />
                    <NumberField defaults={defaults} name="decompile_timeout_seconds" label="反编译超时秒数" min={1} max={7200} />
                    <NumberField defaults={defaults} name="decompile_max_artifacts" label="反编译包数量" min={1} max={500} />
                  </div>
                </div>
              ),
            },
            {
              key: "advanced",
              label: "Advanced",
              children: (
                <Accordion
                  items={[
                    {
                      key: "agents",
                      title: "Agent templates",
                      children: (
                        <div className="grid gap-3 md:grid-cols-2">
                          <TextField defaults={defaults} name="agent_name" label="Orchestrator 模板" />
                          <TextField defaults={defaults} name="code_auditor_agent_name" label="Code Auditor 模板" />
                          <TextField defaults={defaults} name="source_sink_finder_agent_name" label="Trace Worker 模板" />
                          <TextField defaults={defaults} name="validation_judgement_agent_name" label="Validation-Judgement 模板" />
                          <TextField defaults={defaults} name="poc_writer_agent_name" label="PoC Writer 模板" />
                          <TextField defaults={defaults} name="poc_verifier_agent_name" label="PoC Verifier 模板" />
                        </div>
                      ),
                    },
                    {
                      key: "trace-worker",
                      title: "Whiteboard Swarm Trace Worker",
                      children: (
                        <div className="grid gap-4">
                          <p className="text-sm leading-6 text-slate-600">
                            Trace Worker 是 Whiteboard Swarm 按需调度的深度可达性分析能力，不是顶层 pipeline stage。
                          </p>
                          <div className="grid gap-3 md:grid-cols-3">
                            <SwitchField name="trace_worker_enabled" label="允许 Swarm 调度 Trace Worker" defaultChecked={defaults.enable_source_sink_analysis !== false} />
                            <NumberField defaults={defaults} name="max_parallel_source_sink_finders" label="Trace Worker 并发" min={1} max={20} />
                            <NumberField defaults={defaults} name="max_source_sink_findings" label="Trace Candidate 上限" min={1} max={500} />
                          </div>
                        </div>
                      ),
                    },
                    {
                      key: "parallel",
                      title: "Concurrency and rounds",
                      children: (
                        <div className="grid gap-3 md:grid-cols-3">
                          <NumberField defaults={defaults} name="validator_rounds" label="确认轮次" min={1} max={20} />
                          <NumberField defaults={defaults} name="max_parallel_validators" label="确认并发" min={1} max={20} />
                          <NumberField defaults={defaults} name="max_parallel_code_auditors" label="Code Auditor 并发" min={1} max={20} />
                          <NumberField defaults={defaults} name="max_feedback_rounds" label="反馈轮数" min={0} max={10} />
                          <NumberField defaults={defaults} name="max_parallel_poc_writers" label="PoC Writer 并发" min={1} max={20} />
                          <NumberField defaults={defaults} name="max_parallel_poc_verifiers" label="PoC Verifier 并发" min={1} max={20} />
                          <NumberField defaults={defaults} name="max_code_audit_tasks" label="代码分析任务数" min={1} max={100} />
                          <NumberField defaults={defaults} name="max_files_per_code_audit_task" label="每任务文件数" min={1} max={200} />
                          <NumberField defaults={defaults} name="max_poc_findings" label="PoC Finding 上限" min={1} max={500} />
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
                  ]}
                />
              ),
            },
          ]}
        />

        {!customMode ? (
          <div className="flex items-start gap-2 rounded-lg border border-blue-100 bg-blue-50 px-3 py-2 text-sm text-blue-900">
            <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
            <span>当前使用 {presets[preset].label} 预设；需要细调时切换到 Advanced 或选择自定义。</span>
          </div>
        ) : null}

        <p className="text-sm text-slate-500">创建后可在 Audit Runs 页面点击“一键闭环”，按标准 pipeline 执行审计流程。</p>
        <div className="flex justify-end gap-2">
          <Button onClick={onCancel}>取消</Button>
          <Button type="submit" variant="primary" loading={loading}>创建 AuditRun</Button>
        </div>
      </form>
    </Dialog>
  );
}

function TextField({ defaults, label, name }: { defaults: Partial<LocalDefaults>; label: string; name: keyof LocalDefaults }) {
  return (
    <Field label={label}>
      <Input name={name} defaultValue={String(defaults[name] || "")} />
    </Field>
  );
}

function NumberField({ defaults, label, max, min, name }: { defaults: Partial<LocalDefaults>; label: string; max: number; min: number; name: keyof LocalDefaults }) {
  return (
    <Field label={label}>
      <NumberInput name={name} min={min} max={max} defaultValue={Number(defaults[name] || 0)} />
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

function buildEnabledAgents({
  codeAnalysis,
  pocVerification,
  pocWriting,
  validation,
}: {
  codeAnalysis: boolean;
  pocVerification: boolean;
  pocWriting: boolean;
  validation: boolean;
}) {
  return [
    "orchestrator",
    codeAnalysis ? "code-auditor" : "",
    validation ? "validator" : "",
    pocWriting ? "poc-writer" : "",
    pocVerification ? "poc-verifier" : "",
  ].filter(Boolean);
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
