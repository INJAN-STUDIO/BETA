package app.beta.assistant;

import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.view.ViewGroup;
import android.webkit.CookieManager;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

/**
 * B.E.T.A. as a real Android app: a full-screen window around the B.E.T.A. web page.
 * It appears in your app menu with the B.E.T.A. icon, works with any browser setup (it uses the phone's
 * built-in Android System WebView), and updates itself whenever you redeploy the website.
 */
public class MainActivity extends Activity {

    private static final int FILE_REQUEST = 7;

    private WebView web;
    private ValueCallback<Uri[]> fileCallback;
    private String baseUrl;
    private String host;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        baseUrl = getString(R.string.beta_url).trim();
        host = Uri.parse(baseUrl).getHost();

        web = new WebView(this);
        web.setBackgroundColor(Color.parseColor("#051A22"));
        setContentView(web, new ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));

        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);                    // keeps your theme / text size / voice choice
        s.setAllowFileAccess(false);                     // the page can't read files on the phone
        s.setAllowContentAccess(false);
        s.setSupportMultipleWindows(false);
        s.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);

        CookieManager.getInstance().setAcceptCookie(true);   // keeps you logged in

        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri uri = request.getUrl();
                if (host != null && host.equalsIgnoreCase(uri.getHost())) {
                    return false;                         // B.E.T.A. pages stay inside the app
                }
                try {                                     // everything else opens in your browser
                    startActivity(new Intent(Intent.ACTION_VIEW, uri));
                } catch (ActivityNotFoundException ignored) { }
                return true;
            }

            @Override
            public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                if (request.isForMainFrame()) {
                    showOfflinePage();
                }
            }
        });

        // "Attach" button: lets the page open the phone's file picker.
        web.setWebChromeClient(new WebChromeClient() {
            @Override
            public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback,
                                             FileChooserParams params) {
                if (fileCallback != null) {
                    fileCallback.onReceiveValue(null);
                }
                fileCallback = callback;
                try {
                    startActivityForResult(params.createIntent(), FILE_REQUEST);
                } catch (ActivityNotFoundException e) {
                    fileCallback = null;
                    return false;
                }
                return true;
            }
        });

        if (savedInstanceState == null) {
            web.loadUrl(baseUrl);
        } else {
            web.restoreState(savedInstanceState);
        }
    }

    private void showOfflinePage() {
        String html = "<html><head><meta name='viewport' content='width=device-width,initial-scale=1'></head>"
                + "<body style='margin:0;background:#051a22;color:#e9f8fb;font-family:sans-serif;"
                + "display:flex;align-items:center;justify-content:center;height:100vh;text-align:center'>"
                + "<div style='padding:24px'><div style='font-size:22px;font-weight:800;letter-spacing:.08em'>B.E.T.A</div>"
                + "<p style='color:#86aab5;line-height:1.5'>Can't reach B.E.T.A. right now.<br>"
                + "Check your connection. If you're online, the free server may still be waking up (up to a minute).</p>"
                + "<a href='" + baseUrl + "' style='display:inline-block;margin-top:10px;padding:12px 28px;"
                + "border-radius:12px;background:#1a8de0;color:#fff;text-decoration:none;font-weight:700'>Try again</a>"
                + "</div></body></html>";
        web.loadDataWithBaseURL(null, html, "text/html", "utf-8", null);
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        if (requestCode == FILE_REQUEST && fileCallback != null) {
            fileCallback.onReceiveValue(WebChromeClient.FileChooserParams.parseResult(resultCode, data));
            fileCallback = null;
        } else {
            super.onActivityResult(requestCode, resultCode, data);
        }
    }

    @Override
    public void onBackPressed() {
        if (web.canGoBack()) {
            web.goBack();
        } else {
            super.onBackPressed();
        }
    }

    @Override
    protected void onSaveInstanceState(Bundle outState) {
        super.onSaveInstanceState(outState);
        web.saveState(outState);
    }

    @Override
    protected void onPause() {
        super.onPause();
        web.onPause();
        CookieManager.getInstance().flush();             // write the login cookie to disk
    }

    @Override
    protected void onResume() {
        super.onResume();
        web.onResume();
    }

    @Override
    protected void onDestroy() {
        web.destroy();
        super.onDestroy();
    }
}
