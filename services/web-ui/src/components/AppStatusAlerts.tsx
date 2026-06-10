import { Alert } from "antd";
import { API_KEY_HEADER } from "../api";
import type { AuthStatus } from "../types";

type Props = {
  apiKey: string;
  authStatus?: AuthStatus;
  error?: string;
};

export function AppStatusAlerts({ apiKey, authStatus, error }: Props) {
  return (
    <>
      {error && <Alert type="error" showIcon message="运行错误" description={error} className="section" />}
      {authStatus?.enabled && !apiKey.trim() && (
        <Alert
          type="warning"
          showIcon
          message="API authentication is enabled"
          description={`Enter a key for ${authStatus.api_key_header || API_KEY_HEADER} before using runtime, project, audit, artifact, and knowledge APIs.`}
          className="section"
        />
      )}
    </>
  );
}
