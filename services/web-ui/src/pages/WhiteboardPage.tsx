import { BranchesOutlined, ClockCircleOutlined, NodeIndexOutlined, PlayCircleOutlined } from "@ant-design/icons";
import { Alert, Button, Card, Descriptions, Empty, List, Space, Tabs, Tag, Timeline, Typography } from "antd";
import type { AuditRun, WhiteboardGraph } from "../types";
import { PageHeader } from "../components/PageHeader";

const { Paragraph, Text } = Typography;

type Props = {
  auditRun?: AuditRun;
  loading: boolean;
  whiteboard?: WhiteboardGraph;
  onRunWhiteboardSwarm: () => void;
};

export function WhiteboardPage({ auditRun, loading, whiteboard, onRunWhiteboardSwarm }: Props) {
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
  const renderCandidates = (items?: WhiteboardGraph["cards"][number]["expected_predecessors"]) => {
    if (!items?.length) {
      return null;
    }
    return (
      <Space wrap>
        {items.map((item, index) => (
          <Tag key={`${item.title || "candidate"}-${index}`}>
            {item.status}: {item.title || item.card_ids?.join(", ") || "candidate"}
            {item.agent_run_id ? ` · ${item.agent_run_id.slice(0, 8)}` : ""}
          </Tag>
        ))}
      </Space>
    );
  };
  const pageActions = (
    <div className="action-bar">
      <Button icon={<PlayCircleOutlined />} loading={loading} disabled={!auditRun} onClick={onRunWhiteboardSwarm}>
        运行 Whiteboard Swarm
      </Button>
    </div>
  );

  return (
    <>
      <PageHeader title="Whiteboard" actions={pageActions} />
      {!auditRun && (
        <Alert
          className="section"
          type="info"
          showIcon
          message="No active AuditRun"
          description="Create or select an audit run before using the shared Whiteboard."
        />
      )}
      <div className="content-grid section">
        <Card title="Graph Summary">
          <Space wrap>
            <Tag icon={<NodeIndexOutlined />}>{cards.length} cards</Tag>
            <Tag>{edges.length} edges</Tag>
            <Tag>{tasks.length} tasks</Tag>
            <Tag>{events.length} events</Tag>
            <Tag>{notifications.filter((item) => item.status === "pending").length} pending notices</Tag>
            <Tag>{evidence.length} evidence</Tag>
          </Space>
          <Paragraph className="panel-description">
            {whiteboard?.snapshot || "Whiteboard snapshot will appear after the first refresh."}
          </Paragraph>
        </Card>
        <Card title="Agent Queues">
          <Descriptions column={2} size="small">
            <Descriptions.Item label="Working">{workingTasks.length}</Descriptions.Item>
            <Descriptions.Item label="Waiting">{waitingTasks.length}</Descriptions.Item>
            <Descriptions.Item label="Subscriptions">{subscriptions.length}</Descriptions.Item>
            <Descriptions.Item label="Requests">{scheduleRequests.length}</Descriptions.Item>
          </Descriptions>
          <List
            size="small"
            dataSource={workingTasks.slice(0, 5)}
            locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No working agents" /> }}
            renderItem={(task) => (
              <List.Item>
                <List.Item.Meta title={`${task.agent_role} · ${task.agent_name}`} description={task.prompt || task.task_id} />
                <Tag color="processing">{task.status}</Tag>
              </List.Item>
            )}
          />
        </Card>
      </div>
      <div className="content-grid section">
        <Card title="Open Gaps">
          <List
            locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No open gaps" /> }}
            dataSource={cards.filter((card) => card.card_type === "gap" && ["open", "needs_agent", "agent_queued"].includes(card.status))}
            renderItem={(card) => (
              <List.Item>
                <List.Item.Meta title={card.title} description={card.content || card.card_id} />
                <Tag>{card.status}</Tag>
              </List.Item>
            )}
          />
        </Card>
        <Card title="Card Links">
          <List
            size="small"
            dataSource={edges.slice(0, 8)}
            locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No card links" /> }}
            renderItem={(edge) => (
              <List.Item>
                <List.Item.Meta title={`${edge.source_card_id.slice(0, 8)} -> ${edge.target_card_id.slice(0, 8)}`} description={edge.rationale || edge.edge_id} />
                <Tag icon={<BranchesOutlined />}>{edge.edge_type}</Tag>
              </List.Item>
            )}
          />
        </Card>
      </div>
      <Card className="section">
        <Tabs
          items={[
            {
              key: "cards",
              label: "Cards",
              children: (
                <List
                  dataSource={cards}
                  locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No cards yet" /> }}
                  renderItem={(card) => (
                    <List.Item>
                      <List.Item.Meta
                        title={<Space><Text strong>{card.title}</Text><Tag>{card.card_type}</Tag><Tag>{card.status}</Tag></Space>}
                        description={
                          <>
                            <Paragraph>{card.content || "No content"}</Paragraph>
                            {renderCandidates(card.expected_predecessors)}
                            {renderCandidates(card.possible_successors)}
                            <Text type="secondary">{card.file_path || card.finding_id || card.card_id}</Text>
                          </>
                        }
                      />
                    </List.Item>
                  )}
                />
              ),
            },
            {
              key: "edges",
              label: "Edges",
              children: (
                <List
                  dataSource={edges}
                  locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No edges yet" /> }}
                  renderItem={(edge) => (
                    <List.Item>
                      <List.Item.Meta title={`${edge.source_card_id} -> ${edge.target_card_id}`} description={edge.rationale || edge.edge_id} />
                      <Tag>{edge.edge_type}</Tag>
                    </List.Item>
                  )}
                />
              ),
            },
            {
              key: "tasks",
              label: "Agents",
              children: (
                <List
                  dataSource={tasks}
                  locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No swarm tasks yet" /> }}
                  renderItem={(task) => (
                    <List.Item>
                      <List.Item.Meta
                        title={<Space><Text strong>{task.agent_role}</Text><Tag>{task.agent_name}</Tag><Tag>{task.task_group || "default"}</Tag></Space>}
                        description={
                          <>
                            <Paragraph>{task.prompt || task.task_id}</Paragraph>
                            <Text type="secondary">
                              {task.parent_task_id ? `parent ${task.parent_task_id.slice(0, 8)} · ` : ""}
                              {task.card_id || task.gap_card_id || task.agent_run_id || task.task_id}
                            </Text>
                          </>
                        }
                      />
                      <Space>
                        <Tag>{task.status}</Tag>
                        {task.wait_reason && <Tag icon={<ClockCircleOutlined />}>{task.wait_reason}</Tag>}
                        <Tag>r{task.round_index}/a{task.attempt_index}</Tag>
                      </Space>
                    </List.Item>
                  )}
                />
              ),
            },
            {
              key: "events",
              label: "Events",
              children: (
                <Timeline
                  items={events.map((event) => ({
                    children: (
                      <Space direction="vertical" size={2}>
                        <Space wrap>
                          <Text strong>{event.summary || event.event_id}</Text>
                          <Tag>{event.entity_type}</Tag>
                          <Tag>{event.event_type}</Tag>
                        </Space>
                        <Text type="secondary">{event.created_at || event.entity_id}</Text>
                      </Space>
                    ),
                  }))}
                />
              ),
            },
            {
              key: "notifications",
              label: "Listeners",
              children: (
                <div className="content-grid">
                  <List
                    header={<Text strong>Subscriptions</Text>}
                    dataSource={subscriptions}
                    locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No subscriptions" /> }}
                    renderItem={(item) => (
                      <List.Item>
                        <List.Item.Meta title={item.subscriber_agent_run_id || item.subscriber_task_id || item.subscription_id} description={JSON.stringify(item.filter || {})} />
                        <Tag>{item.status}</Tag>
                      </List.Item>
                    )}
                  />
                  <List
                    header={<Text strong>Notifications</Text>}
                    dataSource={notifications}
                    locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No notifications" /> }}
                    renderItem={(item) => (
                      <List.Item>
                        <List.Item.Meta title={item.summary || item.notification_id} description={item.subscriber_agent_run_id || item.event_id} />
                        <Tag>{item.status}</Tag>
                      </List.Item>
                    )}
                  />
                </div>
              ),
            },
            {
              key: "requests",
              label: "Requests",
              children: (
                <List
                  dataSource={scheduleRequests}
                  locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No schedule requests" /> }}
                  renderItem={(item) => (
                    <List.Item>
                      <List.Item.Meta title={item.goal} description={item.reason || item.requested_by_agent_run_id || item.request_id} />
                      <Space>
                        {item.suggested_agent_name && <Tag>{item.suggested_agent_name}</Tag>}
                        <Tag>{item.status}</Tag>
                      </Space>
                    </List.Item>
                  )}
                />
              ),
            },
            {
              key: "evidence",
              label: "Evidence",
              children: (
                <List
                  dataSource={evidence}
                  locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No whiteboard evidence yet" /> }}
                  renderItem={(item) => (
                    <List.Item>
                      <List.Item.Meta title={item.summary || item.evidence_id} description={item.artifact_path || item.finding_id} />
                    </List.Item>
                  )}
                />
              ),
            },
          ]}
        />
      </Card>
    </>
  );
}
