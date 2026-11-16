# B.E.T.A. 4.9 - deploy guide (for ALPHA or for you)

Release 4.9 adds: System report (replaces "Gemini traffic"), card layout for wide tables, Take photo / Record video,
and deeper gradient colours on all 13 themes. APP_VERSION is already bumped to 4.9 in app.py.

## 1. Put the files in the repo (same folder layout as this zip)
- app.py                      -> next to your other .py files (replaces the old one)
- system_report.py            -> NEW, next to app.py
- static/app.js, style.css, themes.css, index.html -> the `static/` folder next to app.py (replace the old ones)
- android/AndroidManifest.xml -> see step 4 (only matters for the Android app)

gemini_status.py is unchanged. Do not delete it - the old /api/gemini/status route still uses it.

## 2. Commit and push
git add app.py system_report.py static/ && git commit -m "B.E.T.A. 4.9: System report, table cards, camera, deeper colours" && git push
Then wait for Render's Events tab to show the new deploy as Live.

## 3. Check it is really live (not just pushed)
Open each address in a browser; every search must be FOUND:
- https://beta-033v.onrender.com/api/health            -> "version":"4.9"
- https://beta-033v.onrender.com/static/app.js         -> search: runSystemReport   and   tbl-cards   and   at-photo
- https://beta-033v.onrender.com/static/style.css      -> search: sr-banner
- https://beta-033v.onrender.com/static/themes.css     -> search: DEEPER COLOURS
Menu bottom should read 4.9. If the page still looks old, open https://beta-033v.onrender.com/reset once.

## 4. Android app (camera and video)
The web page buttons are in the files above. For the INSTALLED APK, the camera needs permission lines in the app's
manifest: CAMERA, RECORD_AUDIO and the camera <queries> block. They are in android/AndroidManifest.xml. How that file
reaches the build depends on your GitHub workflow (.github/workflows/...), which I have not seen: make sure the
generated android/app/src/main/AndroidManifest.xml ends up containing those lines, then run Actions -> Build Android
APK -> Run workflow and install the new APK. Until then, "Take a photo" in the app may still open only the file picker.
