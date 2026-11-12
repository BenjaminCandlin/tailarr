import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { LogOut } from "lucide-react";
import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { api, type LoginSettings } from "@/lib/api";

function LoginForm({ initial }: { initial: LoginSettings }) {
  const queryClient = useQueryClient();
  const [enabled, setEnabled] = useState(initial.enabled);
  const [username, setUsername] = useState(initial.username);
  const [password, setPassword] = useState("");
  const [repeat, setRepeat] = useState("");
  const save = useMutation({
    mutationFn: () =>
      api.saveLoginSettings(
        enabled ? { enabled, username, ...(password ? { password } : {}) } : { enabled: false },
      ),
    onSuccess: (saved) => {
      queryClient.setQueryData(["settings", "login"], saved);
      void queryClient.invalidateQueries({ queryKey: ["auth"] });
      setPassword("");
      setRepeat("");
    },
  });
  const logout = useMutation({
    mutationFn: api.logout,
    onSuccess: (status) => queryClient.setQueryData(["auth"], status),
  });
  const needsPassword = enabled && !initial.enabled;
  const problem =
    enabled && !username.trim()
      ? "Choose a username."
      : needsPassword && password.length < 8
        ? "Choose a password of at least 8 characters."
        : password && password.length < 8
          ? "Choose a password of at least 8 characters."
          : password !== repeat
            ? "The two passwords aren't the same."
            : null;
  const changed =
    enabled !== initial.enabled || (enabled && (username !== initial.username || password !== ""));

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!problem) save.mutate();
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-4">
      <div className="flex items-start gap-3">
        <Switch id="login-enabled" checked={enabled} onCheckedChange={setEnabled} />
        <div className="pt-1.5 md:pt-1">
          <label htmlFor="login-enabled" className="cursor-pointer text-sm font-medium">
            Ask for a username and password
          </label>
          <p className="text-xs text-muted-foreground">
            Worth switching on if other people use your network, or if Tailarr can be reached from
            outside your home. Radarr and Sonarr webhooks keep working (they have their own secret).
          </p>
        </div>
      </div>
      {enabled && (
        <div className="grid gap-3 md:grid-cols-3">
          <div className="flex flex-col gap-1.5">
            <label htmlFor="login-name" className="text-sm font-medium">
              Username
            </label>
            <Input
              id="login-name"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="username"
              autoCapitalize="off"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label htmlFor="login-new-password" className="text-sm font-medium">
              {initial.enabled ? "New password (leave empty to keep it)" : "Password"}
            </label>
            <Input
              id="login-new-password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="new-password"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label htmlFor="login-repeat" className="text-sm font-medium">
              Password again
            </label>
            <Input
              id="login-repeat"
              type="password"
              value={repeat}
              onChange={(e) => setRepeat(e.target.value)}
              autoComplete="new-password"
            />
          </div>
        </div>
      )}
      {changed && problem && <p className="text-sm text-muted-foreground">{problem}</p>}
      {save.isError && (
        <p
          role="alert"
          className="rounded-lg bg-destructive-soft px-3 py-2 text-sm text-destructive"
        >
          {save.error.message}
        </p>
      )}
      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" disabled={!changed || Boolean(problem) || save.isPending}>
          {save.isPending ? "Saving…" : "Save login"}
        </Button>
        {save.isSuccess && !changed && (
          <p role="status" className="text-sm text-success">
            Saved.
          </p>
        )}
        {initial.enabled && (
          <Button type="button" variant="ghost" onClick={() => logout.mutate()}>
            <LogOut aria-hidden />
            Log out
          </Button>
        )}
      </div>
      <p className="text-xs text-muted-foreground">
        Forgotten the password? Start the container once with the variable{" "}
        <span className="font-mono">TAILARR_DISABLE_LOGIN=1</span> (Unraid: edit the container → Add
        another Path, Port, Variable…), then remove it again.
      </p>
    </form>
  );
}

export function LoginCard() {
  const settings = useQuery({ queryKey: ["settings", "login"], queryFn: api.loginSettings });
  return (
    <Card>
      <CardHeader>
        <CardTitle>Login</CardTitle>
        <CardDescription>Optional. Off by default.</CardDescription>
      </CardHeader>
      <CardContent>
        {settings.isPending ? (
          <Skeleton className="h-24 w-full" />
        ) : settings.isError ? (
          <p role="alert" className="text-sm text-destructive">
            {settings.error.message}
          </p>
        ) : (
          <LoginForm
            key={`${settings.data.enabled}-${settings.data.username}`}
            initial={settings.data}
          />
        )}
      </CardContent>
    </Card>
  );
}
