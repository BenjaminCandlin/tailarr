import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { RecycledFile } from "@/lib/api";

import { job, json, mockBackend, renderApp } from "./helpers";

const WAITING: RecycledFile = {
  id: 3,
  name: "Colour Test (2023) WEBDL-2160p DV HDR10.mkv",
  folder: "Colour Test (2023)",
  original_path:
    "/data/media/movies/Colour Test (2023)/Colour Test (2023) WEBDL-2160p DV HDR10.mkv",
  size: 8 * 1024 ** 3,
  recycled_at: "2026-11-01T10:00:00Z",
  days_left: 18,
  available: true,
  clash: false,
  clash_size: null,
};

function backend(files: RecycledFile[], posted: unknown[]) {
  return mockBackend((url, init) => {
    if (url.endsWith("/api/settings/recycle"))
      return json({ keep_days: 30, file_count: files.length, total_size: 8 * 1024 ** 3 });
    if (url.endsWith("/api/settings/recycle/files")) return json(files);
    if (url.includes("/restore") && init?.method === "POST") {
      posted.push({ url, body: JSON.parse(String(init.body)) });
      return json(job({ id: 77, kind: "restore_recycled", status: "queued" }), 202);
    }
    if (url.endsWith("/api/jobs/77"))
      return json(
        job({
          id: 77,
          kind: "restore_recycled",
          status: "done",
          message: "Put it back from the recycle folder.",
        }),
      );
    return undefined;
  });
}

describe("restore from the recycle folder", () => {
  it("lists waiting files and puts one back after a summary", async () => {
    const posted: unknown[] = [];
    backend([WAITING, { ...WAITING, id: 4, name: "Gone.mkv", available: false }], posted);
    renderApp("/settings");
    const list = await screen.findByTestId("recycled-files");
    const row = within(list).getByTestId("recycled-3");
    expect(row).toHaveTextContent("From Colour Test (2023) · 8.0 GB");
    expect(row).toHaveTextContent("deleted in 18 days");
    // A file deleted by hand can't be restored.
    const gone = within(list).getByTestId("recycled-4");
    expect(gone).toHaveTextContent("No longer in the recycle folder");
    expect(within(gone).queryByRole("button")).toBeNull();

    await userEvent.click(within(row).getByRole("button", { name: /Restore/ }));
    const dialog = await screen.findByRole("dialog", { name: "Put this file back?" });
    expect(within(dialog).getByTestId("restore-file")).toHaveTextContent(WAITING.name);
    expect(dialog).toHaveTextContent("/data/media/movies/Colour Test (2023)");
    expect(within(dialog).queryByTestId("restore-clash")).toBeNull();
    await userEvent.click(within(dialog).getByRole("button", { name: "Put it back" }));
    expect(await screen.findByText("File put back", {}, { timeout: 4000 })).toBeInTheDocument();
    expect(posted).toEqual([
      { url: "/api/settings/recycle/files/3/restore", body: { confirmed: true, swap: false } },
    ]);
  });

  it("asks before swapping with the file that's there now", async () => {
    const posted: unknown[] = [];
    backend([{ ...WAITING, clash: true, clash_size: 6 * 1024 ** 3 }], posted);
    renderApp("/settings");
    const row = await screen.findByTestId("recycled-3");
    await userEvent.click(within(row).getByRole("button", { name: /Restore/ }));
    const dialog = await screen.findByRole("dialog", { name: "Put this file back?" });
    const clash = within(dialog).getByTestId("restore-clash");
    expect(clash).toHaveTextContent("(6.0 GB) is in that folder now");
    expect(clash).toHaveTextContent("kept 30 days");
    const confirm = within(dialog).getByRole("button", { name: "Swap them" });
    expect(confirm).toBeDisabled();
    await userEvent.click(within(dialog).getByRole("checkbox", { name: /Swap them/ }));
    await userEvent.click(confirm);
    await waitFor(() =>
      expect(posted).toEqual([
        { url: "/api/settings/recycle/files/3/restore", body: { confirmed: true, swap: true } },
      ]),
    );
  });

  it("shows nothing extra when the recycle folders are empty", async () => {
    mockBackend();
    renderApp("/settings");
    await screen.findByTestId("recycle-contents");
    expect(screen.queryByTestId("recycled-files")).toBeNull();
  });
});
