import { cn } from "./utils";
import type { StatusTone } from "./types";

const tones: Record<StatusTone, string> = {
  neutral: "border-slate-300 bg-slate-100 text-slate-700",
  success: "border-emerald-300 bg-emerald-50 text-emerald-800",
  warning: "border-amber-300 bg-amber-50 text-amber-900",
  danger: "border-red-300 bg-red-50 text-red-800",
  processing: "border-cyan-300 bg-cyan-50 text-cyan-900",
};

export function Badge({
  children,
  className,
  tone = "neutral",
}: {
  children: React.ReactNode;
  className?: string;
  tone?: StatusTone;
}) {
  return (
    <span
      className={cn(
        "inline-flex max-w-full items-center gap-1 rounded px-1.5 py-0.5 text-[11px] font-semibold leading-5",
        "border tabular-nums",
        tones[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}
