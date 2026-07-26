# Tripplanner mobile

Native React Native client built with Expo SDK 54 and Expo Router. It reuses
the authoritative FastAPI backend and `@tripplanner/client`; native code owns
navigation, secure device identity, maps, sheets, and phone layout on iOS and
Android.

## Run on Android

The maintained setup, smoke-test, troubleshooting, EAS preview, and Google Play
instructions live in [`docs/android-testing.md`](../docs/android-testing.md).

Install Expo Go from Google Play, then from this directory:

```powershell
npm install
npm run android
```

This starts LAN mode on port 8082. Scan the QR code from Expo Go. The same
`EXPO_PUBLIC_API_BASE_URL` override described below applies to Android.

## Run on iPhone

The maintained setup, smoke-test, troubleshooting, EAS preview, and TestFlight
instructions live in [`docs/ios-testing.md`](../docs/ios-testing.md).

Install Expo Go from the App Store, then from this directory:

```powershell
npm install
npm run iphone
```

This starts LAN mode on port 8082 because the local Docker Cosmos Emulator uses
8081. Scan the QR code with the iPhone Camera. The app uses the production API
by default. Override it for a reachable development or canary API before starting:

```powershell
$env:EXPO_PUBLIC_API_BASE_URL='https://your-api.example/api'
npm run iphone
```

`localhost` is the phone itself and cannot reach the PC backend. Use a LAN IP,
tunnel, or hosted canary URL for physical-device testing.

## Account and existing trips

Use the Account tab to sign in with the same Google account as the web app.
The native OAuth handoff stores the signed session in SecureStore and reuses
the web identity, so saved trips, active trip, chat, and preferences are shared.
The selected backend must include `/auth/mobile/session`; an older production
deployment can run the app as a local mobile profile but cannot complete native
Google sign-in until those backend changes are deployed.

## Validate

```powershell
npx tsc --noEmit
npm run lint
npm exec --yes expo-doctor
npx expo export --platform ios
npx expo export --platform android
```

## EAS and stores

The iOS bundle identifier and Android package are both
`com.munishgoyal1.tripplanner`. `eas.json` provides development, internal
preview, and production profiles. From Windows, EAS builds both platforms in
the cloud:

```powershell
npm exec --yes eas-cli login
npm exec --yes eas-cli build --platform ios --profile production
npm exec --yes eas-cli build --platform android --profile production
```

Store distribution requires the corresponding Apple Developer or Google Play
Console account, app record, agreements, privacy details, screenshots, and
review metadata. Follow the platform runbooks and never submit production
without the owner's explicit publication approval.
