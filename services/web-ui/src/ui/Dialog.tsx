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
        <DialogPrimitive.Overlay className="fixed inset-0 z-40 bg-slate-950/35" />
        <DialogPrimitive.Content asChild>
          <motion.div
            initial={{ opacity: 0, scale: 0.98, y: 8 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            transition={{ duration: 0.16 }}
            className="fixed left-1/2 top-1/2 z-50 max-h-[88dvh] w-[min(900px,calc(100vw-32px))] -translate-x-1/2 -translate-y-1/2 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-2xl"
          >
            <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4">
              <DialogPrimitive.Title className="text-base font-semibold text-slate-950">{title}</DialogPrimitive.Title>
              <DialogPrimitive.Close asChild>
                <Button size="sm" variant="ghost" aria-label="Close dialog" icon={<X className="h-4 w-4" />} />
              </DialogPrimitive.Close>
            </div>
            <div className="max-h-[calc(88dvh-64px)] overflow-auto p-5">{children}</div>
          </motion.div>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
