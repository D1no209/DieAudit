import { useEffect, useState } from "react";
import { Alert } from "./Alert";

type ToastItem = {
  id: number;
  kind: "success" | "warning" | "error" | "info";
  text: string;
};

export function ToastHost() {
  const [items, setItems] = useState<ToastItem[]>([]);

  useEffect(() => {
    function handle(event: Event) {
      const detail = (event as CustomEvent<Omit<ToastItem, "id">>).detail;
      const id = Date.now() + Math.random();
      setItems((current) => [...current, { id, ...detail }]);
      window.setTimeout(() => {
        setItems((current) => current.filter((item) => item.id !== id));
      }, 3200);
    }

    window.addEventListener("dieaudit-toast", handle);
    return () => window.removeEventListener("dieaudit-toast", handle);
  }, []);

  return (
    <div className="fixed right-4 top-4 z-[80] grid w-[min(380px,calc(100vw-32px))] gap-2">
      {items.map((item) => (
        <Alert key={item.id} tone={item.kind === "error" ? "danger" : item.kind === "info" ? "processing" : item.kind} title={item.text} />
      ))}
    </div>
  );
}
