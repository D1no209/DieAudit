import type { InputHTMLAttributes, TextareaHTMLAttributes } from "react";
import { cn } from "./utils";

const fieldClass =
  "w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 shadow-sm outline-none transition placeholder:text-slate-400 focus:border-blue-500 focus:ring-2 focus:ring-blue-100 disabled:bg-slate-100 disabled:text-slate-500";

export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cn(fieldClass, className)} {...props} />;
}

export function PasswordInput(props: InputHTMLAttributes<HTMLInputElement>) {
  return <Input type="password" {...props} />;
}

export function NumberInput(props: InputHTMLAttributes<HTMLInputElement>) {
  return <Input type="number" {...props} />;
}

export function Textarea({ className, ...props }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea className={cn(fieldClass, "min-h-24 resize-y", className)} {...props} />;
}

export function Field({ children, hint, label }: { children: React.ReactNode; hint?: React.ReactNode; label: React.ReactNode }) {
  return (
    <label className="grid gap-1.5 text-sm">
      <span className="font-medium text-slate-700">{label}</span>
      {children}
      {hint ? <span className="text-xs text-slate-500">{hint}</span> : null}
    </label>
  );
}
