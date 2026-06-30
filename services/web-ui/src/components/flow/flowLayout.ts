import type { FlowEdge, FlowNode } from "./FlowCanvas";

export function layeredLayout(nodes: FlowNode[], edges: FlowEdge[], options?: { columnWidth?: number; rowHeight?: number }) {
  const columnWidth = options?.columnWidth ?? 340;
  const rowHeight = options?.rowHeight ?? 160;
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
  return {
    id,
    source,
    target,
    label,
    animated: false,
    style: { stroke: "#94a3b8", strokeWidth: 1.5 },
  };
}
