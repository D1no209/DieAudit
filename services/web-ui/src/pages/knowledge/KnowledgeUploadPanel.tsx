import { Button, Card, Form, Input, Upload } from "antd";
import type { FormInstance } from "antd/es/form";
import type { UploadFile } from "antd/es/upload/interface";

type Props = {
  files: UploadFile[];
  form: FormInstance;
  loading: boolean;
  selectedProjectId?: string;
  onSetFiles: (files: UploadFile[]) => void;
  onUpload: (values: { title: string; scope?: string; project_id?: string }) => void;
};

export function KnowledgeUploadPanel({ files, form, loading, selectedProjectId, onSetFiles, onUpload }: Props) {
  return (
    <Card title="Upload Document">
      <Form form={form} layout="vertical" onFinish={onUpload}>
        <Form.Item name="title" label="Title" rules={[{ required: true }]}>
          <Input />
        </Form.Item>
        <Form.Item name="scope" label="Scope" initialValue="global">
          <Input placeholder="global or project" />
        </Form.Item>
        <Form.Item name="project_id" label="Project ID">
          <Input placeholder={selectedProjectId || "optional for project scope"} />
        </Form.Item>
        <Upload beforeUpload={() => false} maxCount={1} fileList={files} onChange={({ fileList }) => onSetFiles(fileList)}>
          <Button>选择文档</Button>
        </Upload>
        <Button className="form-action" htmlType="submit" type="primary" loading={loading}>
          上传并索引
        </Button>
      </Form>
    </Card>
  );
}
