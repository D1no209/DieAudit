import * as DialogPrimitive from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { motion } from "motion/react";
import { Button } from "./Button";

export function Drawer({
  children,
  open,
  onOpenChange,
  title,
}: {
  children: React.ReactNode;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: React.ReactNode;
}) {
  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-40 bg-slate-950/35" />
        <DialogPrimitive.Content asChild>
          <motion.aside
            initial={{ x: 32, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            transition={{ duration: 0.18 }}
            className="fixed right-0 top-0 z-50 flex h-dvh w-[min(760px,100vw)] flex-col border-l border-slate-200 bg-white shadow-2xl"
          >
            <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4">
              <DialogPrimitive.Title className="text-base font-semibold text-slate-950">{title}</DialogPrimitive.Title>
              <DialogPrimitive.Close asChild>
                <Button size="sm" variant="ghost" aria-label="Close drawer" icon={<X className="h-4 w-4" />} />
              </DialogPrimitive.Close>
            </div>
            <div className="flex-1 overflow-auto p-5">{children}</div>
          </motion.aside>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
