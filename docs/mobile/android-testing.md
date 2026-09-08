# Android testing runbook

Use this runbook to test the shared React Native app on a physical Android phone
from Windows. Android and iPhone use the same screens, state, API client, and
backend; do not create an Android-specific product fork.

The release progression is Expo Go, EAS internal distribution, Google Play
internal testing, then production. Production publication always requires
explicit owner approval.

## Current baseline

Verified on 2026-07-25:

- Expo SDK 54.0.35 and Expo Router 6.0.24
- React Native 0.81.5 and React 19.1.0
- Android Hermes export: 1,355 modules, approximately 3.78 MB
- Expo Doctor: 18/18 checks pass
- Android package: `com.munishgoyal1.tripplanner`
- Required API setting: `EXPO_PUBLIC_API_BASE_URL`

The Expo dependency tree currently reports 14 transitive advisories. Do not run
`npm audit fix --force`: it proposes an incompatible Expo major-version upgrade.
Re-evaluate these advisories during a planned Expo SDK upgrade.

## Which test channel to use

| Channel | Use | Developer account | Public |
|---|---|---:|---:|
| Expo Go | Fast JavaScript/UI testing | No | No |
| EAS preview | Installable signed APK | Expo account | No |
| Play internal testing | Store-delivered app bundle for the team | Google Play | No |
| Play closed/open testing | Wider staged beta | Google Play | Limited |
| Google Play production | Public release | Google Play | Yes |

Expo Go is the correct first test. It includes Maps, SecureStore, haptics, and
the other native modules used by this app. It does not validate final package
signing, adaptive icons, standalone Google Maps credentials, permissions, or
Play Store metadata. Use EAS preview and Play internal testing before release.

## First-time setup

### On the Android phone

1. Install **Expo Go** from Google Play:
   <https://play.google.com/store/apps/details?id=host.exp.exponent>
2. Allow Camera and nearby/local-network access when Android asks.
3. Connect the phone and development PC to the same Wi-Fi.

No Expo account, USB cable, Android Studio, or Google Play developer account is
required for this Expo Go stage.

### On the Windows development PC

From the repository root:

```powershell
cd mobile
npm install
npm exec --yes expo-doctor
```

Use a supported Node.js LTS release for repeatable development. Node 25.6.1 was
also verified on this workstation on 2026-07-25.

## Start Expo Go

The default physical-device path uses LAN port 8082 because Docker can occupy
Metro's normal port 8081:

```powershell
cd mobile
$env:EXPO_PUBLIC_API_BASE_URL='https://your-api.example/api'
npm run android
```

Wait for Metro to print a QR code and an `exp://<pc-ip>:8082` address. Then:

1. Open Expo Go on Android.
2. Tap **Scan QR code** and scan the terminal QR code.
3. If scanning fails, enter Metro's `exp://` address manually if that option is
   available in the installed Expo Go version.
4. Keep Metro running while testing; press `Ctrl+C` in its terminal when done.

Do not open Metro's displayed `http://localhost:8082` web address. This package
is a native app and its `react-native-maps` screen is not a web target.

If the devices cannot reach each other over LAN, try the optional tunnel:

```powershell
npm run android:tunnel
```

Tunnel mode requires `@expo/ngrok`. If Expo cannot install it automatically:

```powershell
npm install --global @expo/ngrok@^4.1.0
npm run android:tunnel
```

The current network has previously timed out while connecting ngrok. Prefer LAN
instead of changing application dependencies when that happens.

## Select the backend

The app does not select a backend implicitly. Set a reachable development,
canary, or production API before starting Metro:

```powershell
$env:EXPO_PUBLIC_API_BASE_URL='https://your-api.example/api'
npm run android
```

Set the same value in the selected EAS build environment for preview or store
builds. A missing value stops startup instead of routing a development build to
production.

`localhost` on the phone means the phone itself. A local backend must listen on
a LAN-accessible interface, be allowed through Windows Firewall, and use the
PC's LAN address. Prefer hosted canary for repeatable device testing.

Never put secrets in `EXPO_PUBLIC_*`; those values are embedded in the bundle.

## Expo Go smoke test

Complete this checklist after a fresh launch:

- Trips loads saved trips and switches the active trip.
- New trip clears the workspace without deleting saved trips.
- Plan renders structured days; booking controls update without opening Details,
   and the booked count remains consistent after leaving and returning to Plan.
- Map renders Google Maps, pins, and day routes; a pin opens Details.
- Details moves an exact occurrence to another day and removes one exact
   occurrence or all repeated occurrences; Plan and Map reflect each change.
- Assistant restores chat history and sends one streamed turn.
- Android system Back closes Details and returns to the prior tab correctly.
- Force-stop and reopen Expo Go; identity and active-trip data remain available.
- Rotate once and return to portrait; the app remains usable and portrait-bound.
- Switch Wi-Fi off and on once; network failures remain recoverable.

For a bug report, record the API target, phone model, Android version, app commit,
and failed checklist item. Copy Metro errors as text; use screenshots for visual
defects or an Android error overlay.

## Troubleshooting

### QR code does not connect

- Confirm both devices are on the same Wi-Fi and guest/client isolation is off.
- Confirm Metro prints port 8082, not Docker's port 8081.
- Allow Expo Go Camera and nearby/local-network permissions in Android Settings.
- Temporarily disable VPN or restrictive corporate network software.
- Try `npm run android:tunnel` only when LAN is unavailable.

### Stale bundle or Metro cache error

```powershell
cd mobile
npx expo start --clear --lan --port 8082
```

### Shared package cannot be resolved

```powershell
cd mobile
npm install
npx expo start --clear --lan --port 8082
```

`mobile/metro.config.js` must retain the repository root in `watchFolders` so
Metro can resolve `packages/tripplanner-client`.

### Expo Go reports an incompatible SDK

Update Expo Go from Google Play, then run:

```powershell
cd mobile
npm exec --yes expo-doctor
```

Upgrade Expo as one tested SDK milestone, never as unrelated package bumps.

### App opens but API calls fail

- Confirm the selected API URL before Metro started.
- Do not use `localhost` for a physical phone.
- Open the hosted API URL in Chrome on the phone to check reachability.
- Restart Metro after changing `EXPO_PUBLIC_API_BASE_URL`.

### Map is blank in a standalone build

Expo Go provides its own native Google Maps setup. A standalone EAS Android build
needs a Google Maps Android API key restricted to package
`com.munishgoyal1.tripplanner` and the final signing certificate SHA-1. Configure
that through EAS secrets and Expo's `react-native-maps` config plugin before the
first preview build. Never commit the key or put it in `EXPO_PUBLIC_*`.

## EAS preview and Google Play

After Expo Go passes, an EAS preview can produce a directly installable APK:

```powershell
cd mobile
npm exec --yes eas-cli login
npm exec --yes eas-cli build --platform android --profile preview
```

Before Google Play internal testing:

1. Create the Google Play Console application for the package ID.
2. Complete app access, content rating, data safety, privacy policy, and store
   listing fields.
3. Configure the restricted standalone Google Maps key.
4. Build the production Android App Bundle:

```powershell
npm exec --yes eas-cli build --platform android --profile production
```

Upload the resulting AAB to Play internal testing first. Google Play credentials
must be entered directly into Google/EAS tools and never stored in source, docs,
or chat. Do not submit to production without explicit owner approval.

## Handoff checklist

1. Update this runbook when SDKs, commands, API targets, or recurring failures change.
2. Update `docs/CODEMAP.md` when ownership or layout changes.
3. Update `docs/PRODUCT.md` and `docs/reference/history/requirements-log.txt` for product decisions.
4. Run `npx tsc --noEmit`, `npm run lint`, `npm exec --yes expo-doctor`, and
   `npx expo export --platform android`.
5. Commit and push documentation with the implementation it describes.
