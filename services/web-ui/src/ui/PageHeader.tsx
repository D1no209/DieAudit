export function PageHeader({ actions, eyebrow, title }: { actions?: React.ReactNode; eyebrow?: React.ReactNode; title: string }) {
  return (
    <div className="mb-4 flex min-h-10 flex-wrap items-center justify-between gap-3 border-b border-slate-200 pb-3">
      <div className="min-w-0">
        {eyebrow ? <div className="mb-1 text-[11px] font-semibold uppercase text-slate-500">{eyebrow}</div> : null}
        <h1 className="truncate text-lg font-semibold tracking-tight text-slate-950">{title}</h1>
      </div>
      {actions ? <div className="flex max-w-full flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  );
}
