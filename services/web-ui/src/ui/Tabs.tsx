import * as TabsPrimitive from "@radix-ui/react-tabs";
import { cn } from "./utils";

export type TabItem = {
  key: string;
  label: React.ReactNode;
  children: React.ReactNode;
};

export function Tabs({ defaultValue, items }: { defaultValue?: string; items: TabItem[] }) {
  return (
    <TabsPrimitive.Root defaultValue={defaultValue || items[0]?.key}>
      <TabsPrimitive.List className="flex gap-1 overflow-x-auto border-b border-slate-200">
        {items.map((item) => (
          <TabsPrimitive.Trigger
            key={item.key}
            value={item.key}
            className={cn(
              "whitespace-nowrap border-b-2 border-transparent px-3 py-2 text-sm font-semibold text-slate-600 outline-none transition hover:text-slate-950",
              "data-[state=active]:border-cyan-800 data-[state=active]:text-cyan-900",
            )}
          >
            {item.label}
          </TabsPrimitive.Trigger>
        ))}
      </TabsPrimitive.List>
      {items.map((item) => (
        <TabsPrimitive.Content key={item.key} value={item.key} className="pt-4 outline-none">
          {item.children}
        </TabsPrimitive.Content>
      ))}
    </TabsPrimitive.Root>
  );
}
