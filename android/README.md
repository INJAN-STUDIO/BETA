# B.E.T.A. as a real Android app (shows up in your app menu)

Firefox-based browsers (Fennec, Firefox, Mull...) can only put a *shortcut* on the home screen. Android's
app menu lists real apps only. This tiny project wraps B.E.T.A. in one, with your B.E.T.A. icon.
It uses the phone's built-in WebView, so it works the same whatever browser you normally use, and it
updates itself whenever you redeploy the website. No Google Play Services, no extra libraries.

## Build it (about 10 minutes, once)

1. Install **Android Studio** on your laptop (Fedora: the tar.gz from developer.android.com, or Flatpak).
2. **File -> Open** and choose this `android` folder. Let it sync (it downloads Gradle and the Android SDK).
3. Open `app/src/main/res/values/strings.xml` and change `beta_url` to your Render address,
   e.g. `https://beta-xxxx.onrender.com` (keep `https`, no trailing slash).
4. **Build -> Build Bundle(s) / APK(s) -> Build APK(s)**. When it finishes, click *locate*.
5. Copy `app-debug.apk` to your phone (USB, or any file transfer), open it, and allow
   "install from this source" when asked. B.E.T.A. now appears in your app menu.

Phone plugged in with USB debugging on? Skip steps 4-5 and just press the green Run button.

## Notes

- Your login, theme and settings are kept between launches. Open links to other sites go to your browser.
- If the free Render server is asleep, the app shows "Can't reach B.E.T.A." with a Try again button;
  B.E.T.A.'s own "waking up" screen appears once the server answers.
- The "Attach" button opens your phone's file picker.
- It needs the phone's **Android System WebView** to be reasonably recent (it's part of Android and
  updates with the system). If B.E.T.A. looks broken inside the app but fine in Fennec, update WebView.
- I could not compile this inside my sandbox (no Android SDK there), so if Android Studio shows an error,
  send me the message and I'll fix it. Studio may also offer to upgrade the Gradle plugin version: say yes.
