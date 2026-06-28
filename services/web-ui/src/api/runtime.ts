import { bffGet } from "./bffClient";

export const runtimeApi = {
  readiness: () => bffGet<Record<string, unknown>>("/runtime/readiness"),
  managed: () => bffGet<Record<string, unknown>>("/runtime/managed"),
};
