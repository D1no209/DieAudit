import type { ReactNode } from "react";
import { motion } from "motion/react";
import { cn } from "./utils";

export function MetricCard({
  className,
  icon,
  label,
  value,
  detail,
}: {
  className?: string;
  detail?: ReactNode;
  icon?: ReactNode;
  label: ReactNode;
  value: ReactNode;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.18 }}
      className={cn("rounded-lg border border-slate-300 bg-white p-3", className)}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-[11px] font-semibold uppercase text-slate-500">{label}</div>
          <div className="mt-1 truncate text-xl font-semibold tracking-tight text-slate-950">{value}</div>
        </div>
        {icon ? <div className="rounded-md border border-slate-300 bg-slate-100 p-1.5 text-slate-600">{icon}</div> : null}
      </div>
      {detail ? <div className="mt-2 min-w-0 text-xs text-slate-600">{detail}</div> : null}
    </motion.div>
  );
}
