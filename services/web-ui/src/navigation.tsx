import {
  ApiOutlined,
  BugOutlined,
  CloudServerOutlined,
  FileTextOutlined,
  FolderOpenOutlined,
  SafetyCertificateOutlined,
} from "@ant-design/icons";

export type AppView = "overview" | "projects" | "findings" | "runtime" | "knowledge" | "admin";

export const navigationItems = [
  { key: "overview", icon: <ApiOutlined />, label: "Overview" },
  { key: "projects", icon: <FolderOpenOutlined />, label: "Projects & Runs" },
  { key: "findings", icon: <BugOutlined />, label: "Findings" },
  { key: "runtime", icon: <CloudServerOutlined />, label: "Runtime" },
  { key: "knowledge", icon: <FileTextOutlined />, label: "Knowledge" },
  { key: "admin", icon: <SafetyCertificateOutlined />, label: "Admin" },
] satisfies Array<{ key: AppView; icon: React.ReactNode; label: string }>;
