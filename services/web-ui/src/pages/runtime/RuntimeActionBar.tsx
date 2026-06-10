import { DeleteOutlined } from "@ant-design/icons";
import { Button } from "antd";

type Props = {
  loading: boolean;
  onCleanup: () => void;
  onCleanupExpiredRuntime: () => void;
};

export function RuntimeActionBar({
  loading,
  onCleanup,
  onCleanupExpiredRuntime,
}: Props) {
  return (
    <div className="action-bar">
      <Button icon={<DeleteOutlined />} loading={loading} onClick={onCleanupExpiredRuntime}>
        清理过期运行时
      </Button>
      <Button danger icon={<DeleteOutlined />} loading={loading} onClick={onCleanup}>
        清理当前运行时
      </Button>
    </div>
  );
}
