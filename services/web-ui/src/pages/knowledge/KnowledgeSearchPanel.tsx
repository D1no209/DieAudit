import { Card, Form, Input, List, Tag, Typography } from "antd";
import type { FormInstance } from "antd/es/form";
import type { KnowledgeMatch } from "../../types";

const { Paragraph } = Typography;

type Props = {
  form: FormInstance;
  loading: boolean;
  matches: KnowledgeMatch[];
  selectedProjectId?: string;
  onSearch: (values: { query: string; project_id?: string; limit?: string }) => void;
};

export function KnowledgeSearchPanel({ form, loading, matches, selectedProjectId, onSearch }: Props) {
  return (
    <Card title="Search">
      <Form form={form} layout="vertical" onFinish={onSearch}>
        <Form.Item name="query" label="Query" rules={[{ required: true }]}>
          <Input.Search enterButton="检索" loading={loading} />
        </Form.Item>
        <Form.Item name="project_id" label="Project Filter">
          <Input placeholder={selectedProjectId || "optional"} />
        </Form.Item>
        <Form.Item name="limit" label="Limit" initialValue="8">
          <Input />
        </Form.Item>
      </Form>
      <List
        dataSource={matches}
        renderItem={(item) => (
          <List.Item>
            <List.Item.Meta
              title={<Typography.Text strong>{item.title || item.source_name}</Typography.Text>}
              description={
                <>
                  <Tag>{Number(item.score || 0).toFixed(3)}</Tag>
                  <Tag>{item.scope}</Tag>
                  <Paragraph ellipsis={{ rows: 4, expandable: true }}>{item.text}</Paragraph>
                </>
              }
            />
          </List.Item>
        )}
      />
    </Card>
  );
}
