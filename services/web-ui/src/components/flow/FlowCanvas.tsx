import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import { Filter, Maximize2, RotateCcw } from "lucide-react";
import { useMemo } from "react";
import { executionNodeMeta } from "../../displayMeta";
import type { FlowNodeData } from "../../types";
import { Badge, Button, EmptyState, Panel } from "../../ui";
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
  const nodeKinds = useMemo(() => Array.from(new Set(nodes.map((node) => node.data.kind))).sort(), [nodes]);

  return (
    <Panel
      className={cn("overflow-hidden", className)}
      title={title}
      actions={
        <div className="flex flex-wrap items-center gap-2">
          <Badge>{nodes.length} nodes</Badge>
          <Badge>{edges.length} links</Badge>
          <Button size="icon" variant="ghost" aria-label="Filter graph" icon={<Filter className="h-4 w-4" />} />
          <Button size="icon" variant="ghost" aria-label="Fit graph" icon={<Maximize2 className="h-4 w-4" />} />
          <Button size="icon" variant="ghost" aria-label="Reset graph" icon={<RotateCcw className="h-4 w-4" />} />
          {actions}
        </div>
      }
    >
      {description ? <p className="mb-3 text-sm leading-6 text-slate-600">{description}</p> : null}
      {nodeKinds.length ? (
        <div className="mb-3 flex gap-1 overflow-x-auto">
          {nodeKinds.map((kind) => (
            <Badge key={kind}>{executionNodeMeta(kind).label}</Badge>
          ))}
        </div>
      ) : null}
      <div className="overflow-hidden rounded-lg border border-slate-300 bg-slate-100" style={{ height }}>
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
            <Background color="#c4cbd4" gap={24} />
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
  const meta = executionNodeMeta(nodeData.kind);
  return (
    <div
      className={cn(
        "w-64 rounded-lg border bg-white p-3 shadow-sm shadow-slate-200/70",
        selected ? "border-cyan-700 ring-2 ring-cyan-800/15" : "border-slate-300",
      )}
    >
      <div className="mb-2 flex items-start gap-2">
        <span className={cn("rounded-md border p-1.5", meta.ring)}>{meta.icon}</span>
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold text-slate-950">{nodeData.label}</div>
          <div className="mt-1 flex flex-wrap gap-1">
            <Badge tone={tone}>{nodeData.status || "unknown"}</Badge>
            <Badge>{meta.label}</Badge>
          </div>
        </div>
      </div>
      {nodeData.summary ? <p className="line-clamp-3 text-xs leading-5 text-slate-600">{nodeData.summary}</p> : null}
      {nodeData.group ? <div className="mt-2 truncate text-[11px] font-semibold uppercase text-slate-500">{nodeData.group}</div> : null}
    </div>
  );
}
