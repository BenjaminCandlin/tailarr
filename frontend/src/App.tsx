import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes } from "react-router";

import { AppShell } from "@/components/AppShell";
import { ThemeProvider } from "@/lib/theme";
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

export function AppRoutes() {
  return (
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
