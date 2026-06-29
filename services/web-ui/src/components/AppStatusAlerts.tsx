import { API_KEY_HEADER } from "../api";
import type { AuthStatus } from "../types";
import { Alert } from "../ui";

type Props = {
  apiKey: string;
  authStatus?: AuthStatus;
  error?: string;
};

export function AppStatusAlerts({ apiKey, authStatus, error }: Props) {
  return (
    <div className="mb-5 grid gap-3">
      {error && <Alert tone="danger" title="运行错误" description={error} />}
      {authStatus?.enabled && !apiKey.trim() && (
        <Alert
          tone="warning"
          title="API authentication is enabled"
          description={`Enter a key for ${authStatus.api_key_header || API_KEY_HEADER} before using runtime, project, audit, artifact, and knowledge APIs.`}
        />
      )}
    </div>
  );
}
