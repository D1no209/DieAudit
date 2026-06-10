import { Button, Card, Form, Input, List, Table, Tag, Typography, Upload } from "antd";
import type { ColumnsType } from "antd/es/table";
import type { FormInstance } from "antd/es/form";
import type { UploadFile } from "antd/es/upload/interface";
import type { KnowledgeDocument, KnowledgeMatch } from "../types";
import { PageHeader } from "../components/PageHeader";

const { Paragraph } = Typography;

type Props = {
  knowledgeColumns: ColumnsType<KnowledgeDocument>;
  knowledgeDocuments: KnowledgeDocument[];
  knowledgeFiles: UploadFile[];
  knowledgeMatches: KnowledgeMatch[];
  knowledgeSearchForm: FormInstance;
  knowledgeUploadForm: FormInstance;
  loading: boolean;
  selectedProjectId?: string;
  onSearchKnowledge: (values: { query: string; project_id?: string; limit?: string }) => void;
  onSetKnowledgeFiles: (files: UploadFile[]) => void;
  onUploadKnowledgeDocument: (values: { title: string; scope?: string; project_id?: string }) => void;
};

export function KnowledgePage({
  knowledgeColumns,
  knowledgeDocuments,
  knowledgeFiles,
  knowledgeMatches,
  knowledgeSearchForm,
  knowledgeUploadForm,
  loading,
  selectedProjectId,
  onSearchKnowledge,
  onSetKnowledgeFiles,
  onUploadKnowledgeDocument,
}: Props) {
  return (
    <>
      <PageHeader title="Knowledge" />
      <div className="knowledge-grid section">
        <Card title="Knowledge Base">
          <Form form={knowledgeUploadForm} layout="vertical" onFinish={onUploadKnowledgeDocument}>
            <Form.Item name="title" label="Title" rules={[{ required: true }]}>
              <Input />
            </Form.Item>
            <Form.Item name="scope" label="Scope" initialValue="global">
              <Input placeholder="global or project" />
            </Form.Item>
            <Form.Item name="project_id" label="Project ID">
              <Input placeholder={selectedProjectId || "optional for project scope"} />
            </Form.Item>
            <Upload
              beforeUpload={() => false}
              maxCount={1}
              fileList={knowledgeFiles}
              onChange={({ fileList }) => onSetKnowledgeFiles(fileList)}
            >
              <Button>选择文档</Button>
            </Upload>
            <Button className="form-action" htmlType="submit" type="primary" loading={loading}>上传并索引</Button>
          </Form>
          <Table
            className="table-toolbar"
            rowKey="document_id"
            columns={knowledgeColumns}
            dataSource={knowledgeDocuments}
            pagination={{ pageSize: 6 }}
          />
        </Card>
        <Card title="Search">
          <Form form={knowledgeSearchForm} layout="vertical" onFinish={onSearchKnowledge}>
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
            dataSource={knowledgeMatches}
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
      </div>
    </>
  );
}
