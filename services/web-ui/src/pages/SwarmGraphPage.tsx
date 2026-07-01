import { useMemo, useState } from "react";
import { FlowCanvas, type FlowNode } from "../components/flow/FlowCanvas";
import { swarmToFlow } from "../components/flow/flowMappers";
import type { AgentRun, AuditRun, WhiteboardGraph } from "../types";
import { Alert, Badge, EmptyState, MetricCard, Panel, Tabs } from "../ui";
import { PageHeader } from "../components/PageHeader";

type Props = {
  agentRuns: AgentRun[];
  auditRun?: AuditRun;
  whiteboard?: WhiteboardGraph;
};

export function SwarmGraphPage({ agentRuns, auditRun, whiteboard }: Props) {
  const [selectedNode, setSelectedNode] = useState<FlowNode | undefined>();
  const flow = useMemo(() => swarmToFlow(whiteboard, agentRuns), [agentRuns, whiteboard]);
  const tasks = whiteboard?.tasks || [];
  const subscriptions = whiteboard?.subscriptions || [];
  const notifications = whiteboard?.notifications || [];
  const scheduleRequests = whiteboard?.schedule_requests || [];

  return (
    <>
      <PageHeader title="Agent Swarm" eyebrow="Flow Graph" />
      {!auditRun ? (
        <Alert className="mb-5" tone="processing" title="No active AuditRun" description="Select or create an audit run before inspecting the swarm graph." />
      ) : null}
      <div className="mb-5 grid gap-4 md:grid-cols-4">
        <MetricCard label="Tasks" value={tasks.length} />
        <MetricCard label="Subscriptions" value={subscriptions.length} />
        <MetricCard label="Notifications" value={notifications.length} />
        <MetricCard label="Schedule requests" value={scheduleRequests.length} />
      </div>
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_380px]">
        <FlowCanvas
          title="Swarm Execution Graph"
          description="Tasks, notifications, requests, and agent runs share one execution canvas."
          nodes={flow.nodes}
          edges={flow.edges}
          height={680}
          onNodeSelect={setSelectedNode}
          selectedNodeId={selectedNode?.id}
        />
        <Panel title="Inspector" dense>
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
                        <p className="mt-2 whitespace-pre-wrap leading-6 text-slate-600">{selectedNode.data.summary || "No summary"}</p>
                      </div>
                    </div>
                  ),
                },
                {
                  key: "raw",
                  label: "Payload",
                  children: <pre className="max-h-[560px] overflow-auto rounded-lg bg-slate-950 p-3 text-xs text-slate-100">{JSON.stringify(selectedNode.data.raw, null, 2)}</pre>,
                },
              ]}
            />
          ) : (
            <EmptyState description="Select a swarm node" />
          )}
        </Panel>
      </div>
    </>
  );
}
