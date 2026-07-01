import { FormEvent, useState } from "react";
import { Bug, LogIn, ShieldCheck } from "lucide-react";
import { Alert, Button, Field, Input, PasswordInput } from "../ui";

type Props = {
  error?: string;
  loading?: boolean;
  onLogin: (credentials: { username: string; password: string }) => Promise<void> | void;
};

export function LoginPage({ error, loading, onLogin }: Props) {
  const [password, setPassword] = useState("");
  const [touched, setTouched] = useState(false);
  const [username, setUsername] = useState("");
  const showRequired = touched && (!username.trim() || !password);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setTouched(true);
    await onLogin({ username, password });
  }

  return (
    <div className="min-h-dvh bg-slate-100 px-4 py-8 text-slate-950 sm:px-6 lg:px-8">
      <main className="mx-auto flex min-h-[calc(100dvh-4rem)] w-full max-w-md items-center">
        <section className="w-full rounded-lg border border-slate-300 bg-white p-6 shadow-sm shadow-slate-200/70">
          <div className="mb-6 flex items-center gap-3">
            <span className="flex h-11 w-11 items-center justify-center rounded-lg border border-cyan-900 bg-cyan-900 text-white">
              <Bug className="h-5 w-5" />
            </span>
            <div>
              <h1 className="m-0 text-xl font-semibold leading-tight">DieAudit</h1>
              <p className="m-0 text-sm text-slate-500">登录审计运行台</p>
            </div>
          </div>

          <form className="grid gap-4" onSubmit={handleSubmit}>
            {error ? <Alert tone="danger" title="登录失败" description={error} /> : null}
            <Field label="账号">
              <Input
                autoComplete="username"
                autoFocus
                placeholder="输入管理员账号"
                value={username}
                onBlur={() => setTouched(true)}
                onChange={(event) => setUsername(event.target.value)}
              />
            </Field>
            <Field label="密码">
              <PasswordInput
                autoComplete="current-password"
                placeholder="输入管理员密码"
                value={password}
                onBlur={() => setTouched(true)}
                onChange={(event) => setPassword(event.target.value)}
              />
            </Field>
            {showRequired ? <p className="-mt-2 text-sm text-red-600">请输入账号和密码</p> : null}
            <Button
              className="w-full"
              icon={loading ? undefined : <LogIn className="h-4 w-4" />}
              loading={loading}
              type="submit"
              variant="primary"
            >
              登录
            </Button>
          </form>

          <div className="mt-5 flex items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-600">
            <ShieldCheck className="h-4 w-4 shrink-0 text-emerald-700" />
            <span>登录成功后会自动建立本地会话。</span>
          </div>
        </section>
      </main>
    </div>
  );
}
