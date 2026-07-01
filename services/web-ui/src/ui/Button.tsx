import type { ButtonHTMLAttributes, ReactNode } from "react";
import { Loader2 } from "lucide-react";
import { cn } from "./utils";

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger" | "link";
type ButtonSize = "icon" | "sm" | "md" | "lg";

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  icon?: ReactNode;
  loading?: boolean;
  size?: ButtonSize;
  variant?: ButtonVariant;
};

const variants: Record<ButtonVariant, string> = {
  primary: "border-cyan-900 bg-cyan-900 text-white hover:bg-cyan-950",
  secondary: "border-slate-300 bg-white text-slate-800 hover:border-slate-400 hover:bg-slate-50",
  ghost: "border-transparent bg-transparent text-slate-700 hover:bg-slate-200/70 hover:text-slate-950",
  danger: "border-red-700 bg-red-700 text-white hover:bg-red-800",
  link: "border-transparent bg-transparent px-1 text-cyan-800 hover:text-cyan-950",
};

const sizes: Record<ButtonSize, string> = {
  icon: "h-8 w-8 p-0 text-xs",
  sm: "h-8 px-3 text-xs",
  md: "h-9 px-3.5 text-sm",
  lg: "h-10 px-4 text-sm",
};

export function Button({ children, className, disabled, icon, loading, size = "md", type = "button", variant = "secondary", ...props }: Props) {
  return (
    <button
      type={type}
      disabled={disabled || loading}
      className={cn(
        "inline-flex max-w-full shrink-0 items-center justify-center gap-2 whitespace-nowrap rounded-md border font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-800 focus-visible:ring-offset-2 active:translate-y-px disabled:opacity-55",
        sizes[size],
        variants[variant],
        className,
      )}
      {...props}
    >
      {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : icon}
      {children}
    </button>
  );
}
