import { cn } from "./utils";

type Props = {
  actions?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  dense?: boolean;
  interactive?: boolean;
  section?: boolean;
  title?: React.ReactNode;
};

export function Panel({ actions, children, className, dense, interactive, section, title }: Props) {
  return (
    <section
      className={cn(
        "rounded-lg border border-slate-300 bg-white",
        interactive ? "transition hover:border-slate-400 hover:shadow-sm hover:shadow-slate-200/80" : "",
        section ? "bg-slate-50/70" : "",
        className,
      )}
    >
      {title || actions ? (
        <header className={cn("flex flex-wrap items-center justify-between gap-3 border-b border-slate-200", dense ? "px-3 py-2" : "px-4 py-3")}>
          {title ? <h2 className="min-w-0 truncate text-sm font-semibold text-slate-950">{title}</h2> : <span />}
          {actions ? <div className="flex max-w-full flex-wrap items-center gap-2">{actions}</div> : null}
        </header>
      ) : null}
      <div className={cn(dense ? "p-3" : "p-4")}>{children}</div>
    </section>
  );
}
