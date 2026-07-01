import * as DialogPrimitive from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { motion } from "motion/react";
import { Button } from "./Button";

export function Dialog({
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
        <DialogPrimitive.Overlay className="fixed inset-0 z-40 bg-slate-950/45" />
        <DialogPrimitive.Content asChild>
          <motion.div
            initial={{ opacity: 0, scale: 0.98, y: 8 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            transition={{ duration: 0.16 }}
            className="fixed left-1/2 top-1/2 z-50 max-h-[88dvh] w-[min(960px,calc(100vw-24px))] -translate-x-1/2 -translate-y-1/2 overflow-hidden rounded-lg border border-slate-300 bg-white shadow-2xl shadow-slate-950/20"
          >
            <div className="flex items-center justify-between border-b border-slate-200 bg-slate-50 px-4 py-3">
              <DialogPrimitive.Title className="min-w-0 truncate text-sm font-semibold text-slate-950">{title}</DialogPrimitive.Title>
              <DialogPrimitive.Close asChild>
                <Button size="icon" variant="ghost" aria-label="Close dialog" icon={<X className="h-4 w-4" />} />
              </DialogPrimitive.Close>
            </div>
            <div className="max-h-[calc(88dvh-57px)] overflow-auto p-4">{children}</div>
          </motion.div>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
