import { cn } from "./utils";
import type { StatusTone } from "./types";

const tones: Record<StatusTone, string> = {
  neutral: "border-slate-200 bg-slate-100 text-slate-700",
  success: "border-emerald-200 bg-emerald-50 text-emerald-700",
  warning: "border-amber-200 bg-amber-50 text-amber-800",
  danger: "border-red-200 bg-red-50 text-red-700",
  processing: "border-blue-200 bg-blue-50 text-blue-700",
};

export function Badge({ children, className, tone = "neutral" }: { children: React.ReactNode; className?: string; tone?: StatusTone }) {
  return (
    <span className={cn("inline-flex max-w-full items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium", tones[tone], className)}>
      {children}
    </span>
  );
}
