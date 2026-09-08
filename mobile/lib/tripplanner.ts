import { randomUUID } from 'expo-crypto';
import * as Linking from 'expo-linking';
import * as SecureStore from 'expo-secure-store';
import * as WebBrowser from 'expo-web-browser';
import { requireApiBaseUrl, TripplannerClient } from '@tripplanner/client';

const IDENTITY_KEY = 'tripplanner.mobile.user-id';
const ACCOUNT_KEY = 'tripplanner.mobile.account';
const SESSION_KEY = 'tripplanner.mobile.session';

export const apiBaseUrl = requireApiBaseUrl(
  process.env.EXPO_PUBLIC_API_BASE_URL,
  'EXPO_PUBLIC_API_BASE_URL',
);

export interface MobileAccount {
  user_id: string;
  display_name: string;
  email: string;
  picture: string;
}

export interface MobilePreferences {
  display_name: string;
  home_city: string;
  home_country: string;
  trip_style: string;
  budget_level: string;
  about_me: string;
}

async function getMobileUserId(): Promise<string> {
  const existing = await SecureStore.getItemAsync(IDENTITY_KEY);
  if (existing) return existing;
  const created = `mobile-${randomUUID()}`;
  await SecureStore.setItemAsync(IDENTITY_KEY, created);
  return created;
}

async function getMobileSessionToken(): Promise<string | null> {
  const existing = await SecureStore.getItemAsync(SESSION_KEY);
  if (existing) return existing;
  const response = await fetch(`${apiBaseUrl}/auth/guest/session`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_id: await getMobileUserId() }),
  });
  if (!response.ok) return null;
  const session = await response.json() as { token?: string };
  if (!session.token) return null;
  await SecureStore.setItemAsync(SESSION_KEY, session.token);
  return session.token;
}

async function mobileAuthHeaders(): Promise<Record<string, string>> {
  const token = await getMobileSessionToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export async function getMobileAccount(): Promise<MobileAccount | null> {
  const raw = await SecureStore.getItemAsync(ACCOUNT_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as MobileAccount;
  } catch {
    return null;
  }
}

export async function loginWithGoogle(): Promise<MobileAccount> {
  const redirectUrl = Linking.createURL('auth');
  const loginUrl = `${apiBaseUrl}/auth/login/google?redirect=${encodeURIComponent(redirectUrl)}`;
  const result = await WebBrowser.openAuthSessionAsync(loginUrl, redirectUrl);
  if (result.type !== 'success' || !result.url) throw new Error('Google sign-in was cancelled.');
  const sessionToken = new URL(result.url).searchParams.get('session');
  if (!sessionToken) throw new Error('Google sign-in did not return a session.');
  const response = await fetch(`${apiBaseUrl}/auth/mobile/session?token=${encodeURIComponent(sessionToken)}`);
  if (!response.ok) throw new Error('Google sign-in session could not be verified.');
  const account = await response.json() as MobileAccount & { authenticated: boolean };
  if (!account.authenticated || !account.user_id) throw new Error('Google sign-in failed.');
  await SecureStore.setItemAsync(SESSION_KEY, sessionToken);
  await SecureStore.setItemAsync(ACCOUNT_KEY, JSON.stringify(account));
  await SecureStore.setItemAsync(IDENTITY_KEY, account.user_id);
  return account;
}

export async function logoutMobile(): Promise<void> {
  await SecureStore.deleteItemAsync(SESSION_KEY);
  await SecureStore.deleteItemAsync(ACCOUNT_KEY);
  await SecureStore.deleteItemAsync(IDENTITY_KEY);
}

export async function fetchMobilePreferences(): Promise<MobilePreferences> {
  const response = await fetch(
    `${apiBaseUrl}/preferences?user_id=${encodeURIComponent(await getMobileUserId())}`,
    { headers: await mobileAuthHeaders() },
  );
  if (!response.ok) throw new Error(`Could not load preferences (${response.status}).`);
  const data = await response.json() as Partial<MobilePreferences>;
  return {
    display_name: data.display_name || '',
    home_city: data.home_city || '',
    home_country: data.home_country || '',
    trip_style: data.trip_style || '',
    budget_level: data.budget_level || '',
    about_me: data.about_me || '',
  };
}

export async function saveMobilePreferences(
  preferences: Partial<MobilePreferences>,
): Promise<void> {
  const response = await fetch(`${apiBaseUrl}/preferences`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...await mobileAuthHeaders() },
    body: JSON.stringify({ ...preferences, user_id: await getMobileUserId() }),
  });
  if (!response.ok) throw new Error(`Could not save preferences (${response.status}).`);
}

export const tripplannerClient = new TripplannerClient(
  apiBaseUrl,
  getMobileUserId,
  getMobileSessionToken,
);