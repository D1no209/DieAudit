import type {
  AgentRun,
  AgentTranscriptEvent,
  ExecutionGraph,
  WhiteboardGraph,
} from "../../types";
import type { FlowEdge, FlowNode } from "./FlowCanvas";
import { flowEdge, layeredLayout } from "./flowLayout";

export function executionGraphToFlow(graph?: ExecutionGraph) {
  const nodes: FlowNode[] = (graph?.nodes || []).map((node) => ({
    id: node.id,
    type: flowType(node.kind),
    position: { x: 0, y: 0 },
    data: {
      kind: node.kind,
      label: node.label,
      status: node.status,
      group: node.group,
      target: node.target,
      raw: node,
    },
  }));
  const edges: FlowEdge[] = (graph?.edges || []).map((edge, index) =>
    flowEdge(`execution-${index}-${edge.source}-${edge.target}`, edge.source, edge.target, edge.type),
  );
  return layeredLayout(nodes, edges);
}

export function agentMessagesToFlow(agentRuns: AgentRun[], events: AgentTranscriptEvent[]) {
  const nodes: FlowNode[] = agentRuns.map((agent, index) => ({
    id: agent.agent_run_id,
    type: "agent",
    position: { x: 0, y: index * 180 },
    data: {
      kind: "agent",
      label: agent.agent_name,
      status: agent.status,
      group: agent.template_name,
      summary: agent.error || agent.agent_run_id,
      target: { agent_run_id: agent.agent_run_id },
      raw: agent,
    },
  }));
  const edges: FlowEdge[] = [];
  const byAgent = new Map<string, AgentTranscriptEvent[]>();
  for (const event of events) {
    byAgent.set(event.agent_run_id, [...(byAgent.get(event.agent_run_id) || []), event]);
  }
  for (const [agentRunId, rows] of byAgent) {
    const sortedRows = rows.slice().sort((left, right) => left.seq - right.seq);
    sortedRows.forEach((event, index) => {
        const id = `message-${event.agent_run_id}-${event.id || event.seq}`;
        nodes.push({
          id,
          type: "message",
          position: { x: 360 + index * 320, y: Math.max(0, [...byAgent.keys()].indexOf(agentRunId)) * 180 },
          data: {
            kind: "message",
            label: event.event_type,
            status: event.session_id ? "session" : "event",
            group: `seq ${event.seq}`,
            summary: event.content_text || summarizePayload(event.payload),
            target: { agent_run_id: event.agent_run_id },
            raw: event,
          },
        });
        const previous = sortedRows[index - 1];
        edges.push(flowEdge(`agent-message-${agentRunId}-${index}`, index === 0 ? agentRunId : `message-${event.agent_run_id}-${previous.id || previous.seq}`, id));
      });
  }
  return { nodes, edges };
}

export function whiteboardToFlow(whiteboard?: WhiteboardGraph) {
  const nodes: FlowNode[] = [];
  const edges: FlowEdge[] = [];
  for (const card of whiteboard?.cards || []) {
    nodes.push({
      id: `card-${card.card_id}`,
      type: "whiteboard",
      position: { x: 0, y: 0 },
      data: {
        kind: "whiteboard-card",
        label: card.title,
        status: card.status,
        group: card.card_type,
        summary: card.content || card.file_path || card.finding_id,
        target: { card_id: card.card_id },
        raw: card,
      },
    });
  }
  for (const edge of whiteboard?.edges || []) {
    edges.push(flowEdge(edge.edge_id, `card-${edge.source_card_id}`, `card-${edge.target_card_id}`, edge.edge_type));
  }
  for (const item of whiteboard?.evidence || []) {
    const id = `evidence-${item.evidence_id}`;
    nodes.push({
      id,
      type: "artifact",
      position: { x: 0, y: 0 },
      data: {
        kind: "artifact",
        label: item.summary || item.evidence_id,
        status: "evidence",
        summary: item.artifact_path || item.finding_id,
        raw: item,
      },
    });
    if (item.finding_id) {
      const card = (whiteboard?.cards || []).find((row) => row.finding_id === item.finding_id);
      if (card) edges.push(flowEdge(`evidence-link-${item.evidence_id}`, `card-${card.card_id}`, id, "evidence"));
    }
  }
  return layeredLayout(nodes, edges);
}

export function swarmToFlow(whiteboard?: WhiteboardGraph, agentRuns: AgentRun[] = []) {
  const nodes: FlowNode[] = [];
  const edges: FlowEdge[] = [];
  for (const agent of agentRuns) {
    nodes.push({
      id: `agent-${agent.agent_run_id}`,
      type: "agent",
      position: { x: 0, y: 0 },
      data: { kind: "agent", label: agent.agent_name, status: agent.status, summary: agent.template_name, target: { agent_run_id: agent.agent_run_id }, raw: agent },
    });
  }
  for (const task of whiteboard?.tasks || []) {
    const id = `task-${task.task_id}`;
    nodes.push({
      id,
      type: "swarm",
      position: { x: 0, y: 0 },
      data: {
        kind: "swarm-task",
        label: task.agent_role,
        status: task.status,
        group: task.agent_name,
        summary: task.prompt || task.wait_reason || task.task_id,
        target: { task_id: task.task_id, agent_run_id: task.agent_run_id },
        raw: task,
      },
    });
    if (task.parent_task_id) edges.push(flowEdge(`task-parent-${task.task_id}`, `task-${task.parent_task_id}`, id, "parent"));
    if (task.agent_run_id) edges.push(flowEdge(`task-agent-${task.task_id}`, `agent-${task.agent_run_id}`, id, "runs"));
  }
  for (const note of whiteboard?.notifications || []) {
    const id = `notice-${note.notification_id}`;
    nodes.push({
      id,
      type: "message",
      position: { x: 0, y: 0 },
      data: { kind: "message", label: note.summary || "notification", status: note.status, summary: note.event_id, raw: note },
    });
    if (note.subscriber_task_id) edges.push(flowEdge(`notice-task-${note.notification_id}`, id, `task-${note.subscriber_task_id}`, "notifies"));
  }
  return layeredLayout(nodes, edges);
}

function flowType(kind: string) {
  if (kind.includes("agent")) return "agent";
  if (kind.includes("whiteboard")) return "whiteboard";
  if (kind.includes("container")) return "container";
  if (kind.includes("artifact")) return "artifact";
  if (kind.includes("finding")) return "finding";
  if (kind.includes("pipeline")) return "pipeline";
  return "default";
}

function summarizePayload(value: unknown) {
  if (!value || typeof value !== "object") return String(value || "");
  const record = value as Record<string, unknown>;
  for (const key of ["text", "content", "message", "summary", "error"]) {
    const text = record[key];
    if (typeof text === "string" && text.trim()) return text.trim();
  }
  return JSON.stringify(record).slice(0, 240);
}
