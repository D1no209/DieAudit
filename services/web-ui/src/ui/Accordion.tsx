import * as AccordionPrimitive from "@radix-ui/react-accordion";
import { ChevronDown } from "lucide-react";

export function Accordion({ items }: { items: Array<{ key: string; title: React.ReactNode; children: React.ReactNode }> }) {
  return (
    <AccordionPrimitive.Root type="multiple" className="grid gap-2">
      {items.map((item) => (
        <AccordionPrimitive.Item key={item.key} value={item.key} className="overflow-hidden rounded-lg border border-slate-200 bg-white">
          <AccordionPrimitive.Header>
            <AccordionPrimitive.Trigger className="flex w-full items-center justify-between px-3 py-2 text-left text-sm font-medium text-slate-800 hover:bg-slate-50">
              {item.title}
              <ChevronDown className="h-4 w-4 transition data-[state=open]:rotate-180" />
            </AccordionPrimitive.Trigger>
          </AccordionPrimitive.Header>
          <AccordionPrimitive.Content className="border-t border-slate-200 p-3 text-sm text-slate-700">{item.children}</AccordionPrimitive.Content>
        </AccordionPrimitive.Item>
      ))}
    </AccordionPrimitive.Root>
  );
}
