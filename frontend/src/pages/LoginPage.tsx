import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { Logo } from "@/components/Logo";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";

/** Shown instead of everything else while the optional login is on and nobody's logged in. */
export function LoginPage() {
  const queryClient = useQueryClient();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const login = useMutation({
    mutationFn: () => api.login(username, password),
    onSuccess: (status) => {
      queryClient.setQueryData(["auth"], status);
      void queryClient.invalidateQueries();
    },
  });
  function onSubmit(event: FormEvent) {
    event.preventDefault();
    login.mutate();
  }
  return (
    <main className="flex min-h-dvh items-center justify-center px-4 py-10">
      <form
        onSubmit={onSubmit}
        className="flex w-full max-w-sm flex-col gap-4 rounded-2xl border bg-card p-6 shadow-lg"
        aria-labelledby="login-title"
      >
        <div className="flex items-center gap-3">
          <Logo />
          <h1 id="login-title" className="text-xl font-semibold">
            Log in to Tailarr
          </h1>
        </div>
        <div className="flex flex-col gap-1.5">
          <label htmlFor="login-username" className="text-sm font-medium">
            Username
          </label>
          <Input
            id="login-username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
            autoCapitalize="off"
            required
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <label htmlFor="login-password" className="text-sm font-medium">
            Password
          </label>
          <Input
            id="login-password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            required
          />
        </div>
        {login.isError && (
          <p
            role="alert"
            className="rounded-lg bg-destructive-soft px-3 py-2 text-sm text-destructive"
          >
            {login.error.message}
          </p>
        )}
        <Button type="submit" disabled={login.isPending || !username || !password}>
          {login.isPending ? "Logging in…" : "Log in"}
        </Button>
        <p className="text-xs text-muted-foreground">
          Forgotten the password? Start the container once with the variable{" "}
          <span className="font-mono">TAILARR_DISABLE_LOGIN=1</span> to switch the login off.
        </p>
      </form>
    </main>
  );
}
