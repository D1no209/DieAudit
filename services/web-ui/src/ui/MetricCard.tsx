import type { ReactNode } from "react";
import { motion } from "motion/react";

export function MetricCard({
  icon,
  label,
  value,
  detail,
}: {
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
      className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm shadow-slate-200/60"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-xs font-medium text-slate-500">{label}</div>
          <div className="mt-2 truncate text-2xl font-semibold tracking-tight text-slate-950">{value}</div>
        </div>
        {icon ? <div className="rounded-lg border border-slate-200 bg-slate-50 p-2 text-slate-600">{icon}</div> : null}
      </div>
      {detail ? <div className="mt-3 text-sm text-slate-600">{detail}</div> : null}
    </motion.div>
  );
}
