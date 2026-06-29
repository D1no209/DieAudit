import * as SwitchPrimitive from "@radix-ui/react-switch";
import { cn } from "./utils";

export function SwitchField({
  defaultChecked,
  label,
  name,
}: {
  defaultChecked?: boolean;
  label: React.ReactNode;
  name: string;
}) {
  return (
    <label className="flex items-center justify-between gap-3 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm">
      <span className="font-medium text-slate-700">{label}</span>
      <SwitchPrimitive.Root
        name={name}
        defaultChecked={defaultChecked}
        className={cn("h-5 w-9 rounded-full bg-slate-300 outline-none transition data-[state=checked]:bg-blue-600")}
      >
        <SwitchPrimitive.Thumb className="block h-4 w-4 translate-x-0.5 rounded-full bg-white shadow transition data-[state=checked]:translate-x-4" />
      </SwitchPrimitive.Root>
    </label>
  );
}
