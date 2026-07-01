import * as CheckboxPrimitive from "@radix-ui/react-checkbox";
import { Check } from "lucide-react";

export function CheckboxGroup({
  defaultValue = [],
  name,
  options,
}: {
  defaultValue?: string[];
  name: string;
  options: Array<{ label: React.ReactNode; value: string }>;
}) {
  return (
    <div className="grid gap-2 sm:grid-cols-2">
      {options.map((option) => (
        <label key={option.value} className="flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-700">
          <CheckboxPrimitive.Root
            name={name}
            value={option.value}
            defaultChecked={defaultValue.includes(option.value)}
            className="flex h-4 w-4 items-center justify-center rounded border border-slate-300 bg-white data-[state=checked]:border-cyan-900 data-[state=checked]:bg-cyan-900"
          >
            <CheckboxPrimitive.Indicator>
              <Check className="h-3 w-3 text-white" />
            </CheckboxPrimitive.Indicator>
          </CheckboxPrimitive.Root>
          {option.label}
        </label>
      ))}
    </div>
  );
}
