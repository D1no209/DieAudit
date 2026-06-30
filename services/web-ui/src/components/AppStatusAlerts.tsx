import { Alert } from "../ui";

type Props = {
  error?: string;
};

export function AppStatusAlerts({ error }: Props) {
  return (
    <div className="mb-5 grid gap-3">
      {error && <Alert tone="danger" title="运行错误" description={error} />}
    </div>
  );
}
