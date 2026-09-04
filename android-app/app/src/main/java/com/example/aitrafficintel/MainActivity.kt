package com.example.aitrafficintel

import android.Manifest
import android.content.pm.PackageManager
import android.os.Bundle
import android.os.Handler
import android.os.Looper
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

class MainActivity : ComponentActivity() {

    private lateinit var webView: WebView
    private val LOCATION_PERMISSION_REQUEST_CODE = 1001
    private var backPressedOnce = false
    private val backHandler = Handler(Looper.getMainLooper())

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // Set status bar and navigation bar colors to match Dark Forest theme (#203531)
        window.statusBarColor = android.graphics.Color.parseColor("#203531")
        window.navigationBarColor = android.graphics.Color.parseColor("#203531")

        webView = WebView(this)
        setContentView(webView)

        configureWebView()
        setupBackNavigation()
        requestLocationPermissions()

        webView.loadUrl("file:///android_asset/index.html")
    }

    private fun configureWebView() {
        val settings: WebSettings = webView.settings
        settings.javaScriptEnabled = true
        settings.domStorageEnabled = true
        settings.databaseEnabled = true
        settings.setGeolocationEnabled(true)
        settings.allowFileAccess = true
        settings.allowContentAccess = true
        settings.mixedContentMode = WebSettings.MIXED_CONTENT_ALWAYS_ALLOW
        settings.useWideViewPort = true
        settings.loadWithOverviewMode = true
        settings.cacheMode = WebSettings.LOAD_DEFAULT

        // Register Javascript Bridge Interface
        webView.addJavascriptInterface(WebAppInterface(this), "AndroidBridge")

        webView.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView?, url: String?): Boolean {
                return false
            }
        }

        webView.webChromeClient = object : WebChromeClient() {
            override fun onGeolocationPermissionsShowPrompt(
                origin: String?,
                callback: GeolocationPermissions.Callback?
            ) {
                callback?.invoke(origin, true, false)
            }
        }
    }

    private fun setupBackNavigation() {
        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                // Query JavaScript app to handle back action with priority order
                webView.evaluateJavascript("window.TrafficAIHandleBack ? window.TrafficAIHandleBack() : false") { result ->
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
            Toast.makeText(this, "Press back again to exit", Toast.LENGTH_SHORT).show()
            backHandler.postDelayed({ backPressedOnce = false }, 2000)
        }
    }

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
    }
}
