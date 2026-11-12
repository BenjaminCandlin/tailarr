import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { CONNECTIONS, json, mockBackend, renderApp } from "./helpers";

describe("login", () => {
  it("asks to log in when the login is on", async () => {
    let loggedIn = false;
    const bodies: unknown[] = [];
    mockBackend((url, init) => {
      if (url.endsWith("/api/auth/status"))
        return json({
          login_enabled: true,
          logged_in: loggedIn,
          username: loggedIn ? "ben" : null,
        });
      if (url.endsWith("/api/auth/login")) {
        bodies.push(JSON.parse(String(init?.body)));
        const headers = new Headers(init?.headers);
        expect(headers.get("X-Requested-With")).toBe("tailarr");
        const body = JSON.parse(String(init?.body));
        if (body.password !== "correct horse")
          return json({ detail: "Wrong username or password." }, 401);
        loggedIn = true;
        return json({ login_enabled: true, logged_in: true, username: "ben" });
      }
      return undefined;
    });
    renderApp("/films");
    expect(await screen.findByRole("heading", { name: "Log in to Tailarr" })).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Username"), "ben");
    await userEvent.type(screen.getByLabelText("Password"), "wrong");
    await userEvent.click(screen.getByRole("button", { name: "Log in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Wrong username or password.");
    await userEvent.clear(screen.getByLabelText("Password"));
    await userEvent.type(screen.getByLabelText("Password"), "correct horse");
    await userEvent.click(screen.getByRole("button", { name: "Log in" }));
    expect(await screen.findByRole("heading", { name: "Films", level: 1 })).toBeInTheDocument();
    expect(bodies).toHaveLength(2);
  });

  it("switches the login on from Settings", async () => {
    let saved: unknown = null;
    mockBackend((url, init) => {
      if (url.endsWith("/api/settings/login") && init?.method === "PUT") {
        saved = JSON.parse(String(init.body));
        return json({ enabled: true, username: "ben" });
      }
      return undefined;
    });
    renderApp("/settings");
    await userEvent.click(await screen.findByRole("switch", { name: /Ask for a username/ }));
    await userEvent.type(screen.getByLabelText("Username"), "ben");
    await userEvent.type(screen.getByLabelText("Password", { exact: true }), "short");
    expect(screen.getByText("Choose a password of at least 8 characters.")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Password", { exact: true }), "-but-longer");
    await userEvent.type(screen.getByLabelText("Password again"), "short-but-longer");
    await userEvent.click(screen.getByRole("button", { name: "Save login" }));
    await waitFor(() =>
      expect(saved).toEqual({ enabled: true, username: "ben", password: "short-but-longer" }),
    );
  });
});

describe("getting started", () => {
  it("shows first steps until something is connected, and can be hidden", async () => {
    mockBackend((url) =>
      url.endsWith("/api/settings/connections")
        ? json({ ...CONNECTIONS, radarr: { url: "", has_key: false } })
        : undefined,
    );
    renderApp("/films");
    expect(await screen.findByRole("heading", { name: "Getting started" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Got it" }));
    expect(screen.queryByRole("heading", { name: "Getting started" })).toBeNull();
    expect(localStorage.getItem("tailarr-welcome-dismissed")).toBe("1");
  });

  it("isn't shown once Radarr is connected", async () => {
    mockBackend();
    renderApp("/films");
    await screen.findByRole("heading", { name: "Films", level: 1 });
    expect(screen.queryByRole("heading", { name: "Getting started" })).toBeNull();
  });
});
