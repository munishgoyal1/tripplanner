import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import AccountSettingsHub from "./AccountSettingsHub";

function renderHub(overrides: Partial<React.ComponentProps<typeof AccountSettingsHub>> = {}) {
  const props: React.ComponentProps<typeof AccountSettingsHub> = {
    auth: { authenticated: false },
    googleEnabled: true,
    localIdentityActive: false,
    nameInput: "",
    privacyBusy: false,
    onNameInputChange: vi.fn(),
    onClose: vi.fn(),
    onGoogleSignIn: vi.fn(),
    onLocalSignIn: vi.fn(),
    onSignOut: vi.fn(),
    onDeleteTripHistory: vi.fn(),
    onClearAllData: vi.fn(),
    onDeleteAccount: vi.fn(),
    ...overrides,
  };
  render(<AccountSettingsHub {...props} />);
  return props;
}

describe("AccountSettingsHub", () => {
  it("presents the four selected account destinations", () => {
    renderHub();

    expect(screen.getByRole("complementary", { name: "Account settings" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Profile and sign-in/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Travel profile/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Analytics preferences/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Privacy and data/ })).toBeInTheDocument();
  });

  it("keeps travel profile and analytics inside the account settings hub", async () => {
    renderHub();

    fireEvent.click(screen.getByRole("button", { name: /Travel profile/ }));
    expect(screen.getByRole("heading", { name: "Travel profile" })).toBeInTheDocument();
    expect(screen.getByRole("complementary", { name: "Account settings" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Back to settings/ }));
    fireEvent.click(screen.getByRole("button", { name: /Analytics preferences/ }));
    expect(screen.getByRole("region", { name: "Analytics preferences" })).toBeInTheDocument();
    expect(screen.getByRole("complementary", { name: "Account settings" })).toBeInTheDocument();
  });

  it("supports sign-in and all grounded privacy actions", () => {
    const props = renderHub({ nameInput: "Munish" });

    fireEvent.click(screen.getByRole("button", { name: /Profile and sign-in/ }));
    fireEvent.click(screen.getByRole("button", { name: "Sign in with Google" }));
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(props.onGoogleSignIn).toHaveBeenCalledOnce();
    expect(props.onLocalSignIn).toHaveBeenCalledOnce();

    fireEvent.click(screen.getByRole("button", { name: /Back to settings/ }));
    fireEvent.click(screen.getByRole("button", { name: /Privacy and data/ }));
    fireEvent.click(screen.getByRole("button", { name: /Delete trip and chat history/ }));
    fireEvent.click(screen.getByRole("button", { name: /Clear all app data/ }));
    fireEvent.click(screen.getByRole("button", { name: /Delete account data/ }));

    expect(props.onDeleteTripHistory).toHaveBeenCalledOnce();
    expect(props.onClearAllData).toHaveBeenCalledOnce();
    expect(props.onDeleteAccount).toHaveBeenCalledOnce();
  });
});