import { cn } from "./utils";

type Props = {
  actions?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  title?: React.ReactNode;
};

export function Panel({ actions, children, className, title }: Props) {
  return (
    <section className={cn("rounded-xl border border-slate-200 bg-white shadow-sm shadow-slate-200/60", className)}>
      {title || actions ? (
        <header className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-4 py-3">
          {title ? <h2 className="text-sm font-semibold text-slate-900">{title}</h2> : <span />}
          {actions}
        </header>
      ) : null}
      <div className="p-4">{children}</div>
    </section>
  );
}
