export function cn(...values: Array<string | false | null | undefined>) {
  return values.filter(Boolean).join(" ");
}

export function fieldValue(formData: FormData, name: string) {
  const value = formData.get(name);
  return typeof value === "string" ? value : undefined;
}

export function numberFieldValue(formData: FormData, name: string) {
  const value = fieldValue(formData, name);
  if (value === undefined || value === "") {
    return undefined;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : undefined;
}

export function checkedFieldValue(formData: FormData, name: string) {
  return formData.get(name) === "on" || formData.get(name) === "true";
}
