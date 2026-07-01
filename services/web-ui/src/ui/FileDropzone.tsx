import { Upload } from "lucide-react";

export function FileDropzone({
  accept,
  name = "file",
  onFilesChange,
}: {
  accept?: string;
  name?: string;
  onFilesChange: (files: File[]) => void;
}) {
  return (
    <label className="flex cursor-pointer flex-col items-center justify-center rounded-lg border border-dashed border-slate-300 bg-slate-50 px-4 py-6 text-center text-sm text-slate-600 transition hover:border-cyan-700 hover:bg-cyan-50/50">
      <Upload className="mb-2 h-5 w-5 text-slate-500" />
      <span className="font-medium text-slate-800">Choose file</span>
      <span className="mt-1 text-xs text-slate-500">{accept || "Any supported file"}</span>
      <input
        name={name}
        type="file"
        accept={accept}
        className="sr-only"
        onChange={(event) => onFilesChange(Array.from(event.currentTarget.files || []))}
      />
    </label>
  );
}
