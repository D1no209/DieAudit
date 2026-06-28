import { bffGet } from "./bffClient";

export const reportsApi = {
  list: () => bffGet<unknown[]>("/reports"),
};
