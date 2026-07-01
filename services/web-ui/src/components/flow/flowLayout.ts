import type { FlowEdge, FlowNode } from "./FlowCanvas";

export function layeredLayout(nodes: FlowNode[], edges: FlowEdge[], options?: { columnWidth?: number; rowHeight?: number }) {
  const columnWidth = options?.columnWidth ?? 360;
  const rowHeight = options?.rowHeight ?? 148;
  const kindRank = new Map([
    ["pipeline", 0],
    ["agent", 1],
    ["message", 2],
    ["whiteboard", 1],
    ["swarm", 2],
    ["task", 2],
    ["finding", 3],
    ["artifact", 4],
    ["container", 3],
  ]);
  const grouped = new Map<number, FlowNode[]>();
  for (const node of nodes) {
    const rank = kindRank.get(String(node.data.kind).split("-")[0]) ?? kindRank.get(node.data.kind) ?? 2;
    grouped.set(rank, [...(grouped.get(rank) || []), node]);
  }
  const positioned = [...grouped.entries()].flatMap(([rank, items]) =>
    items.map((node, index) => ({
      ...node,
      position: node.position?.x || node.position?.y ? node.position : { x: rank * columnWidth, y: index * rowHeight },
    })),
  );
  return { nodes: positioned, edges };
}

export function flowEdge(id: string, source: string, target: string, label?: string): FlowEdge {
  const tone = edgeTone(label);
  return {
    id,
    source,
    target,
    label,
    animated: ["schedules", "started", "runs"].includes(label || ""),
    style: { stroke: tone.stroke, strokeDasharray: tone.dash, strokeWidth: 1.6 },
  };
}

function edgeTone(label?: string) {
  if (["next", "started"].includes(label || "")) return { stroke: "#0f766e", dash: undefined };
  if (["runs", "schedules"].includes(label || "")) return { stroke: "#1d4ed8", dash: "5 4" };
  if (["writes", "produces", "reports"].includes(label || "")) return { stroke: "#7c3aed", dash: undefined };
  if (["validates"].includes(label || "")) return { stroke: "#b45309", dash: undefined };
  if (["container"].includes(label || "")) return { stroke: "#475569", dash: "3 3" };
  return { stroke: "#94a3b8", dash: undefined };
}
