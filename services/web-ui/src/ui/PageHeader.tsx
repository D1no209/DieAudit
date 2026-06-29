export function PageHeader({ actions, title }: { actions?: React.ReactNode; title: string }) {
  return (
    <div className="mb-5 flex min-h-10 flex-wrap items-center justify-between gap-3">
      <h1 className="text-2xl font-semibold tracking-tight text-slate-950">{title}</h1>
      {actions}
    </div>
  );
}
