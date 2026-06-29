import { Bug, RefreshCw } from "lucide-react";
import type { AppView } from "../navigation";
import { API_KEY_HEADER } from "../api";
import type { NavigationItem } from "../navigation";
import { Button, PasswordInput } from "../ui";
import { cn } from "../ui/utils";

type Props = {
  activeView: AppView;
  apiKey: string;
  authHeaderName?: string;
  navigationItems: NavigationItem[];
  onApiKeyChange: (value: string) => void;
  onRefresh: () => void;
  onSaveApiKey: () => void;
  onViewChange: (view: AppView) => void;
};

export function AppHeader({
  activeView,
  apiKey,
  authHeaderName,
  navigationItems,
  onApiKeyChange,
  onRefresh,
  onSaveApiKey,
  onViewChange,
}: Props) {
  return (
    <header className="sticky top-0 z-30 border-b border-slate-200 bg-white/95 px-4 py-3 backdrop-blur sm:px-6 lg:px-8">
      <div className="mx-auto flex max-w-[1440px] flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-700 text-white shadow-sm">
            <Bug className="h-5 w-5" />
          </span>
          <div>
            <h1 className="m-0 text-lg font-semibold leading-tight text-slate-950">DieAudit</h1>
            <p className="m-0 text-xs text-slate-500">多 Agent 代码审计运行台</p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <PasswordInput
            className="h-9 w-48"
            placeholder={authHeaderName || API_KEY_HEADER}
            value={apiKey}
            onChange={(event) => onApiKeyChange(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") onSaveApiKey();
            }}
          />
          <Button onClick={onSaveApiKey}>保存 Key</Button>
          <Button icon={<RefreshCw className="h-4 w-4" />} onClick={onRefresh}>刷新</Button>
        </div>
      </div>
      <nav className="mx-auto mt-3 flex max-w-[1440px] gap-1 overflow-x-auto lg:hidden" aria-label="Mobile navigation">
        {navigationItems.map((item) => (
          <button
            key={item.key}
            type="button"
            className={cn(
              "inline-flex shrink-0 items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-slate-600",
              activeView === item.key ? "bg-blue-50 text-blue-700" : "hover:bg-slate-100 hover:text-slate-950",
            )}
            onClick={() => onViewChange(item.key as AppView)}
          >
            {item.icon}
            {item.label}
          </button>
        ))}
      </nav>
    </header>
  );
}
