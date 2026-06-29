import type { ReactNode } from "react";

export type StatusTone = "neutral" | "success" | "warning" | "danger" | "processing";

export type DataColumn<T> = {
  key?: string;
  title: ReactNode;
  dataIndex?: keyof T;
  width?: string | number;
  className?: string;
  render?: (value: unknown, row: T, index: number) => ReactNode;
};

export type TablePagination = {
  pageSize?: number;
};

export type FileSelection = File[];

export type FormSubmitHandler<T> = (values: T) => void | Promise<void>;
