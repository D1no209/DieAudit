import { Button, Card, Descriptions, Form, Input, Table, Tabs, Tag, Typography, Upload } from "antd";
import type { ColumnsType } from "antd/es/table";
import type { FormInstance } from "antd/es/form";
import type { UploadFile } from "antd/es/upload/interface";
import type { Project } from "../types";
import { PageHeader } from "../components/PageHeader";

const { Text } = Typography;

type Props = {
  gitForm: FormInstance;
  loading: boolean;
  projectColumns: ColumnsType<Project>;
  projects: Project[];
  selectedProject?: Project;
  selectedProjectId?: string;
  zipFiles: UploadFile[];
  zipForm: FormInstance;
  onCreateGitProject: (values: { name: string; git_url: string; ref?: string }) => void;
  onSelectProject: (projectId: string) => void;
  onSetZipFiles: (files: UploadFile[]) => void;
  onUploadZipProject: (values: { name: string }) => void;
};

export function ProjectsPage({
  gitForm,
  loading,
  projectColumns,
  projects,
  selectedProject,
  selectedProjectId,
  zipFiles,
  zipForm,
  onCreateGitProject,
  onSelectProject,
  onSetZipFiles,
  onUploadZipProject,
}: Props) {
  return (
    <>
      <PageHeader title="Projects" />

      <div className="workspace-grid section">
        <Card title="Import Project">
          <Tabs
            items={[
              {
                key: "git",
                label: "Git",
                children: (
                  <Form form={gitForm} layout="vertical" onFinish={onCreateGitProject}>
                    <Form.Item name="name" label="Name" rules={[{ required: true }]}>
                      <Input />
                    </Form.Item>
                    <Form.Item name="git_url" label="Git URL" rules={[{ required: true }]}>
                      <Input />
                    </Form.Item>
                    <Form.Item name="ref" label="Ref">
                      <Input />
                    </Form.Item>
                    <Button htmlType="submit" type="primary" loading={loading}>导入 Git</Button>
                  </Form>
                ),
              },
              {
                key: "zip",
                label: "Zip",
                children: (
                  <Form form={zipForm} layout="vertical" onFinish={onUploadZipProject}>
                    <Form.Item name="name" label="Name" rules={[{ required: true }]}>
                      <Input />
                    </Form.Item>
                    <Upload beforeUpload={() => false} maxCount={1} fileList={zipFiles} onChange={({ fileList }) => onSetZipFiles(fileList)}>
                      <Button>选择 zip</Button>
                    </Upload>
                    <Button className="form-action" htmlType="submit" type="primary" loading={loading}>上传 Zip</Button>
                  </Form>
                ),
              },
            ]}
          />
        </Card>
        <Card title="Selected Project">
          <Descriptions bordered size="small" column={1}>
            <Descriptions.Item label="Name">{selectedProject?.name || "-"}</Descriptions.Item>
            <Descriptions.Item label="Project ID">{selectedProject?.project_id || "-"}</Descriptions.Item>
            <Descriptions.Item label="Source">{selectedProject?.source_type || "-"}</Descriptions.Item>
            <Descriptions.Item label="Status">
              {selectedProject?.status ? <Tag color={selectedProject.status === "ready" ? "green" : "blue"}>{selectedProject.status}</Tag> : "-"}
            </Descriptions.Item>
          </Descriptions>
          <Text type="secondary" className="block-hint">
            选择项目后，在 Audit Runs 页面启动审计闭环并查看运行结果。
          </Text>
        </Card>
      </div>

      <Card className="section" title="Project Inventory">
          <Table
            rowKey="project_id"
            size="small"
            columns={projectColumns}
            dataSource={projects}
            pagination={{ pageSize: 10 }}
            rowSelection={{ type: "radio", selectedRowKeys: selectedProjectId ? [selectedProjectId] : [], onChange: ([key]) => onSelectProject(String(key)) }}
          />
      </Card>
    </>
  );
}
