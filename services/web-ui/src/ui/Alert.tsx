import { AlertCircle, CheckCircle2, Info, TriangleAlert } from "lucide-react";
import { cn } from "./utils";
import type { StatusTone } from "./types";

const toneClass: Record<StatusTone, string> = {
  neutral: "border-slate-300 bg-white text-slate-700",
  processing: "border-cyan-300 bg-cyan-50 text-cyan-900",
  success: "border-emerald-300 bg-emerald-50 text-emerald-900",
  warning: "border-amber-300 bg-amber-50 text-amber-950",
  danger: "border-red-300 bg-red-50 text-red-900",
};

function Icon({ tone }: { tone: StatusTone }) {
  if (tone === "success") return <CheckCircle2 className="h-4 w-4" />;
  if (tone === "warning") return <TriangleAlert className="h-4 w-4" />;
  if (tone === "danger") return <AlertCircle className="h-4 w-4" />;
  return <Info className="h-4 w-4" />;
}

export function Alert({
  children,
  className,
  description,
  title,
  tone = "neutral",
}: {
  children?: React.ReactNode;
  className?: string;
  description?: React.ReactNode;
  title?: React.ReactNode;
  tone?: StatusTone;
}) {
  return (
    <div className={cn("flex gap-3 rounded-lg border px-3.5 py-3 text-sm", toneClass[tone], className)}>
      <span className="mt-0.5 shrink-0">
        <Icon tone={tone} />
      </span>
      <div className="min-w-0">
        {title ? <div className="font-semibold">{title}</div> : null}
        {description ? <div className="mt-1 text-sm opacity-90">{description}</div> : null}
        {children}
      </div>
    </div>
  );
}
