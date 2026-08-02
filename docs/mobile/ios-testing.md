# iPhone testing runbook

Use this runbook to test the native app from Windows without publishing it.
The normal progression is Expo Go, EAS internal distribution, TestFlight, then
App Store production. Production submission always requires explicit owner
approval.

## Current baseline

Verified on 2026-07-24:

- Expo SDK 54.0.35 and Expo Router 6.0.24
- React Native 0.81.5 and React 19.1.0
- Expo Doctor: 18/18 checks pass
- iPhone-only bundle ID: `com.munishgoyal1.tripplanner`
- Default API: hosted production API from `mobile/lib/tripplanner.ts`
- Optional API override: `EXPO_PUBLIC_API_BASE_URL`

The Expo dependency tree currently reports 14 transitive advisories. Do not run
`npm audit fix --force`: it proposes an incompatible Expo major-version upgrade.
Re-evaluate the advisories during the next planned Expo SDK upgrade.

## Which test channel to use

| Channel | Use | Apple Developer membership | Public |
|---|---|---:|---:|
| Expo Go | Fast JavaScript/UI testing | No | No |
| EAS preview | Real signed app on registered devices | Yes | No |
| TestFlight internal | App Store-like beta for the team | Yes | No |
| TestFlight external | Wider beta after Beta App Review | Yes | No |
| App Store | Production release | Yes | Yes |

Expo Go is the right first check. It includes the native modules this app uses,
including SecureStore and Maps, but it does not validate the final signed binary,
bundle metadata, production entitlements, or App Store packaging. Use an EAS
preview build and TestFlight before release.

## First-time setup

### On the iPhone

1. Install **Expo Go** from the Apple App Store:
   <https://apps.apple.com/app/expo-go/id982107779>
2. Allow Camera and local-network access when iOS asks.
3. Keep the phone and development PC on the same network when using LAN mode.

No Expo account is required for ordinary Expo Go LAN or tunnel testing.

### On the Windows development PC

From the repository root:

```powershell
cd mobile
npm install
npm exec --yes expo-doctor
```

Use a supported Node.js LTS release for repeatable development. The toolchain was
also verified with Node 25.6.1 on 2026-07-24, but a current LTS release is the
preferred team baseline.

## Start Expo Go

LAN mode is the default because it avoids external tunnel dependencies. Connect
the iPhone and PC to the same Wi-Fi, then run:

```powershell
cd mobile
npm run iphone
```

This uses port 8082. Port 8081 is intentionally avoided because the local Docker
Cosmos Emulator can already own it. Wait for the terminal to show a QR code, then:

1. Open the iPhone Camera.
2. Scan the QR code.
3. Tap the Expo Go banner.
4. Keep the terminal running while testing. Press `Ctrl+C` there when finished.

If Camera does not offer the Expo link, open Expo Go, choose its manual URL
option, and enter the `exp://<pc-ip>:8082` URL printed by Metro.

Tunnel mode can work when the phone cannot directly reach the PC:

```powershell
npm run iphone:tunnel
```

The first tunnel run requires `@expo/ngrok`. If Expo's automatic global install
fails, install it directly and retry:

```powershell
npm install --global @expo/ngrok@^4.1.0
npm run iphone:tunnel
```

Some networks block or time out ngrok even after installation. In that case,
return to `npm run iphone`; changing package versions will not fix a blocked
network tunnel.

## Select the backend

The app uses the hosted production API by default. To test against a reachable
canary or development backend, set the URL before starting Expo:

```powershell
$env:EXPO_PUBLIC_API_BASE_URL='https://your-api.example/api'
npm run iphone
```

`localhost` on an iPhone means the iPhone, not the Windows PC. A local backend
must listen on a LAN-accessible interface, be allowed through Windows Firewall,
and use the PC's LAN address. Prefer hosted canary for stable device testing.

`EXPO_PUBLIC_*` values are embedded in the client bundle. Never put API keys,
tokens, passwords, or other secrets in them.

## Expo Go smoke test

Complete this checklist after a fresh launch:

- Trips loads the saved-trip list and can switch the active trip.
- New trip clears the active workspace without deleting saved trips.
- Plan shows structured days and booking controls update.
- Map renders pins and day routes; selecting a pin opens Details.
- Details can remove one exact occurrence or all repeated occurrences.
- Assistant restores chat history and can send one streamed turn.
- Force-close and reopen Expo Go; identity and active-trip data remain available.
- Switch between Wi-Fi and cellular once and confirm failures are recoverable.

Record the API target, iPhone model, iOS version, app commit, and failed checklist
item in any bug report. Copy terminal errors as text; attach a screenshot only for
visual defects or an iOS error overlay.

## Troubleshooting

### QR code does not connect

- Confirm both devices are on the same Wi-Fi and use `npm run iphone`.
- Confirm Metro prints an address ending in `:8082`, not Docker's port 8081.
- Enter Metro's `exp://` URL manually in Expo Go when Camera does not open it.
- Try `npm run iphone:tunnel` only when LAN access is unavailable.
- Disable VPN or restrictive corporate network software temporarily.
- Keep Expo Go in the foreground during the initial connection.
- Confirm the PC has internet access and retry once with a fresh QR code.

### Stale code or Metro cache errors

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

`mobile/metro.config.js` must keep the repository root in `watchFolders` so
Metro can resolve `packages/tripplanner-client`.

### Expo Go reports an incompatible SDK

Update Expo Go from the App Store, then run:

```powershell
cd mobile
npm exec --yes expo-doctor
```

Do not upgrade Expo packages independently. Upgrade the SDK as one tested
milestone using Expo's compatibility guidance.

### App opens but API calls fail

- Confirm which API URL was selected before Metro started.
- Do not use `localhost` for a physical phone.
- Open the hosted API URL in iPhone Safari to distinguish API reachability from
  an app problem.
- Restart Metro after changing `EXPO_PUBLIC_API_BASE_URL`.

## EAS preview and TestFlight

After Expo Go passes, follow this progression from `mobile/`:

```powershell
npm exec --yes eas-cli login
npm exec --yes eas-cli device:create
npm exec --yes eas-cli build --platform ios --profile preview
```

The preview profile creates a private signed build for registered iPhones. For
TestFlight, create the App Store Connect app record first, then build production:

```powershell
npm exec --yes eas-cli build --platform ios --profile production
npm exec --yes eas-cli submit --platform ios --profile production
```

Apple and Expo authentication must be entered directly into their CLIs. Never
place credentials in documentation, source control, chat, or `EXPO_PUBLIC_*`
variables. Do not submit a production build without explicit owner approval.

## Handoff checklist

Before ending a mobile-testing milestone:

1. Update this runbook when a command, SDK, API target, or recurring failure changes.
2. Update `docs/CODEMAP.md` if ownership or file layout changes.
3. Update `docs/PRODUCT.md` and `docs/reference/history/requirements-log.txt` for product decisions.
4. Run `npx tsc --noEmit`, `npm run lint`, and `npm exec --yes expo-doctor`.
5. Commit and push the documentation with the code it describes.
