import { bffGet } from "./bffClient";

export const findingsApi = {
  list: () => bffGet<unknown[]>("/findings"),
};
