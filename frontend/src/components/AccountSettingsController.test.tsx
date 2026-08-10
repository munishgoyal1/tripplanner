import { act, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import AccountSettingsController from "./AccountSettingsController";
import { openAccountSettings } from "./accountSettings";

vi.mock("../api", () => ({
  fetchAuthConfig: vi.fn().mockResolvedValue({ google: true }),
  loginWithGoogle: vi.fn(),
  logoutGoogle: vi.fn().mockResolvedValue(undefined),
  runPrivacyAction: vi.fn(),
  signIn: vi.fn(),
  signOut: vi.fn(),
  syncAuth: vi.fn().mockResolvedValue({ authenticated: true, display_name: "Munish" }),
}));

describe("AccountSettingsController", () => {
  beforeEach(() => {
    window.history.replaceState({}, "", "/welcome");
  });

  it("opens the complete shared settings experience without leaving the current page", async () => {
    render(<AccountSettingsController />);

    act(() => openAccountSettings());

    expect(await screen.findByRole("complementary", { name: "Account settings" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Profile and sign-in/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Travel profile/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Travel documents/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Analytics preferences/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Privacy and data/ })).toBeInTheDocument();
    expect(window.location.pathname).toBe("/welcome");
  });
});
