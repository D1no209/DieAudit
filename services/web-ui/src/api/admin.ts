import { bffGet } from "./bffClient";

export const adminApi = {
  auditEvents: () => bffGet<unknown[]>("/admin/audit-events"),
};
