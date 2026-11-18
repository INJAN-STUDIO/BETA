# B.E.T.A. 5.1 - deploy guide

NEW in 5.1: soft sound effects (taps, send, reply arrives, errors, switches, menus opening and closing, copy, mic on/off,
new K-10 mail, theme change, press-and-hold menu). Menu -> "Sound effects" (on/off) and "Sound volume" (Low / Medium / High).
They are made by the phone itself, so there are no sound files. They stay silent while B.E.T.A. reads a reply aloud, while the
app is in the background, and when switched off. Nothing needs setting up on the server for this.

Everything from 5.0 is included in this zip (Firebase alerts, K-10 mail menu, tidier menu, 8 new themes, natural read-aloud).
If you have NOT deployed 5.0 yet, follow the steps below as written (the Firebase part is step 2). If you already deployed
5.0 and Firebase is set up, you only need steps 1, 3 and a hard refresh: just replace the files and push.

Version number to look for: 5.1 (APP_VERSION is already bumped in app.py).

What is new: reply alerts through Firebase (FCM) instead of ntfy, an alert + in-app notice for new K-10 mail, press-and-hold
on a mail message for Resend / Delete, a tidier menu, 8 new colour themes, the loading screen no longer explains the free
server, the Copy button no longer turns into Listen/Stop, and read-aloud now speaks like a person (no code, links, tables,
symbols). APP_VERSION is already 5.0 in app.py.

## 1. Put the files in the repo (same layout as this zip)
- app.py, system_report.py                    -> replace the old ones
- fcm_push.py, speech_text.py                 -> NEW, next to app.py
- static/app.js, style.css, themes.css, index.html -> replace the old ones in `static/`
- capacitor.config.json, android/AndroidManifest.xml -> for the Android app (see step 4)
gemini_status.py is unchanged.

## 2. Firebase (once, free) - needed for the Android app's alerts
1. console.firebase.google.com -> Add project (any name; turn Google Analytics off).
2. Project settings -> General -> Add app -> Android. Package name must be exactly:  com.beta.app
   Download `google-services.json` (keep it private).
3. Project settings -> Service accounts -> Generate new private key. This downloads a JSON file.
4. Render -> your service -> Environment -> add  FIREBASE_SERVICE_ACCOUNT  = the ENTIRE contents of that second JSON file.
   (If pasting multi-line text gives trouble, base64-encode the file and use FIREBASE_SERVICE_ACCOUNT_B64 instead.)
5. Make sure requirements.txt contains `cryptography` (pywebpush already installs it, so it is usually there).

## 3. Commit and push, then check it is live
git add app.py fcm_push.py speech_text.py system_report.py capacitor.config.json static/ android/
git commit -m "B.E.T.A. 5.1: sound effects (plus 5.0: FCM alerts, K-10 mail menu, tidier menu, more themes, natural read-aloud)" && git push
- https://beta-033v.onrender.com/api/health  -> "version":"5.1"
- https://beta-033v.onrender.com/static/app.js -> search: sfx   and   nativePush   and   attachLongPress   and   speakable
- https://beta-033v.onrender.com/static/themes.css -> search: v5.0 MORE THEMES
If a phone still looks old, open https://beta-033v.onrender.com/reset once.

## 4. Rebuild the Android app (alerts and camera live here)
The APK must contain Firebase and the push plugin. In your GitHub Actions workflow (.github/workflows/...), where it builds
the Capacitor app:
  a. Install the plugin next to your other Capacitor plugins:   npm install @capacitor/push-notifications
     (use the same major version as your @capacitor/core)
  b. After the Android project is created/synced and BEFORE the Gradle build, add the Firebase file:
       - name: Add Firebase config
         run: echo '${{ secrets.GOOGLE_SERVICES_JSON }}' > android/app/google-services.json
     and create a repository secret GOOGLE_SERVICES_JSON containing the whole google-services.json from step 2.
     (Capacitor's default Android project already applies the Google services plugin when that file exists.)
  c. Make sure the manifest lines in android/AndroidManifest.xml (camera, notifications, the Replies channel) end up in the
     built app's manifest - how that file reaches the build depends on your workflow.
  d. Run the workflow, install the new APK.
I have not seen your workflow file. If any of this does not fit, send me the file from .github/workflows/ and I will edit it.

## 5. Turn alerts on
Open the app -> Menu -> "Notify me when a reply is ready" -> allow notifications. A test alert arrives a couple of seconds
later. Menu -> System report shows "Reply alerts" with the state (and the reason if an alert ever fails).
New K-10 mail from ALPHA now sends the same kind of alert, and shows a notice and a dot on the menu button while the app is open.

## 6. Good to know
- FCM needs Google Play services on the phone. If the Honor 8X has them removed (de-Googled), the alerts cannot arrive in the
  app. In that case keep NTFY_TOPIC set on Render: ntfy still works quietly in the background as a fallback (it is only used
  when FCM could not deliver, so you never get both). It is no longer shown anywhere in the menu.
- To retire ntfy completely later: delete NTFY_TOPIC (and NTFY_SERVER / NTFY_TOKEN) on Render.
- Web page in a browser (not the app): reply alerts there still use browser Web Push if it is set up.
