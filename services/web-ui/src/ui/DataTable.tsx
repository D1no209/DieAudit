import { useMemo, useState } from "react";
import { Button } from "./Button";
import { EmptyState } from "./EmptyState";
import type { DataColumn, TablePagination } from "./types";
import { cn } from "./utils";

type Props<T> = {
  columns: DataColumn<T>[];
  data: T[];
  getRowKey: (row: T) => string | number;
  onRowClick?: (row: T) => void;
  pagination?: false | TablePagination;
  selectedRowKey?: string | number;
};

export function DataTable<T>({ columns, data, getRowKey, onRowClick, pagination, selectedRowKey }: Props<T>) {
  const pageSize = pagination === false ? data.length || 1 : pagination?.pageSize || 10;
  const [page, setPage] = useState(1);
  const pageCount = Math.max(1, Math.ceil(data.length / pageSize));
  const visibleRows = useMemo(() => {
    if (pagination === false) return data;
    const start = (Math.min(page, pageCount) - 1) * pageSize;
    return data.slice(start, start + pageSize);
  }, [data, page, pageCount, pageSize, pagination]);

  return (
    <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-slate-200 text-left text-sm">
          <thead className="bg-slate-50 text-xs font-semibold uppercase text-slate-500">
            <tr>
              {columns.map((column) => (
                <th key={column.key || String(column.dataIndex) || String(column.title)} style={{ width: column.width }} className={cn("px-3 py-2.5", column.className)}>
                  {column.title}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {visibleRows.map((row, index) => {
              const key = getRowKey(row);
              return (
                <tr
                  key={key}
                  onClick={() => onRowClick?.(row)}
                  className={cn(
                    "transition",
                    onRowClick ? "cursor-pointer hover:bg-blue-50/60" : "hover:bg-slate-50/70",
                    selectedRowKey === key && "bg-blue-50",
                  )}
                >
                  {columns.map((column) => {
                    const value = column.dataIndex ? row[column.dataIndex] : undefined;
                    return (
                      <td key={column.key || String(column.dataIndex) || String(column.title)} className={cn("max-w-[380px] px-3 py-3 align-top text-slate-700", column.className)}>
                        {column.render ? column.render(value, row, index) : String(value ?? "-")}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {!data.length ? <div className="p-4"><EmptyState /></div> : null}
      {pagination !== false && data.length > pageSize ? (
        <div className="flex items-center justify-between border-t border-slate-200 px-3 py-2 text-xs text-slate-500">
          <span>
            Page {Math.min(page, pageCount)} of {pageCount}
          </span>
          <div className="flex gap-2">
            <Button size="sm" disabled={page <= 1} onClick={() => setPage((value) => Math.max(1, value - 1))}>
              Prev
            </Button>
            <Button size="sm" disabled={page >= pageCount} onClick={() => setPage((value) => Math.min(pageCount, value + 1))}>
              Next
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
