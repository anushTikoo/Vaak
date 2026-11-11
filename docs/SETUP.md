# Vaak (वाक्) — Environment Setup & Verification Guide

This guide details the complete developer setup on Linux (Fedora KDE) and other platforms.

---

## 1. Prerequisites Already Configured

- **Git**: `2.56.0`
- **Node.js**: `v22.23.4` (LTS managed via `fnm`)
- **Python**: `3.12.16` (Isolated and managed via `uv`)
- **uv**: `0.13.7` (Astral's fast Python package manager)

---

## 2. Android & Java Setup (Fedora Linux KDE)

For Android development with React Native and Expo (SDK 58), follow these exact steps:

### A. Install Android 32-bit Compatibility Libraries
On Fedora, run:
```bash
sudo dnf install -y glibc.i686 glibc-devel.i686 libstdc++.i686 zlib-ng-compat.i686 ncurses-devel.i686
```
*(Note: Fedora replaces legacy `zlib-devel` with `zlib-ng-compat`)*

### B. Install Android Studio (Recommended Native Method)
1. Download the official Linux archive (`.tar.gz`) from:
   https://developer.android.com/studio
2. Extract and move to `/opt` or `~/android-studio`:
   ```bash
   cd ~/Downloads
   tar -xzf android-studio-*-linux.tar.gz
   sudo mv android-studio /opt/
   ```
3. Run the initial Setup Wizard:
   ```bash
   /opt/android-studio/bin/studio.sh
   ```
4. Select **Standard Installation**. This will automatically download:
   - Android SDK Platform (API 35/36)
   - Android SDK Build-Tools
   - Android SDK Platform-Tools (`adb`)
   - Android Emulator
   - Bundled OpenJDK (JBR)

### C. Configure Environment Variables
Add the following to your `~/.bashrc` (or `~/.zshrc`):

```bash
# Android SDK & Tools
export ANDROID_HOME=$HOME/Android/Sdk
export PATH=$PATH:$ANDROID_HOME/emulator
export PATH=$PATH:$ANDROID_HOME/platform-tools
export PATH=$PATH:$ANDROID_HOME/cmdline-tools/latest/bin

# Use Android Studio's bundled OpenJDK (JetBrains Runtime)
export JAVA_HOME=/opt/android-studio/jbr
export PATH=$PATH:$JAVA_HOME/bin
```

Reload your shell configuration:
```bash
source ~/.bashrc
```

### D. Verification Commands
Run these commands to verify that the tools are working:
```bash
# Verify Java version
java -version

# Verify Android Debug Bridge
adb version

# Check connected Android devices or running emulators
adb devices
```

### E. Physical Android Phone Setup (USB Debugging)
To run and test directly on your physical Android phone without an emulator:
1. On your Android phone, go to **Settings > About Phone**.
2. Tap **Build Number** 7 times until you see "You are now a developer!".
3. Go back to **Settings > System > Developer Options**.
4. Enable **USB Debugging**.
5. Connect your phone via USB cable to your PC.
6. When prompted on your phone screen, tap **"Always allow from this computer"** and accept.
7. Run `adb devices` on your PC. Your phone will appear in the device list.

---

## 3. Starting the Project

### Running Backend (FastAPI)
```bash
# Run tests
npm run test:backend

# Start backend dev server
npm run backend
# Server will run at http://localhost:8000
# OpenAPI Docs: http://localhost:8000/docs
```

### Running Mobile (Expo)
```bash
# Start Expo bundler
npm run mobile

# Run on connected Android device / emulator
npm run android
```
