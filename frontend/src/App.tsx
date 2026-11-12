import { QueryClient, QueryClientProvider, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router";

import { AppShell } from "@/components/AppShell";
import { api, setLoggedOutHandler } from "@/lib/api";
import { ThemeProvider } from "@/lib/theme";
import { LoginPage } from "@/pages/LoginPage";
import { FilmDetailPage } from "@/pages/FilmDetailPage";
import { FilmsPage } from "@/pages/FilmsPage";
import { NotFoundPage } from "@/pages/NotFoundPage";
import { QueuePage } from "@/pages/QueuePage";
import { RuleEditorPage } from "@/pages/RuleEditorPage";
import { RulesPage } from "@/pages/RulesPage";
import { SettingsPage } from "@/pages/SettingsPage";
import { ActivityPage } from "@/pages/ActivityPage";
import { EpisodePage } from "@/pages/EpisodePage";
import { ShowPage } from "@/pages/ShowPage";
import { TvPage } from "@/pages/TvPage";

/** Shows the login form instead of the app while the optional login is needed. */
function AuthGate({ children }: { children: React.ReactNode }) {
  const queryClient = useQueryClient();
  const auth = useQuery({ queryKey: ["auth"], queryFn: api.authStatus, retry: false });
  useEffect(() => {
    setLoggedOutHandler(() => void queryClient.invalidateQueries({ queryKey: ["auth"] }));
    return () => setLoggedOutHandler(null);
  }, [queryClient]);
  if (auth.data && auth.data.login_enabled && !auth.data.logged_in) return <LoginPage />;
  return <>{children}</>;
}

export function AppRoutes() {
  return (
    <AuthGate>
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<Navigate to="/films" replace />} />
          <Route path="films" element={<FilmsPage />} />
          <Route path="films/:id" element={<FilmDetailPage />} />
          <Route path="tv" element={<TvPage />} />
          <Route path="tv/shows/:id" element={<ShowPage />} />
          <Route path="tv/episodes/:id" element={<EpisodePage />} />
          <Route path="rules" element={<RulesPage />} />
          <Route path="rules/new" element={<RuleEditorPage />} />
          <Route path="rules/:id" element={<RuleEditorPage />} />
          <Route path="queue" element={<QueuePage />} />
          <Route path="activity" element={<ActivityPage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Routes>
    </AuthGate>
  );
}

export function makeQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
  });
}

export function App() {
  return (
    <ThemeProvider>
      <QueryClientProvider client={makeQueryClient()}>
        <BrowserRouter>
          <AppRoutes />
        </BrowserRouter>
      </QueryClientProvider>
    </ThemeProvider>
  );
}
