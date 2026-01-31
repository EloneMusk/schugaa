# Schugaa 🩸

Schugaa is a lightweight, native macOS menu bar application that displays real-time glucose levels from your Freestyle Libre sensor. It sits quietly in your menu bar, providing quick access to your current glucose reading, trend arrows, and a historical data graph.

<p align="center">
  <img src="https://github.com/EloneMusk/schugaa/blob/main/Screenshot.png" alt="Schugaa Preview" width="600">
</p>

## Features ✨

*   **Menu Bar Widget**: View your latest glucose value and trend arrow directly in the macOS menu bar.
*   **Interactive Graph**: Click the menu item to view a beautiful, native interactive graph of your recent history. hover over points to see exact values and timestamps.
*   **Unit Conversion**: Supports both **mg/dL** and **mmol/L**. Switch instantly via the menu.
*   **Auto-Refresh**: Data automatically refreshes in the background (every 5 minutes) and immediately when you open the menu.
*   **Region Support**: Compatible with LibreView accounts worldwide (EU, Global, DE, FR, JP, AP, AE).
*   **Native & Lightweight**: Built with Python and native macOS APIs for a seamless system integration.
*   **Universal Support**: Runs natively on both Apple Silicon (M1/M2/M3) and Intel Macs.
*   **Secure**: Your credentials are stored locally on your machine.

## Installation 📦

### Running from Source using Script
1.  Ensure you have Python 3.10+ installed.
2.  Clone this repository.
3.  Run the start script:
    ```bash
    ./run.sh
    ```
    This will automatically set up a virtual environment, install dependencies, and launch the app.

### Building the App (DMG)
To create a standalone `.dmg` file that you can install like any other Mac app:
1.  Run the package script:
    ```bash
    ./package.sh
    ```
2.  The `Schugaa.dmg` file will be created in the project folder. Open it and drag Schugaa to your Applications folder.

## Usage 🚀

1.  **Login**: Upon first launch, you will be prompted to enter your **LibreView** credentials (Email & Password) and select your region.
2.  **View Data**: The app will appear in your menu bar. 
3.  **Graph**: Click the menu bar item to see the graph.
4.  **Settings**: 
    *   **Change Units**: Go to `Schugaa` -> `Units` to toggle between mg/dL and mmol/L.
    *   **Refresh**: Click `Schugaa` -> `Refresh Now` to force an update.
    *   **Logout**: Click `Schugaa` -> `Logout` to remove stored credentials.

## Troubleshooting 🛠️

*   **Error 430 (Client Error)**: This usually means "Too Many Requests". Abbott/LibreView has strict rate limits. If you see this, wait ~15-30 minutes before trying again. The app behaves conservatively to avoid this, but frequent restarts usually trigger it.
*   **No Data**: Ensure your sensor is active and uploading data to LibreView (e.g., via the LibreLink phone app).


## Support the Project ☕️

If you find Schugaa helpful, consider supporting its development!

<a href='https://ko-fi.com/abhishek0978' target='_blank'><img height='36' style='border:0px;height:36px;' src='https://storage.ko-fi.com/cdn/kofi2.png?v=3' border='0' alt='Buy Me a Coffee at ko-fi.com' /></a>

## Disclaimer ⚠️

**Schugaa is an unofficial open-source tool and is NOT affiliated with, endorsed by, or associated with Abbott Laboratories.**

This application is for informational purposes only and should **not** be used for medical decisions, diagnosis, or treatment. Always consult your official Freestyle Libre reader or app and your healthcare professional for medical advice.

---
*Built with ❤️ for the T1D community.*
