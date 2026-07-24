# Tripplanner for iPhone

Native React Native client built with Expo SDK 54 and Expo Router. It reuses
the authoritative FastAPI backend and `@tripplanner/client`; native code owns
navigation, Keychain identity, maps, sheets, and phone layout.

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

## Validate

```powershell
npx tsc --noEmit
npm run lint
npm exec --yes expo-doctor
npx expo export --platform ios
```

## EAS and App Store

The bundle identifier is `com.munishgoyal1.tripplanner`. `eas.json` provides
development, internal preview, and production profiles. From Windows, EAS can
build and submit iOS in the cloud:

```powershell
npm exec --yes eas-cli login
npm exec --yes eas-cli build --platform ios --profile production
npm exec --yes eas-cli submit --platform ios --profile production
```

Building requires an Expo account and active Apple Developer membership.
Submission also requires the App Store Connect app record, agreements,
privacy details, screenshots, and review metadata. Never submit without the
owner's explicit publication approval.
