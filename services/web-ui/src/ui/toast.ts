type ToastKind = "success" | "warning" | "error" | "info";

function notify(kind: ToastKind, text: string) {
  window.dispatchEvent(new CustomEvent("dieaudit-toast", { detail: { kind, text } }));
}

export const toast = {
  error: (text: string) => notify("error", text),
  info: (text: string) => notify("info", text),
  success: (text: string) => notify("success", text),
  warning: (text: string) => notify("warning", text),
};
