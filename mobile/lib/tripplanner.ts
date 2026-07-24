import { randomUUID } from 'expo-crypto';
import * as SecureStore from 'expo-secure-store';
import { TripplannerClient } from '@tripplanner/client';

const PROD_API =
  'https://prod-app-f3ddjudq2rdt4.redglacier-42f3888f.eastus2.azurecontainerapps.io/api';
const IDENTITY_KEY = 'tripplanner.mobile.user-id';

export const apiBaseUrl = process.env.EXPO_PUBLIC_API_BASE_URL?.replace(/\/$/, '') || PROD_API;

async function getMobileUserId(): Promise<string> {
  const existing = await SecureStore.getItemAsync(IDENTITY_KEY);
  if (existing) return existing;
  const created = `mobile-${randomUUID()}`;
  await SecureStore.setItemAsync(IDENTITY_KEY, created);
  return created;
}

export const tripplannerClient = new TripplannerClient(apiBaseUrl, getMobileUserId);