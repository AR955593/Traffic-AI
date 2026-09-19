package com.arrajput.trafficai

import android.Manifest
import android.content.pm.PackageManager
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.util.Log
import android.webkit.GeolocationPermissions
import android.webkit.JavascriptInterface
import android.webkit.WebChromeClient
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.OnBackPressedCallback
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import androidx.credentials.CredentialManager
import androidx.credentials.CustomCredential
import androidx.credentials.GetCredentialRequest
import androidx.credentials.GetCredentialResponse
import androidx.credentials.exceptions.GetCredentialCancellationException
import androidx.credentials.exceptions.GetCredentialException
import androidx.credentials.exceptions.NoCredentialException
import com.google.android.libraries.identity.googleid.GetGoogleIdOption
import com.google.android.libraries.identity.googleid.GoogleIdTokenCredential
import com.google.android.libraries.identity.googleid.GoogleIdTokenParsingException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

private const val TAG = "TrafficAI-Auth"

class MainActivity : ComponentActivity() {

    private lateinit var webView: WebView
    private lateinit var credentialManager: CredentialManager
    private val LOCATION_PERMISSION_REQUEST_CODE = 1001
    private var backPressedOnce = false
    private val backHandler = Handler(Looper.getMainLooper())

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // Set status bar and navigation bar colors to match Dark Forest theme (#203531)
        window.statusBarColor = android.graphics.Color.parseColor("#203531")
        window.navigationBarColor = android.graphics.Color.parseColor("#203531")

        // Initialize Credential Manager for native Google Sign-In
        credentialManager = CredentialManager.create(this)

        webView = WebView(this)
        setContentView(webView)

        configureWebView()
        setupBackNavigation()
        requestLocationPermissions()

        val LOCAL_ASSET_URL = "file:///android_asset/index.html"
        webView.loadUrl(LOCAL_ASSET_URL)
    }

    private fun configureWebView() {
        val settings: WebSettings = webView.settings
        settings.javaScriptEnabled = true
        settings.domStorageEnabled = true
        settings.databaseEnabled = true
        settings.setGeolocationEnabled(true)
        settings.allowFileAccess = true
        settings.allowContentAccess = true
        settings.allowFileAccessFromFileURLs = true
        settings.allowUniversalAccessFromFileURLs = true
        settings.javaScriptCanOpenWindowsAutomatically = true
        settings.setSupportMultipleWindows(true)
        settings.mixedContentMode = WebSettings.MIXED_CONTENT_NEVER_ALLOW
        settings.useWideViewPort = false
        settings.loadWithOverviewMode = false
        settings.cacheMode = WebSettings.LOAD_NO_CACHE

        // Keep standard WebView UA for normal web content
        val defaultUa = settings.userAgentString
        settings.userAgentString = defaultUa.replace("; wv", "")

        // Register Javascript Bridge Interface
        webView.addJavascriptInterface(WebAppInterface(this), "AndroidBridge")

        webView.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView?, url: String?): Boolean {
                if (url != null && (url.startsWith("file:") || url.startsWith("https://"))) {
                    return false
                }
                return false
            }
        }

        webView.webChromeClient = object : WebChromeClient() {
            override fun onGeolocationPermissionsShowPrompt(
                origin: String?,
                callback: GeolocationPermissions.Callback?
            ) {
                val hasPermission = ContextCompat.checkSelfPermission(
                    this@MainActivity,
                    Manifest.permission.ACCESS_FINE_LOCATION
                ) == PackageManager.PERMISSION_GRANTED
                callback?.invoke(origin, hasPermission, false)
            }

            override fun onCreateWindow(
                view: WebView?,
                isDialog: Boolean,
                isUserGesture: Boolean,
                resultMsg: android.os.Message?
            ): Boolean {
                val popupWebView = WebView(this@MainActivity)
                popupWebView.settings.javaScriptEnabled = true
                popupWebView.settings.domStorageEnabled = true
                popupWebView.settings.userAgentString =
                    popupWebView.settings.userAgentString.replace("; wv", "")

                val dialog = android.app.Dialog(
                    this@MainActivity,
                    android.R.style.Theme_Black_NoTitleBar_Fullscreen
                )
                dialog.setContentView(popupWebView)
                dialog.show()

                popupWebView.webChromeClient = object : WebChromeClient() {
                    override fun onCloseWindow(window: WebView?) {
                        dialog.dismiss()
                    }
                }
                popupWebView.webViewClient = object : WebViewClient() {
                    override fun onPageFinished(view: WebView?, url: String?) {
                        super.onPageFinished(view, url)
                    }
                }

                val transport = resultMsg?.obj as? WebView.WebViewTransport
                transport?.webView = popupWebView
                resultMsg?.sendToTarget()
                return true
            }
        }
    }

    // =========================================================
    // Native Google Sign-In via Credential Manager API
    // =========================================================

    /**
     * Launches native Google Sign-In using Credential Manager.
     * Called from the JavaScript bridge when the web UI requests Google auth.
     *
     * Flow:
     *   JS "Continue with Google" button
     *     → AndroidBridge.nativeGoogleSignIn(webClientId)
     *       → Credential Manager shows native account picker
     *         → Google ID Token returned
     *           → TrafficAIHandleGoogleCredential(idToken) called in WebView
     *             → Frontend POSTs to /api/v1/auth/google
     *               → Backend validates → TrafficAI JWT issued → Dashboard opens
     */
    private fun launchNativeGoogleSignIn(webClientId: String) {
        if (webClientId.isBlank() || webClientId == "YOUR_WEB_CLIENT_ID.apps.googleusercontent.com") {
            runOnUiThread {
                webView.evaluateJavascript(
                    "window.showToast && showToast('Google Sign-In is not configured on this device. " +
                        "Please set the Google Web Client ID.', 'warning');",
                    null
                )
            }
            Log.e(TAG, "launchNativeGoogleSignIn called with unconfigured webClientId")
            return
        }

        CoroutineScope(Dispatchers.IO).launch {
            try {
                // Build the GetGoogleIdOption request
                val googleIdOption = GetGoogleIdOption.Builder()
                    .setFilterByAuthorizedAccounts(false) // Show all accounts, not just previously signed-in ones
                    .setServerClientId(webClientId)       // Must be the WEB OAuth client ID
                    .setAutoSelectEnabled(false)           // Force account picker to appear
                    .build()

                val request = GetCredentialRequest.Builder()
                    .addCredentialOption(googleIdOption)
                    .build()

                val result: GetCredentialResponse = credentialManager.getCredential(
                    request = request,
                    context = this@MainActivity
                )

                handleGoogleCredentialResult(result)

            } catch (e: GetCredentialCancellationException) {
                Log.i(TAG, "Google Sign-In cancelled by user")
                withContext(Dispatchers.Main) {
                    webView.evaluateJavascript(
                        "window.showToast && showToast('Google Sign-In was cancelled.', 'warning');",
                        null
                    )
                    // Reset buttons in JS
                    webView.evaluateJavascript(
                        "typeof setGoogleButtonsLoading === 'function' && setGoogleButtonsLoading(false);",
                        null
                    )
                }
            } catch (e: NoCredentialException) {
                Log.w(TAG, "No Google credentials available: ${e.message}")
                withContext(Dispatchers.Main) {
                    webView.evaluateJavascript(
                        "window.showToast && showToast(" +
                            "'No Google account found on this device. Please add a Google account in Settings.', " +
                            "'error');",
                        null
                    )
                    webView.evaluateJavascript(
                        "typeof setGoogleButtonsLoading === 'function' && setGoogleButtonsLoading(false);",
                        null
                    )
                }
            } catch (e: GetCredentialException) {
                Log.e(TAG, "Google Sign-In error: ${e.type} — ${e.message}")
                withContext(Dispatchers.Main) {
                    val userMsg = when {
                        e.message?.contains("network", ignoreCase = true) == true ->
                            "Network error during Google Sign-In. Please check your connection."
                        e.message?.contains("cancel", ignoreCase = true) == true ->
                            "Google Sign-In was cancelled."
                        else -> "Google Sign-In failed: ${e.type ?: "unknown error"}"
                    }
                    webView.evaluateJavascript(
                        "window.showToast && showToast('$userMsg', 'error');",
                        null
                    )
                    webView.evaluateJavascript(
                        "typeof setGoogleButtonsLoading === 'function' && setGoogleButtonsLoading(false);",
                        null
                    )
                }
            } catch (e: Exception) {
                Log.e(TAG, "Unexpected error during Google Sign-In", e)
                withContext(Dispatchers.Main) {
                    webView.evaluateJavascript(
                        "window.showToast && showToast('An unexpected error occurred during Google Sign-In.', 'error');",
                        null
                    )
                    webView.evaluateJavascript(
                        "typeof setGoogleButtonsLoading === 'function' && setGoogleButtonsLoading(false);",
                        null
                    )
                }
            }
        }
    }

    private suspend fun handleGoogleCredentialResult(result: GetCredentialResponse) {
        when (val credential = result.credential) {
            is CustomCredential -> {
                if (credential.type == GoogleIdTokenCredential.TYPE_GOOGLE_ID_TOKEN_CREDENTIAL) {
                    try {
                        val googleIdTokenCredential = GoogleIdTokenCredential
                            .createFrom(credential.data)
                        val idToken = googleIdTokenCredential.idToken

                        Log.i(TAG, "Google ID Token obtained for: ${googleIdTokenCredential.displayName}")

                        // Pass the raw Google ID token to the WebView
                        // The JS function TrafficAIHandleGoogleCredential(token) will:
                        //   1. POST to /api/v1/auth/google with the token
                        //   2. Receive TrafficAI JWT
                        //   3. Store JWT and open Home Dashboard
                        withContext(Dispatchers.Main) {
                            val escapedToken = idToken.replace("'", "\\'")
                            webView.evaluateJavascript(
                                "window.TrafficAIHandleGoogleCredential && " +
                                    "window.TrafficAIHandleGoogleCredential('$escapedToken');",
                                null
                            )
                        }
                    } catch (e: GoogleIdTokenParsingException) {
                        Log.e(TAG, "Error parsing Google ID Token", e)
                        withContext(Dispatchers.Main) {
                            webView.evaluateJavascript(
                                "window.showToast && showToast(" +
                                    "'Failed to parse Google credential. Please try again.', 'error');",
                                null
                            )
                            webView.evaluateJavascript(
                                "typeof setGoogleButtonsLoading === 'function' && setGoogleButtonsLoading(false);",
                                null
                            )
                        }
                    }
                } else {
                    Log.w(TAG, "Unexpected credential type: ${credential.type}")
                    withContext(Dispatchers.Main) {
                        webView.evaluateJavascript(
                            "window.showToast && showToast('Unexpected credential type received.', 'error');",
                            null
                        )
                        webView.evaluateJavascript(
                            "typeof setGoogleButtonsLoading === 'function' && setGoogleButtonsLoading(false);",
                            null
                        )
                    }
                }
            }
            else -> {
                Log.w(TAG, "Unhandled credential class: ${credential.javaClass.name}")
                withContext(Dispatchers.Main) {
                    webView.evaluateJavascript(
                        "window.showToast && showToast('Unrecognised Google credential. Please try again.', 'error');",
                        null
                    )
                    webView.evaluateJavascript(
                        "typeof setGoogleButtonsLoading === 'function' && setGoogleButtonsLoading(false);",
                        null
                    )
                }
            }
        }
    }

    // =========================================================
    // Back Navigation
    // =========================================================
    private fun setupBackNavigation() {
        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                webView.evaluateJavascript(
                    "window.TrafficAIHandleBack ? window.TrafficAIHandleBack() : false"
                ) { result ->
                    val handled = result == "true" || result == "\"true\""
                    if (!handled) {
                        handleNativeDoubleBackExit()
                    }
                }
            }
        })
    }

    fun handleNativeDoubleBackExit() {
        if (backPressedOnce) {
            finish()
        } else {
            backPressedOnce = true
            Toast.makeText(this, "Press back again to exit TrafficAI", Toast.LENGTH_SHORT).show()
            backHandler.postDelayed({ backPressedOnce = false }, 2000)
        }
    }

    // =========================================================
    // Location Permissions
    // =========================================================
    private fun requestLocationPermissions() {
        if (ContextCompat.checkSelfPermission(
                this,
                Manifest.permission.ACCESS_FINE_LOCATION
            ) != PackageManager.PERMISSION_GRANTED
        ) {
            ActivityCompat.requestPermissions(
                this,
                arrayOf(
                    Manifest.permission.ACCESS_FINE_LOCATION,
                    Manifest.permission.ACCESS_COARSE_LOCATION
                ),
                LOCATION_PERMISSION_REQUEST_CODE
            )
        }
    }

    // =========================================================
    // JavaScript ↔ Native Bridge
    // =========================================================
    inner class WebAppInterface(private val activity: MainActivity) {

        @JavascriptInterface
        fun exitApp() {
            activity.runOnUiThread {
                activity.finish()
            }
        }

        @JavascriptInterface
        fun showNativeToast(message: String) {
            activity.runOnUiThread {
                Toast.makeText(activity, message, Toast.LENGTH_SHORT).show()
            }
        }

        /**
         * Called by the WebView JavaScript when a Google ID Token has been obtained
         * (either via WebView GSI or passed from native Credential Manager).
         * The token is forwarded to TrafficAIHandleGoogleCredential in the WebView.
         */
        @JavascriptInterface
        fun onGoogleToken(token: String) {
            activity.runOnUiThread {
                val escapedToken = token.replace("'", "\\'")
                webView.evaluateJavascript(
                    "window.TrafficAIHandleGoogleCredential && " +
                        "window.TrafficAIHandleGoogleCredential('$escapedToken');",
                    null
                )
            }
        }

        /**
         * Called by the WebView JavaScript to request native Google Sign-In.
         * The WebView passes the google_client_id fetched from /api/v1/auth/config.
         *
         * Usage from JavaScript:
         *   if (window.AndroidBridge) {
         *     window.AndroidBridge.nativeGoogleSignIn(googleClientId);
         *   }
         */
        @JavascriptInterface
        fun nativeGoogleSignIn(webClientId: String) {
            Log.i(TAG, "nativeGoogleSignIn called with clientId: ${webClientId.take(20)}...")
            // Launch on main thread since CredentialManager needs Activity context
            activity.runOnUiThread {
                activity.launchNativeGoogleSignIn(webClientId)
            }
        }
    }
}
