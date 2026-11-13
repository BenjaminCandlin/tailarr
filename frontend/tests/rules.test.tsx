import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { Rule, RuleInput, RulePreview } from "@/lib/api";
import { EXAMPLES } from "@/pages/RulesPage";

import { json, mockBackend, renderApp } from "./helpers";

const RULE: Rule = {
  ...EXAMPLES[0].rule,
  id: 3,
  sentence:
    "When a new film is added, if it has Dolby Vision: make a copy without Dolby Vision (HDR10 copy).",
  action_text: "Make a copy without Dolby Vision (HDR10 copy)",
  changes_originals: false,
  created_at: "2026-11-11T10:00:00Z",
  updated_at: "2026-11-11T10:00:00Z",
  last_run_at: null,
};

const PREVIEW: RulePreview = {
  sentence: RULE.sentence,
  changes_originals: false,
  items: [
    {
      kind: "film",
      id: 6,
      label: "Blu-ray Night (2018)",
      file: "Blu-ray Night (2018) Remux-2160p.mkv",
      will_run: true,
      lines: ["Copy without Dolby Vision profile 7: players show it as HDR10"],
      reason: null,
      hardlinked: false,
      new_file: "Blu-ray Night (2018) Remux-2160p - HDR10.mkv",
    },
    {
      kind: "film",
      id: 4,
      label: "Streaming Only (2024)",
      file: "Streaming Only (2024) WEBDL-2160p DV.mkv",
      will_run: false,
      lines: [],
      reason: "This file uses Dolby Vision profile 5…",
      hardlinked: false,
      new_file: null,
    },
  ],
  will_run: 1,
  skipped: 1,
  not_matching: 6,
  not_read: 0,
  space: [],
  enough_space: true,
};

describe("rules", () => {
  it("offers the two example rules when there are none", async () => {
    mockBackend((url) => (url.endsWith("/api/rules") ? json([]) : undefined));
    renderApp("/rules");
    expect(await screen.findByText("No rules yet")).toBeInTheDocument();
    await userEvent.click(
      screen.getByRole("button", { name: "Remove subtitle tracks that aren't English" }),
    );
    expect(await screen.findByRole("heading", { name: "New rule" })).toBeInTheDocument();
    expect(screen.getByLabelText("Rule name")).toHaveValue("Only English subtitles");
    expect(screen.getByLabelText("When a new … is added")).toHaveValue("both");
    expect(screen.getByText("If it has subtitles that aren't in…")).toBeInTheDocument();
  });

  it("previews and saves a new rule", async () => {
    let saved: RuleInput | null = null;
    const previews: RuleInput[] = [];
    mockBackend((url, init) => {
      if (url.endsWith("/api/rules/preview")) {
        previews.push(JSON.parse(String(init?.body)));
        return json(PREVIEW);
      }
      if (url.endsWith("/api/rules") && init?.method === "POST") {
        saved = JSON.parse(String(init.body));
        return json(RULE, 201);
      }
      if (url.endsWith("/api/rules")) return json([RULE]);
      return undefined;
    });
    renderApp("/rules/new?example=0");
    await userEvent.click(await screen.findByRole("button", { name: "Preview this rule" }));
    expect(await screen.findByTestId("rule-preview-counts")).toHaveTextContent(
      "1 file would get a copy, 1 matched but would be skipped. 6 files didn't match.",
    );
    expect(screen.getByRole("link", { name: "Blu-ray Night (2018)" })).toHaveAttribute(
      "href",
      "/films/6",
    );
    expect(previews[0].conditions).toEqual([{ type: "has_dolby_vision", languages: [] }]);
    // Pressing the button again hides the long list.
    await userEvent.click(screen.getAllByRole("button", { name: "Hide the preview" })[0]);
    expect(screen.queryByTestId("rule-preview-counts")).toBeNull();
    expect(screen.getByRole("button", { name: "Preview this rule" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Save the rule" }));
    await waitFor(() => expect(saved).not.toBeNull());
    expect(saved!.enabled).toBe(false);
    expect(saved!.action).toEqual({ type: "hdr10_copy", overwrite: false });
    expect(await screen.findByRole("list", { name: "Rules" })).toBeInTheDocument();
  });

  it("needs permission before a rule may change original files", async () => {
    mockBackend();
    renderApp("/rules/new");
    await userEvent.type(await screen.findByLabelText("Rule name"), "Defaults");
    await userEvent.click(screen.getByRole("radio", { name: /Choose the default audio/ }));
    await userEvent.selectOptions(screen.getByLabelText("Default audio", { exact: true }), "eng");
    expect(screen.getByText(/switch on “Allowed to change original files”/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save the rule" })).toBeDisabled();
    await userEvent.click(screen.getByRole("switch", { name: "Allowed to change original files" }));
    expect(screen.getByRole("button", { name: "Save the rule" })).toBeEnabled();
    expect(
      screen.getByRole("switch", { name: "Also change files that are still seeding" }),
    ).not.toBeChecked();
  });

  it("lists rules, switches them on and runs one", async () => {
    let enabled: boolean | null = null;
    let ran = false;
    mockBackend((url, init) => {
      if (url.endsWith("/api/rules/3/enabled")) {
        enabled = JSON.parse(String(init?.body)).enabled;
        return json({ ...RULE, enabled: true });
      }
      if (url.endsWith("/api/rules/preview")) return json(PREVIEW);
      if (url.endsWith("/api/rules/3/run")) {
        ran = JSON.parse(String(init?.body)).confirmed;
        return json({ group_id: "g", jobs: 1 }, 202);
      }
      if (url.endsWith("/api/rules")) return json([RULE]);
      return undefined;
    });
    renderApp("/rules");
    const card = await screen.findByTestId("rule-3");
    expect(card).toHaveTextContent(RULE.sentence);
    expect(card).toHaveTextContent("Off");
    await userEvent.click(within(card).getByRole("switch"));
    await waitFor(() => expect(enabled).toBe(true));
    await userEvent.click(within(card).getByRole("button", { name: /Preview and run now/ }));
    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByTestId("rule-preview-counts")).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole("button", { name: "Make 1 copy" }));
    expect(await within(dialog).findByText("1 job added to the queue")).toBeInTheDocument();
    expect(ran).toBe(true);
  });

  it("asks before deleting a rule", async () => {
    let deleted = false;
    mockBackend((url, init) => {
      if (url.endsWith("/api/rules/3") && init?.method === "DELETE") {
        deleted = true;
        return new Response(null, { status: 204 });
      }
      if (url.endsWith("/api/rules")) return json([RULE]);
      return undefined;
    });
    renderApp("/rules");
    const card = await screen.findByTestId("rule-3");
    await userEvent.click(within(card).getByRole("button", { name: "Delete" }));
    const dialog = await screen.findByRole("dialog");
    expect(deleted).toBe(false);
    await userEvent.click(within(dialog).getByRole("button", { name: "Delete the rule" }));
    await waitFor(() => expect(deleted).toBe(true));
  });
});
