import { useEffect, useMemo, useState } from "react";
import { MessageSquareText } from "lucide-react";
import { FlowCanvas, type FlowNode } from "../components/flow/FlowCanvas";
import { agentMessagesToFlow } from "../components/flow/flowMappers";
import type { AgentRun, AgentTranscriptEvent, AuditRun } from "../types";
import { Alert, Badge, Button, EmptyState, Panel, Tabs } from "../ui";
import { PageHeader } from "../components/PageHeader";

type Props = {
  agentMessages: AgentTranscriptEvent[];
  agentRuns: AgentRun[];
  auditRun?: AuditRun;
  loading: boolean;
  onOpenAgentMessages: (agentRunId: string) => void;
};

export function AgentMessagesPage({ agentMessages, agentRuns, auditRun, loading, onOpenAgentMessages }: Props) {
  const [selectedAgentRunId, setSelectedAgentRunId] = useState<string | undefined>();
  const [selectedNode, setSelectedNode] = useState<FlowNode | undefined>();
  const flow = useMemo(() => agentMessagesToFlow(agentRuns, agentMessages), [agentRuns, agentMessages]);

  useEffect(() => {
    if (!selectedAgentRunId && agentRuns[0]?.agent_run_id) {
      setSelectedAgentRunId(agentRuns[0].agent_run_id);
    }
  }, [agentRuns, selectedAgentRunId]);

  useEffect(() => {
    if (selectedAgentRunId) {
      onOpenAgentMessages(selectedAgentRunId);
    }
  }, [selectedAgentRunId]);

  return (
    <>
      <PageHeader title="Agent Messages" />
      {!auditRun ? (
        <Alert className="mb-5" tone="processing" title="No active AuditRun" description="Select or create an audit run before inspecting agent messages." />
      ) : null}
      <div className="grid gap-4 xl:grid-cols-[280px_minmax(0,1fr)_360px]">
        <Panel title="Agent Lanes">
          {agentRuns.length ? (
            <div className="grid gap-2">
              {agentRuns.map((agent) => (
                <Button
                  key={agent.agent_run_id}
                  className="justify-start"
                  icon={<MessageSquareText className="h-4 w-4" />}
                  loading={loading && selectedAgentRunId === agent.agent_run_id}
                  variant={selectedAgentRunId === agent.agent_run_id ? "primary" : "secondary"}
                  onClick={() => setSelectedAgentRunId(agent.agent_run_id)}
                >
                  <span className="truncate">{agent.agent_name}</span>
                </Button>
              ))}
            </div>
          ) : (
            <EmptyState description="No agent runs yet" />
          )}
        </Panel>

        <FlowCanvas
          title="Message Flow"
          description="Transcript events are grouped by agent run and ordered by sequence."
          nodes={flow.nodes}
          edges={flow.edges}
          height={620}
          onNodeSelect={setSelectedNode}
        />

        <Panel title="Inspector">
          {selectedNode ? (
            <Tabs
              items={[
                {
                  key: "summary",
                  label: "Summary",
                  children: (
                    <div className="grid gap-3 text-sm">
                      <div className="flex flex-wrap gap-2">
                        <Badge>{selectedNode.data.kind}</Badge>
                        {selectedNode.data.status ? <Badge>{selectedNode.data.status}</Badge> : null}
                        {selectedNode.data.group ? <Badge>{selectedNode.data.group}</Badge> : null}
                      </div>
                      <div>
                        <div className="font-medium text-slate-900">{selectedNode.data.label}</div>
                        <p className="mt-2 whitespace-pre-wrap leading-6 text-slate-600">{selectedNode.data.summary || "No content text"}</p>
                      </div>
                    </div>
                  ),
                },
                {
                  key: "raw",
                  label: "Raw Event",
                  children: <pre className="max-h-[520px] overflow-auto rounded-lg bg-slate-950 p-3 text-xs text-slate-100">{JSON.stringify(selectedNode.data.raw, null, 2)}</pre>,
                },
              ]}
            />
          ) : (
            <EmptyState description="Select a message node" />
          )}
        </Panel>
      </div>
    </>
  );
}
