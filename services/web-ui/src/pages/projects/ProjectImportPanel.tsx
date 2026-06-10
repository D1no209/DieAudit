import { Button, Card, Form, Input, Tabs, Upload } from "antd";
import type { FormInstance } from "antd/es/form";
import type { UploadFile } from "antd/es/upload/interface";

type Props = {
  gitForm: FormInstance;
  loading: boolean;
  zipFiles: UploadFile[];
  zipForm: FormInstance;
  onCreateGitProject: (values: { name: string; git_url: string; ref?: string }) => void;
  onSetZipFiles: (files: UploadFile[]) => void;
  onUploadZipProject: (values: { name: string }) => void;
};

export function ProjectImportPanel({
  gitForm,
  loading,
  zipFiles,
  zipForm,
  onCreateGitProject,
  onSetZipFiles,
  onUploadZipProject,
}: Props) {
  return (
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
                <Button htmlType="submit" type="primary" loading={loading}>
                  导入 Git
                </Button>
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
                <Button className="form-action" htmlType="submit" type="primary" loading={loading}>
                  上传 Zip
                </Button>
              </Form>
            ),
          },
        ]}
      />
    </Card>
  );
}
