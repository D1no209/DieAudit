import { useMemo, useState } from "react";
import { Clock, PlayCircle } from "lucide-react";
import { FlowCanvas, type FlowNode } from "../components/flow/FlowCanvas";
import { whiteboardToFlow } from "../components/flow/flowMappers";
import type { AuditRun, WhiteboardGraph } from "../types";
import { Alert, Badge, Button, EmptyState, MetricCard, Panel, Tabs } from "../ui";
import { statusTone } from "../utils/format";
import { PageHeader } from "../components/PageHeader";

type Props = {
  auditRun?: AuditRun;
  loading: boolean;
  whiteboard?: WhiteboardGraph;
  onRunWhiteboardSwarm: () => void;
};

export function WhiteboardPage({ auditRun, loading, whiteboard, onRunWhiteboardSwarm }: Props) {
  const [selectedNode, setSelectedNode] = useState<FlowNode | undefined>();
  const flow = useMemo(() => whiteboardToFlow(whiteboard), [whiteboard]);
  const cards = whiteboard?.cards || [];
  const edges = whiteboard?.edges || [];
  const tasks = whiteboard?.tasks || [];
  const evidence = whiteboard?.evidence || [];
  const events = whiteboard?.events || [];
  const subscriptions = whiteboard?.subscriptions || [];
  const notifications = whiteboard?.notifications || [];
  const scheduleRequests = whiteboard?.schedule_requests || [];
  const workingTasks = tasks.filter((task) => ["running", "queued", "agent_queued", "scheduled"].includes(task.status));
  const waitingTasks = tasks.filter((task) => ["waiting", "blocked"].includes(task.status) || task.wait_reason);
  const pageActions = (
    <div className="flex flex-wrap gap-2">
      <Button icon={<PlayCircle className="h-4 w-4" />} loading={loading} disabled={!auditRun} onClick={onRunWhiteboardSwarm}>
        运行 Whiteboard Swarm
      </Button>
    </div>
  );

  return (
    <>
      <PageHeader title="Whiteboard" eyebrow="Swarm coordination" actions={pageActions} />
      {!auditRun ? (
        <Alert className="mb-5" tone="processing" title="No active AuditRun" description="Create or select an audit run before using the shared Whiteboard." />
      ) : null}
      <div className="mb-5 grid gap-4 md:grid-cols-3 xl:grid-cols-6">
        <MetricCard label="Cards" value={cards.length} />
        <MetricCard label="Edges" value={edges.length} />
        <MetricCard label="Tasks" value={tasks.length} />
        <MetricCard label="Events" value={events.length} />
        <MetricCard label="Pending notices" value={notifications.filter((item) => item.status === "pending").length} />
        <MetricCard label="Evidence" value={evidence.length} />
      </div>

      <div className="mb-5 grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
        <FlowCanvas
          title="Whiteboard Graph"
          description="Cards, evidence, findings, and Trace Worker outputs are connected as a traceable audit graph."
          nodes={flow.nodes}
          edges={flow.edges}
          height={620}
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
                        {selectedNode.data.status ? <Badge tone={statusTone(selectedNode.data.status)}>{selectedNode.data.status}</Badge> : null}
                        {selectedNode.data.group ? <Badge>{selectedNode.data.group}</Badge> : null}
                      </div>
                      <div>
                        <div className="font-medium text-slate-900">{selectedNode.data.label}</div>
                        <p className="mt-2 whitespace-pre-wrap leading-6 text-slate-600">{selectedNode.data.summary || "No content"}</p>
                      </div>
                    </div>
                  ),
                },
                {
                  key: "raw",
                  label: "Payload",
                  children: <pre className="max-h-[520px] overflow-auto rounded-lg bg-slate-950 p-3 text-xs text-slate-100">{JSON.stringify(selectedNode.data.raw, null, 2)}</pre>,
                },
              ]}
            />
          ) : (
            <EmptyState description="Select a whiteboard node" />
          )}
        </Panel>
      </div>

      <div className="mb-5 grid gap-4 xl:grid-cols-2">
        <Panel title="Graph Summary" dense>
          <p className="text-sm leading-6 text-slate-600">{whiteboard?.snapshot || "Whiteboard snapshot will appear after the first refresh."}</p>
        </Panel>
        <Panel title="Swarm Task Queues" dense>
          <div className="mb-4 grid gap-3 sm:grid-cols-4">
            <QueueStat label="Working" value={workingTasks.length} />
            <QueueStat label="Waiting" value={waitingTasks.length} />
            <QueueStat label="Subscriptions" value={subscriptions.length} />
            <QueueStat label="Requests" value={scheduleRequests.length} />
          </div>
          {workingTasks.length ? (
            <div className="grid gap-2">
              {workingTasks.slice(0, 5).map((task) => (
                <CompactRow key={task.task_id} title={`${task.agent_role} · ${task.agent_name}`} detail={task.prompt || task.task_id}>
                  <Badge tone="processing">{task.status}</Badge>
                </CompactRow>
              ))}
            </div>
          ) : (
            <EmptyState description="No working agents" />
          )}
        </Panel>
      </div>

      <div className="mb-5 grid gap-4 xl:grid-cols-2">
        <Panel title="Open Gaps" dense>
          <Rows
            empty="No open gaps"
            items={cards.filter((card) => card.card_type === "gap" && ["open", "needs_agent", "agent_queued"].includes(card.status))}
            render={(card) => <CompactRow key={card.card_id} title={card.title} detail={card.content || card.card_id}><Badge tone={statusTone(card.status)}>{card.status}</Badge></CompactRow>}
          />
        </Panel>
        <Panel title="Card Links" dense>
          <Rows
            empty="No card links"
            items={edges.slice(0, 8)}
            render={(edge) => (
              <CompactRow key={edge.edge_id} title={`${edge.source_card_id.slice(0, 8)} -> ${edge.target_card_id.slice(0, 8)}`} detail={edge.rationale || edge.edge_id}>
                <Badge>{edge.edge_type}</Badge>
              </CompactRow>
            )}
          />
        </Panel>
      </div>

      <Panel title="Swarm Board" dense>
        <Tabs
          items={[
            {
              key: "cards",
              label: "Cards",
              children: (
                <Rows
                  empty="No cards yet"
                  items={cards}
                  render={(card) => (
                    <article key={card.card_id} className="rounded-lg border border-slate-300 bg-slate-50 p-3">
                      <div className="mb-2 flex flex-wrap items-center gap-2">
                        <strong className="text-slate-900">{card.title}</strong>
                        <Badge>{card.card_type}</Badge>
                        <Badge tone={statusTone(card.status)}>{card.status}</Badge>
                      </div>
                      <p className="text-sm leading-6 text-slate-600">{card.content || "No content"}</p>
                      {renderCandidates(card.expected_predecessors)}
                      {renderCandidates(card.possible_successors)}
                      <p className="mt-2 text-xs text-slate-500">{card.file_path || card.finding_id || card.card_id}</p>
                    </article>
                  )}
                />
              ),
            },
            {
              key: "edges",
              label: "Edges",
              children: (
                <Rows
                  empty="No edges yet"
                  items={edges}
                  render={(edge) => (
                    <CompactRow key={edge.edge_id} title={`${edge.source_card_id} -> ${edge.target_card_id}`} detail={edge.rationale || edge.edge_id}>
                      <Badge>{edge.edge_type}</Badge>
                    </CompactRow>
                  )}
                />
              ),
            },
            {
              key: "tasks",
              label: "Tasks",
              children: (
                <Rows
                  empty="No swarm tasks yet"
                  items={tasks}
                  render={(task) => (
                    <CompactRow key={task.task_id} title={task.agent_role} detail={task.prompt || task.task_id}>
                      <Badge>{task.agent_name}</Badge>
                      <Badge>{task.task_group || "default"}</Badge>
                      <Badge tone={statusTone(task.status)}>{task.status}</Badge>
                      {task.wait_reason ? <Badge tone="warning"><Clock className="h-3 w-3" />{task.wait_reason}</Badge> : null}
                      <Badge>r{task.round_index}/a{task.attempt_index}</Badge>
                    </CompactRow>
                  )}
                />
              ),
            },
            {
              key: "events",
              label: "Events",
              children: (
                <Rows
                  empty="No events yet"
                  items={events}
                  render={(event) => (
                    <CompactRow key={event.event_id} title={event.summary || event.event_id} detail={event.created_at || event.entity_id}>
                      <Badge>{event.entity_type}</Badge>
                      <Badge>{event.event_type}</Badge>
                    </CompactRow>
                  )}
                />
              ),
            },
            {
              key: "notifications",
              label: "Listeners",
              children: (
                <div className="grid gap-4 xl:grid-cols-2">
                  <Panel title="Subscriptions" dense>
                    <Rows
                      empty="No subscriptions"
                      items={subscriptions}
                      render={(item) => <CompactRow key={item.subscription_id} title={item.subscriber_agent_run_id || item.subscriber_task_id || item.subscription_id} detail={JSON.stringify(item.filter || {})}><Badge>{item.status}</Badge></CompactRow>}
                    />
                  </Panel>
                  <Panel title="Notifications" dense>
                    <Rows
                      empty="No notifications"
                      items={notifications}
                      render={(item) => <CompactRow key={item.notification_id} title={item.summary || item.notification_id} detail={item.subscriber_agent_run_id || item.event_id}><Badge>{item.status}</Badge></CompactRow>}
                    />
                  </Panel>
                </div>
              ),
            },
            {
              key: "requests",
              label: "Requests",
              children: (
                <Rows
                  empty="No schedule requests"
                  items={scheduleRequests}
                  render={(item) => (
                    <CompactRow key={item.request_id} title={item.goal} detail={item.reason || item.requested_by_agent_run_id || item.request_id}>
                      {item.suggested_agent_name ? <Badge>{item.suggested_agent_name}</Badge> : null}
                      <Badge tone={statusTone(item.status)}>{item.status}</Badge>
                    </CompactRow>
                  )}
                />
              ),
            },
            {
              key: "evidence",
              label: "Evidence",
              children: (
                <Rows
                  empty="No whiteboard evidence yet"
                  items={evidence}
                  render={(item) => <CompactRow key={item.evidence_id} title={item.summary || item.evidence_id} detail={item.artifact_path || item.finding_id} />}
                />
              ),
            },
          ]}
        />
      </Panel>
    </>
  );
}

function QueueStat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg border border-slate-300 bg-slate-50 p-3">
      <div className="text-xs font-medium text-slate-500">{label}</div>
      <div className="mt-1 text-xl font-semibold text-slate-950">{value}</div>
    </div>
  );
}

function CompactRow({ children, detail, title }: { children?: React.ReactNode; detail?: React.ReactNode; title: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-3 rounded-lg border border-slate-300 bg-white p-3">
      <div className="min-w-0">
        <div className="font-medium text-slate-900">{title}</div>
        {detail ? <div className="mt-1 max-w-[72ch] truncate text-sm text-slate-500">{detail}</div> : null}
      </div>
      {children ? <div className="flex flex-wrap gap-1">{children}</div> : null}
    </div>
  );
}

function Rows<T>({ empty, items, render }: { empty: string; items: T[]; render: (item: T) => React.ReactNode }) {
  if (!items.length) return <EmptyState description={empty} />;
  return <div className="grid gap-3">{items.map(render)}</div>;
}

function renderCandidates(items?: WhiteboardGraph["cards"][number]["expected_predecessors"]) {
  if (!items?.length) return null;
  return (
    <div className="mt-2 flex flex-wrap gap-1">
      {items.map((item, index) => (
        <Badge key={`${item.title || "candidate"}-${index}`}>
          {item.status}: {item.title || item.card_ids?.join(", ") || "candidate"}
          {item.agent_run_id ? ` · ${item.agent_run_id.slice(0, 8)}` : ""}
        </Badge>
      ))}
    </div>
  );
}
