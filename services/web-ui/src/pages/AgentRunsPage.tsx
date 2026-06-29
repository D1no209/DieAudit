import { Bot, Boxes, GitBranch, Network, SquareStack } from "lucide-react";
import type { AgentRun, AuditRun, ContainerRow, ExecutionGraph, ExecutionGraphNode } from "../types";
import type { DataColumn } from "../ui";
import { Alert, Badge, Button, DataTable, EmptyState, Panel } from "../ui";
import { statusTone } from "../utils/format";
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
  const runnableNodes = nodes.filter((node) =>
    ["agent-run", "whiteboard-task", "whiteboard-card", "container", "pipeline-step", "decompiled-artifact"].includes(node.kind),
  );
  const statusCounts = executionGraph?.summary?.by_status || {};
  const containerById = new Map(containers.map((container) => [container.Id || container.container_id || "", container]));

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
          {runnableNodes.length ? (
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3" aria-label="Agent execution graph">
              {runnableNodes.map((node) => (
                <GraphNode
                  key={node.id}
                  node={node}
                  container={node.kind === "container" ? containerById.get(String(node.data?.container_id || "")) : undefined}
                  onOpenAgentEvents={onOpenAgentEvents}
                  onOpenContainerLogs={onOpenContainerLogs}
                  onViewWhiteboard={onViewWhiteboard}
                />
              ))}
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

function GraphNode({
  node,
  container,
  onOpenAgentEvents,
  onOpenContainerLogs,
  onViewWhiteboard,
}: {
  node: ExecutionGraphNode;
  container?: ContainerRow;
  onOpenAgentEvents: (agentRunId: string) => void;
  onOpenContainerLogs: (row: ContainerRow) => void;
  onViewWhiteboard: () => void;
}) {
  const icon =
    node.kind === "container"
      ? <Boxes className="h-4 w-4" />
      : node.kind.startsWith("whiteboard")
        ? <GitBranch className="h-4 w-4" />
        : node.kind === "pipeline-step"
          ? <Network className="h-4 w-4" />
          : <Bot className="h-4 w-4" />;
  const agentRunId = node.target?.agent_run_id;
  return (
    <div className="flex min-h-28 flex-col justify-between gap-3 rounded-lg border border-slate-200 border-l-blue-500 bg-white p-3 shadow-sm">
      <div className="flex items-start gap-2">
        <span className="mt-0.5 rounded-lg border border-slate-200 bg-slate-50 p-1.5 text-slate-500">{icon}</span>
        <div className="min-w-0">
          <div className="truncate font-medium text-slate-900">{node.label}</div>
          <div className="mt-2 flex flex-wrap gap-1">
            <Badge tone={statusTone(node.status)}>{node.status || "unknown"}</Badge>
            <Badge>{node.kind}</Badge>
            {node.group ? <Badge>{node.group}</Badge> : null}
          </div>
        </div>
      </div>
      <div className="flex flex-wrap gap-2">
        {agentRunId ? <Button size="sm" onClick={() => onOpenAgentEvents(agentRunId)}>Events</Button> : null}
        {container ? <Button size="sm" onClick={() => onOpenContainerLogs(container)}>Logs</Button> : null}
        {node.kind.startsWith("whiteboard") ? <Button size="sm" icon={<SquareStack className="h-4 w-4" />} onClick={onViewWhiteboard}>Open</Button> : null}
      </div>
    </div>
  );
}
