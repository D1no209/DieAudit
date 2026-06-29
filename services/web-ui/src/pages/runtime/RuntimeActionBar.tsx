import { Trash2 } from "lucide-react";
import { Button } from "../../ui";

type Props = {
  loading: boolean;
  onCleanup: () => void;
  onCleanupExpiredRuntime: () => void;
};

export function RuntimeActionBar({ loading, onCleanup, onCleanupExpiredRuntime }: Props) {
  return (
    <div className="flex flex-wrap gap-2">
      <Button icon={<Trash2 className="h-4 w-4" />} loading={loading} onClick={onCleanupExpiredRuntime}>清理过期运行时</Button>
      <Button variant="danger" icon={<Trash2 className="h-4 w-4" />} loading={loading} onClick={onCleanup}>清理当前运行时</Button>
    </div>
  );
}
