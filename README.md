# Schugaa 🩸

![GitHub Downloads (all assets, all releases)](https://img.shields.io/github/downloads/EloneMusk/schugaa/total?style=flat&logo=github&label=Downloads)

Schugaa is a lightweight, native macOS menu bar application that displays real-time glucose levels from your Freestyle Libre or Dexcom sensor. It sits quietly in your menu bar, providing quick access to your current glucose reading, trend arrows, and a historical data graph.

<p align="center">
  <img src="https://github.com/EloneMusk/schugaa/blob/main/dark.png" alt="Dark Preview" width="400">
  <img src="https://github.com/EloneMusk/schugaa/blob/main/light.png" alt="Light Preview" width="400">
</p>

## Features ✨

- **Menu Bar Widget**: View your latest glucose value and trend arrow directly in the macOS menu bar.
- **Sensor Status Tracking**: Real-time sensor monitoring with:
  - **Warmup Display**: Shows "Warming up (X min)" during the 60-minute sensor warmup period
  - **Expiration Countdown**: Displays days remaining until sensor expires (14-day lifecycle)
  - **Expired Warning**: Visual alert when sensor needs replacement
- **Interactive Graph**: Click the menu item to view a beautiful, native interactive graph of your recent history. Hover over points to see exact values and timestamps.
- **Cream-Colored Status Bar**: Stylish cream background for the status display showing glucose status, last updated time, and sensor information all in one line.
- **Unit Conversion**: Supports both **mg/dL** and **mmol/L**. Switch instantly via the menu.
- **Auto-Refresh**: Data automatically refreshes in the background (every 5 minutes) and immediately when you open the menu.
- **Region Support**: Compatible with LibreView accounts worldwide (EU, Global, DE, FR, JP, AP, AE, UK, etc.).
- **Dexcom Support**: Log in with Dexcom (US or OUS) and view readings with the same UI.
- **Smart Redirect Handling**: Automatically detects and handles regional account redirects.
- **Native & Lightweight**: Built with Python and native macOS APIs (AppKit) for a seamless system integration.
- **Universal Support**: Runs natively on both Apple Silicon (M1/M2/M3) and Intel Macs.
- **Secure-ish**: Credentials are stored locally; passwords are kept in macOS Keychain when available, and local files are permission-restricted (`~/.schugaa/session.json`).

## Installation 📦

### Running from Source using Script

1.  Ensure you have Python 3.10+ installed.
2.  Clone this repository.
3.  Run the start script:
    ```bash
    ./run.sh
    ```
    This will automatically set up a virtual environment, install dependencies, and launch the app.

### Running from Source using `uv`
1. Ensure you have [uv](https://docs.astral.sh/uv/getting-started/installation/) installed
2. Run `uv sync` to install dependencies
3. Run the main script:
```bash
uv run main.py
```

### Building the App (DMG)

To create a standalone `.dmg` file that you can install like any other Mac app:

1.  Run the package script:
    ```bash
    ./package.sh
    ```
2.  The `Schugaa.dmg` file will be created in the `dist/` folder (or project root). Open it and drag Schugaa to your Applications folder.

## Usage 🚀

1.  **Login**: Upon first launch, choose **LibreLinkUp** or **Dexcom**, then enter your credentials and region. Passwords are stored in Keychain when available.
2.  **View Data**: The app will appear in your menu bar.
3.  **Graph**: Click the menu bar item to see the graph.
4.  **Settings**:
    - **Change Units**: Go to `Schugaa` -> `Units` to toggle between mg/dL and mmol/L.
    - **Share Debug Logs**: Go to `Schugaa` -> `Share Debug Logs` to find log files for troubleshooting.
    - **Refresh**: Click `Schugaa` -> `Refresh Now` to force an update.
    - **Logout**: Click `Schugaa` -> `Logout` to remove stored credentials.

## Troubleshooting 🛠️

- **Error 429 (Too Many Requests)**: Abbott/LibreView has strict rate limits. If you see this, the app will automatically back off and retry. If it persists, wait ~15-30 minutes.
- **No Data**: Ensure your sensor is active and uploading data to LibreView (e.g., via the LibreLink phone app).
- **Login Loop**: The app now handles redirects intelligently. If you still have issues, try "Logout" and logging in again with the correct initial region if known.
- **"App is damaged" / "Can't be opened"**: This is due to macOS Gatekeeper. To fix:
  1.  Open Terminal.
  2.  Run: `xattr -cr /Applications/Schugaa.app` (or wherever you dragged the app).
  3.  Alternatively, Right-Click the app and select **Open**.

## Credits & Acknowledgements 👏

- **[pylibrelinkup](https://github.com/robberwick/pylibrelinkup)**: A huge thanks to Rob Berwick for the excellent library that powers the API interactions in this app.
- **rumps**: For making macOS menu bar apps easy in Python.

## Support the Project ☕️

If you find Schugaa helpful, consider supporting its development!

<a href='https://ko-fi.com/abhishek0978' target='_blank'><img height='36' style='border:0px;height:36px;' src='https://storage.ko-fi.com/cdn/kofi2.png?v=3' border='0' alt='Buy Me a Coffee at ko-fi.com' /></a>

## Disclaimer ⚠️

**Schugaa is an unofficial open-source tool and is NOT affiliated with, endorsed by, or associated with Abbott Laboratories.**

This application is for informational purposes only and should **not** be used for medical decisions, diagnosis, or treatment. Always consult your official Freestyle Libre reader or app and your healthcare professional for medical advice.

---

_Built with ❤️ for the T1D community._
