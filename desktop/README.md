# AutoJobApply - Windows desktop app

A thin Electron shell that opens your AutoJobApply server (local or hosted) in a native window. It does **not** bundle the backend: start the platform first (`docker compose up`, see ../docs/DEPLOYMENT.md), or point the app at your hosted URL via **App > Server settings**.

Security: contextIsolation on, nodeIntegration off, sandbox on, only the configured origin loads in-window (other links open in the browser), https required except localhost.

## Build the .exe
```powershell
cd desktop
npm install
npm run dist     # -> dist\AutoJobApply Setup 1.0.0.exe and a portable .exe
```
Or push a tag `desktop-v*`: the `desktop` GitHub Action builds it on a Windows runner and uploads the artifact.

## Status
- Unit tests for URL rules: `npm test`.
- The `.exe` was **not built or launched** in the authoring environment (Linux, no Windows/Wine/display). The code is unverified as a running app until you build it on Windows. The installer is unsigned, so Windows SmartScreen will warn.
