import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import { Boxes, Bot, Bug, FileText, GitBranch, MessageSquare, Network, Workflow } from "lucide-react";
import { useMemo } from "react";
import type { FlowNodeData } from "../../types";
import { Badge, EmptyState, Panel } from "../../ui";
import { cn } from "../../ui/utils";
import { statusTone } from "../../utils/format";

export type FlowNode = Node<FlowNodeData>;
export type FlowEdge = Edge<Record<string, unknown>>;

type Props = {
  actions?: React.ReactNode;
  className?: string;
  description?: React.ReactNode;
  edges: FlowEdge[];
  height?: number;
  nodes: FlowNode[];
  onNodeSelect?: (node: FlowNode) => void;
  selectedNodeId?: string;
  title?: React.ReactNode;
};

const nodeTypes = {
  pipeline: FlowCardNode,
  agent: FlowCardNode,
  message: FlowCardNode,
  whiteboard: FlowCardNode,
  swarm: FlowCardNode,
  artifact: FlowCardNode,
  finding: FlowCardNode,
  container: FlowCardNode,
  default: FlowCardNode,
};

export function FlowCanvas({ actions, className, description, edges, height = 560, nodes, onNodeSelect, selectedNodeId, title = "Graph" }: Props) {
  const decoratedNodes = useMemo(
    () =>
      nodes.map((node) => ({
        ...node,
        selected: selectedNodeId === node.id,
      })),
    [nodes, selectedNodeId],
  );

  return (
    <Panel
      className={cn("overflow-hidden", className)}
      title={title}
      actions={
        <div className="flex flex-wrap items-center gap-2">
          <Badge>{nodes.length} nodes</Badge>
          <Badge>{edges.length} links</Badge>
          {actions}
        </div>
      }
    >
      {description ? <p className="mb-3 text-sm leading-6 text-slate-600">{description}</p> : null}
      <div className="overflow-hidden rounded-lg border border-slate-200 bg-slate-50" style={{ height }}>
        {nodes.length ? (
          <ReactFlow
            fitView
            nodes={decoratedNodes}
            edges={edges}
            nodeTypes={nodeTypes}
            minZoom={0.25}
            maxZoom={1.6}
            onNodeClick={(_, node) => onNodeSelect?.(node as FlowNode)}
          >
            <Background color="#cbd5e1" gap={24} />
            <MiniMap pannable zoomable nodeStrokeWidth={3} />
            <Controls showInteractive={false} />
          </ReactFlow>
        ) : (
          <div className="flex h-full items-center justify-center">
            <EmptyState description="No graph data yet" />
          </div>
        )}
      </div>
    </Panel>
  );
}

function FlowCardNode({ data, selected }: NodeProps) {
  const nodeData = data as FlowNodeData;
  const tone = statusTone(nodeData.status);
  return (
    <div
      className={cn(
        "w-64 rounded-lg border bg-white p-3 shadow-sm shadow-slate-200/70",
        selected ? "border-blue-500 ring-2 ring-blue-100" : "border-slate-200",
      )}
    >
      <div className="mb-2 flex items-start gap-2">
        <span className={cn("rounded-md border p-1.5", iconTone(nodeData.kind))}>{nodeIcon(nodeData.kind)}</span>
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold text-slate-950">{nodeData.label}</div>
          <div className="mt-1 flex flex-wrap gap-1">
            <Badge tone={tone}>{nodeData.status || "unknown"}</Badge>
            <Badge>{nodeData.kind}</Badge>
          </div>
        </div>
      </div>
      {nodeData.summary ? <p className="line-clamp-3 text-xs leading-5 text-slate-600">{nodeData.summary}</p> : null}
      {nodeData.group ? <div className="mt-2 text-[11px] font-medium uppercase tracking-wide text-slate-400">{nodeData.group}</div> : null}
    </div>
  );
}

function nodeIcon(kind: string) {
  if (kind.includes("message")) return <MessageSquare className="h-4 w-4" />;
  if (kind.includes("agent")) return <Bot className="h-4 w-4" />;
  if (kind.includes("whiteboard")) return <GitBranch className="h-4 w-4" />;
  if (kind.includes("swarm") || kind.includes("task")) return <Workflow className="h-4 w-4" />;
  if (kind.includes("artifact")) return <FileText className="h-4 w-4" />;
  if (kind.includes("finding")) return <Bug className="h-4 w-4" />;
  if (kind.includes("container")) return <Boxes className="h-4 w-4" />;
  return <Network className="h-4 w-4" />;
}

function iconTone(kind: string) {
  if (kind.includes("agent")) return "border-blue-200 bg-blue-50 text-blue-700";
  if (kind.includes("message")) return "border-indigo-200 bg-indigo-50 text-indigo-700";
  if (kind.includes("whiteboard")) return "border-emerald-200 bg-emerald-50 text-emerald-700";
  if (kind.includes("swarm") || kind.includes("task")) return "border-amber-200 bg-amber-50 text-amber-700";
  if (kind.includes("finding")) return "border-rose-200 bg-rose-50 text-rose-700";
  return "border-slate-200 bg-slate-50 text-slate-600";
}
