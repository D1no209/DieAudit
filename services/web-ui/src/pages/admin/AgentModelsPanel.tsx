import type { AgentModelConfig, AgentModelProviderTypeOption, AgentRuntimeAdapter } from "../../types";
import { Alert, Badge, Button, Field, Input, NumberInput, Panel, fieldValue, numberFieldValue } from "../../ui";

const roles = [
  { key: "orchestrator", label: "Orchestrator", displayKey: "orchestrator" },
  { key: "code-auditor", label: "Code Auditor", displayKey: "code-auditor" },
  { key: "source-sink-finder", label: "Trace Worker", displayKey: "trace-worker" },
  { key: "validator", label: "Validator", displayKey: "validator" },
  { key: "judger", label: "Judger", displayKey: "judger" },
  { key: "poc-writer", label: "PoC Writer", displayKey: "poc-writer" },
  { key: "poc-verifier", label: "PoC Verifier", displayKey: "poc-verifier" },
];

const fallbackProviderTypeOptions: AgentModelProviderTypeOption[] = [
  { value: "openai", label: "OpenAI Chat Completions" },
  { value: "openai_responses", label: "OpenAI Responses" },
  { value: "anthropic", label: "Anthropic" },
];

type Props = {
  agentModelConfig?: AgentModelConfig;
  agentRuntimes: AgentRuntimeAdapter[];
  loading: boolean;
  onSave: (values: AgentModelConfig) => void;
};

export function AgentModelsPanel({ agentModelConfig, agentRuntimes, loading, onSave }: Props) {
  const defaultRuntime = agentRuntimes[0]?.runtime_id || "kimi-code";
  const providerTypeOptions = agentModelConfig?.provider_type_options?.length
    ? agentModelConfig.provider_type_options
    : fallbackProviderTypeOptions;
  return (
    <Panel title="Agent Models" dense>
      <Alert
        className="mb-4"
        tone="processing"
        title="Platform defaults"
        description="这些参数会作为 Agent runtime provider 配置生效；Type 选项来自后端当前支持能力。API Key 留空会保留现有密钥。"
      />
      <form
        id="agent-model-profile-form"
        className="grid gap-3"
        onSubmit={(event) => {
          event.preventDefault();
          const formData = new FormData(event.currentTarget);
          onSave({
            roles: Object.fromEntries(
              roles.map((role) => [
                role.key,
                {
                  runtime_id: fieldValue(formData, `${role.key}.runtime_id`) || defaultRuntime,
                  provider_type: fieldValue(formData, `${role.key}.provider_type`) || "openai",
                  base_url: fieldValue(formData, `${role.key}.base_url`) || "",
                  model_name: fieldValue(formData, `${role.key}.model_name`) || "default",
                  api_key: fieldValue(formData, `${role.key}.api_key`) || "",
                  temperature: numberFieldValue(formData, `${role.key}.temperature`),
                  max_output_tokens: numberFieldValue(formData, `${role.key}.max_output_tokens`),
                  context_window: numberFieldValue(formData, `${role.key}.context_window`),
                },
              ]),
            ),
          });
        }}
      >
        <section className="rounded-lg border border-cyan-300 bg-cyan-50 p-3">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <div>
              <div className="text-sm font-semibold text-slate-950">Common Profile</div>
              <div className="text-xs text-slate-600">填一次并应用到全部 Agent，下面仍可逐项覆盖。</div>
            </div>
            <Button
              size="sm"
              onClick={() => applyCommonProfile(defaultRuntime)}
            >
              一键应用到全部
            </Button>
          </div>
          <div className="grid gap-3 lg:grid-cols-4">
            <Field label="Runtime">
              <Input name="common.runtime_id" defaultValue={defaultRuntime} list="agent-runtime-ids" />
            </Field>
            <Field label="Type">
              <ProviderSelect name="common.provider_type" defaultValue="openai" options={providerTypeOptions} />
            </Field>
            <Field label="Model name">
              <Input name="common.model_name" placeholder="gpt-4.1 / gpt-4.1-mini / claude-3.5" />
            </Field>
            <Field label="API Key">
              <Input name="common.api_key" type="password" placeholder="Optional shared key" />
            </Field>
            <div className="lg:col-span-2">
              <Field label="Base URL">
                <Input name="common.base_url" placeholder="https://api.openai.com/v1" />
              </Field>
            </div>
            <Field label="Temperature">
              <NumberInput name="common.temperature" step="0.1" min={0} max={2} defaultValue={0.1} />
            </Field>
            <Field label="Max tokens">
              <NumberInput name="common.max_output_tokens" min={1} defaultValue={8192} />
            </Field>
            <Field label="Context window">
              <NumberInput name="common.context_window" min={1} defaultValue={128000} />
            </Field>
          </div>
        </section>
        <div className="grid gap-3">
          {roles.map((role) => {
            const current = agentModelConfig?.roles?.[role.key];
            return (
              <section key={role.key} className="rounded-lg border border-slate-300 bg-slate-50 p-3">
                <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <div className="text-sm font-semibold text-slate-950">{role.label}</div>
                    <div className="text-xs text-slate-500">{role.displayKey}</div>
                  </div>
                  <div className="flex flex-wrap gap-1">
                    <Badge>{current?.runtime_id || defaultRuntime}</Badge>
                    {current?.api_key_set ? <Badge tone="success">key {current.api_key_preview || "set"}</Badge> : <Badge tone="warning">no key</Badge>}
                  </div>
                </div>
                <div className="grid gap-3 lg:grid-cols-4">
                  <Field label="Runtime">
                    <Input name={`${role.key}.runtime_id`} defaultValue={current?.runtime_id || defaultRuntime} list="agent-runtime-ids" />
                  </Field>
                  <Field label="Type">
                    <ProviderSelect name={`${role.key}.provider_type`} defaultValue={current?.provider_type || "openai"} options={providerTypeOptions} />
                  </Field>
                  <Field label="Model name">
                    <Input name={`${role.key}.model_name`} defaultValue={current?.model_name || "default"} placeholder="gpt-4.1 / gpt-4.1-mini / claude-3.5" />
                  </Field>
                  <Field label="API Key">
                    <Input name={`${role.key}.api_key`} type="password" placeholder={current?.api_key_set ? "Leave blank to keep existing key" : "Paste key"} />
                  </Field>
                  <div className="lg:col-span-2">
                    <Field label="Base URL">
                      <Input name={`${role.key}.base_url`} defaultValue={current?.base_url || ""} placeholder="https://api.openai.com/v1" />
                    </Field>
                  </div>
                  <Field label="Temperature">
                    <NumberInput name={`${role.key}.temperature`} step="0.1" min={0} max={2} defaultValue={current?.temperature ?? 0.1} />
                  </Field>
                  <Field label="Max tokens">
                    <NumberInput name={`${role.key}.max_output_tokens`} min={1} defaultValue={current?.max_output_tokens ?? 8192} />
                  </Field>
                  <Field label="Context window">
                    <NumberInput name={`${role.key}.context_window`} min={1} defaultValue={current?.context_window ?? 128000} />
                  </Field>
                </div>
              </section>
            );
          })}
        </div>
        <datalist id="agent-runtime-ids">
          {agentRuntimes.map((runtime) => (
            <option key={runtime.runtime_id} value={runtime.runtime_id} />
          ))}
        </datalist>
        <div className="flex justify-end">
          <Button type="submit" variant="primary" loading={loading}>保存 Agent 模型配置</Button>
        </div>
      </form>
    </Panel>
  );
}

function applyCommonProfile(defaultRuntime: string) {
  const form = document.getElementById("agent-model-profile-form") as HTMLFormElement | null;
  if (!form) return;
  const formData = new FormData(form);
  const common = {
    runtime_id: fieldValue(formData, "common.runtime_id") || defaultRuntime,
    provider_type: fieldValue(formData, "common.provider_type") || "openai",
    model_name: fieldValue(formData, "common.model_name") || "default",
    api_key: fieldValue(formData, "common.api_key") || "",
    base_url: fieldValue(formData, "common.base_url") || "",
    temperature: String(numberFieldValue(formData, "common.temperature") ?? 0.1),
    max_output_tokens: String(numberFieldValue(formData, "common.max_output_tokens") ?? 8192),
    context_window: String(numberFieldValue(formData, "common.context_window") ?? 128000),
  };
  for (const role of roles) {
    setFormValue(form, `${role.key}.runtime_id`, common.runtime_id);
    setFormValue(form, `${role.key}.provider_type`, common.provider_type);
    setFormValue(form, `${role.key}.model_name`, common.model_name);
    setFormValue(form, `${role.key}.base_url`, common.base_url);
    setFormValue(form, `${role.key}.temperature`, common.temperature);
    setFormValue(form, `${role.key}.max_output_tokens`, common.max_output_tokens);
    setFormValue(form, `${role.key}.context_window`, common.context_window);
    if (common.api_key) {
      setFormValue(form, `${role.key}.api_key`, common.api_key);
    }
  }
}

function setFormValue(form: HTMLFormElement, name: string, value: string) {
  const element = form.elements.namedItem(name);
  if (element instanceof HTMLInputElement || element instanceof HTMLSelectElement) {
    element.value = value;
  }
}

function ProviderSelect({ defaultValue, name, options }: { defaultValue?: string; name: string; options: AgentModelProviderTypeOption[] }) {
  return (
    <select
      name={name}
      defaultValue={defaultValue || "openai"}
      className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none transition focus:border-cyan-800 focus:ring-2 focus:ring-cyan-800/15"
    >
      {providerOptionValues(options, defaultValue).map((type) => (
        <option key={type.value} value={type.value}>{type.label}</option>
      ))}
    </select>
  );
}

function providerOptionValues(options: AgentModelProviderTypeOption[], current?: string) {
  const value = (current || "").trim();
  return value && !options.some((option) => option.value === value) ? [...options, { value, label: value }] : options;
}
