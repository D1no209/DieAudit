import { useMemo, useState } from "react";
import { Bot, SquareStack } from "lucide-react";
import { FlowCanvas, type FlowNode } from "../components/flow/FlowCanvas";
import { executionGraphToFlow } from "../components/flow/flowMappers";
import type { AgentRun, AuditRun, ContainerRow, ExecutionGraph } from "../types";
import type { DataColumn } from "../ui";
import { Alert, Badge, Button, DataTable, EmptyState, Panel } from "../ui";
import { PageHeader } from "../components/PageHeader";

type Props = {
  agentColumns: DataColumn<AgentRun>[];
  agentRuns: AgentRun[];
  auditRun?: AuditRun;
  containers: ContainerRow[];
  executionGraph?: ExecutionGraph;
  onOpenAgentEvents: (agentRunId: string) => void;
  onOpenContainerLogs: (row: ContainerRow) => void;
  onViewWhiteboard: () => void;
};

export function AgentRunsPage({
  agentColumns,
  agentRuns,
  auditRun,
  containers,
  executionGraph,
  onOpenAgentEvents,
  onOpenContainerLogs,
  onViewWhiteboard,
}: Props) {
  const nodes = executionGraph?.nodes || [];
  const edges = executionGraph?.edges || [];
  const statusCounts = executionGraph?.summary?.by_status || {};
  const [selectedNode, setSelectedNode] = useState<FlowNode | undefined>();
  const flow = useMemo(() => executionGraphToFlow(executionGraph), [executionGraph]);

  return (
    <>
      <PageHeader title="Agent Runs" />
      {!auditRun ? (
        <Alert className="mb-5" tone="processing" title="No active AuditRun" description="Create an audit run before inspecting agent execution." />
      ) : null}
      <div className="mb-5 grid gap-4 xl:grid-cols-[minmax(280px,0.55fr)_minmax(560px,1.45fr)]">
        <Panel title="Run Status">
          <div className="flex flex-wrap gap-2">
            <Badge tone="success">completed {executionGraph?.summary?.completed ?? statusCounts.completed ?? 0}</Badge>
            <Badge tone="processing">unfinished {executionGraph?.summary?.unfinished ?? 0}</Badge>
            <Badge tone="danger">failed {executionGraph?.summary?.failed ?? statusCounts.failed ?? 0}</Badge>
            <Badge>{edges.length} links</Badge>
          </div>
          <p className="mt-4 text-sm leading-6 text-slate-600">
            Graph combines pipeline steps, ACP AgentRuns, containers, Whiteboard swarm tasks, and decompiled artifacts.
          </p>
        </Panel>
        <Panel
          title="Execution Graph"
          actions={
            <div className="flex flex-wrap gap-2">
              <Badge>{nodes.length} nodes</Badge>
              <Button size="sm" onClick={onViewWhiteboard}>Whiteboard</Button>
            </div>
          }
        >
          {flow.nodes.length ? (
            <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_320px]">
              <FlowCanvas nodes={flow.nodes} edges={flow.edges} height={560} onNodeSelect={setSelectedNode} />
              <AgentNodeInspector
                node={selectedNode}
                containers={containers}
                onOpenAgentEvents={onOpenAgentEvents}
                onOpenContainerLogs={onOpenContainerLogs}
                onViewWhiteboard={onViewWhiteboard}
              />
            </div>
          ) : (
            <EmptyState description="No execution graph yet" />
          )}
        </Panel>
      </div>
      <Panel title="Agent Execution" actions={<span className="text-sm text-slate-500">{auditRun?.audit_run_id || "No run"} {auditRun?.status ? <Badge>{auditRun.status}</Badge> : null}</span>}>
        <DataTable getRowKey={(row) => row.agent_run_id} columns={agentColumns} data={agentRuns} pagination={{ pageSize: 10 }} />
      </Panel>
    </>
  );
}

function AgentNodeInspector({
  node,
  containers,
  onOpenAgentEvents,
  onOpenContainerLogs,
  onViewWhiteboard,
}: {
  node?: FlowNode;
  containers: ContainerRow[];
  onOpenAgentEvents: (agentRunId: string) => void;
  onOpenContainerLogs: (row: ContainerRow) => void;
  onViewWhiteboard: () => void;
}) {
  if (!node) {
    return <Panel title="Inspector"><EmptyState description="Select a graph node" /></Panel>;
  }
  const agentRunId = node.data.target?.agent_run_id;
  const containerId = String((node.data.raw as { data?: Record<string, unknown> } | undefined)?.data?.container_id || node.data.target?.container_id || "");
  const container = containers.find((row) => row.Id === containerId || row.container_id === containerId);
  return (
    <Panel title="Inspector">
      <div className="grid gap-4 text-sm">
        <div className="flex items-start gap-2">
          <span className="mt-0.5 rounded-lg border border-slate-200 bg-slate-50 p-1.5 text-slate-500"><Bot className="h-4 w-4" /></span>
          <div className="min-w-0">
            <div className="truncate font-medium text-slate-900">{node.data.label}</div>
            <div className="mt-2 flex flex-wrap gap-1">
              {node.data.status ? <Badge>{node.data.status}</Badge> : null}
              <Badge>{node.data.kind}</Badge>
              {node.data.group ? <Badge>{node.data.group}</Badge> : null}
            </div>
          </div>
        </div>
        <p className="whitespace-pre-wrap leading-6 text-slate-600">{node.data.summary || "No summary"}</p>
        <div className="flex flex-wrap gap-2">
          {agentRunId ? <Button size="sm" onClick={() => onOpenAgentEvents(agentRunId)}>Raw Events</Button> : null}
          {container ? <Button size="sm" onClick={() => onOpenContainerLogs(container)}>Logs</Button> : null}
          {node.data.kind.startsWith("whiteboard") ? <Button size="sm" icon={<SquareStack className="h-4 w-4" />} onClick={onViewWhiteboard}>Open</Button> : null}
        </div>
        <pre className="max-h-72 overflow-auto rounded-lg bg-slate-950 p-3 text-xs text-slate-100">{JSON.stringify(node.data.raw, null, 2)}</pre>
      </div>
    </Panel>
  );
}
