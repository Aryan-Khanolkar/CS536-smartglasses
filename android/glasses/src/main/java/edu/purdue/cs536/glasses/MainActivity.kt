package edu.purdue.cs536.glasses

import android.Manifest
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.os.Bundle
import android.os.SystemClock
import android.util.Log
import android.util.Size
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageProxy
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import java.io.ByteArrayOutputStream
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors

/**
 * Runs ON THE GLASSES.
 * Step 1 (sanity check): shows the camera preview. If you see video, camera access works.
 * Step 2: tap Start to JPEG-encode frames and stream them to the phone relay.
 */
class MainActivity : AppCompatActivity() {

    // Tunables (later: move into a settings screen for Part B "configured in advance")
    private val targetFps = 15
    private val jpegQuality = 70
    private val resolution = Size(640, 480)

    private lateinit var previewView: PreviewView
    private lateinit var statsView: TextView
    private lateinit var urlInput: EditText
    private lateinit var toggle: Button

    private lateinit var cameraExecutor: ExecutorService
    private val sender = FrameSender { msg -> runOnUiThread { statsView.text = msg } }

    @Volatile private var streaming = false
    private var seq = 0
    private var lastFrameAt = 0L
    private var lastStatsAt = 0L
    private var lastStatsSent = 0L
    private var lastStatsBytes = 0L

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        previewView = findViewById(R.id.preview)
        statsView = findViewById(R.id.stats)
        urlInput = findViewById(R.id.serverUrl)
        toggle = findViewById(R.id.toggle)

        val prefs = getPreferences(MODE_PRIVATE)
        urlInput.setText(prefs.getString("url", "ws://192.168.1.100:8080/ingest"))

        toggle.setOnClickListener {
            if (streaming) stopStreaming() else {
                prefs.edit().putString("url", urlInput.text.toString()).apply()
                startStreaming(urlInput.text.toString())
            }
        }

        cameraExecutor = Executors.newSingleThreadExecutor()

        if (hasCameraPermission()) startCamera()
        else ActivityCompat.requestPermissions(this, arrayOf(Manifest.permission.CAMERA), REQ_CAMERA)
    }

    private fun startStreaming(url: String) {
        seq = 0
        sender.connect(url)
        streaming = true
        toggle.text = "Stop"
    }

    private fun stopStreaming() {
        streaming = false
        sender.close()
        toggle.text = "Start"
    }

    private fun startCamera() {
        val providerFuture = ProcessCameraProvider.getInstance(this)
        providerFuture.addListener({
            val provider = providerFuture.get()

            val preview = Preview.Builder().build().also {
                it.setSurfaceProvider(previewView.surfaceProvider)
            }

            @Suppress("DEPRECATION") // setTargetResolution is fine for CameraX 1.3
            val analysis = ImageAnalysis.Builder()
                .setTargetResolution(resolution)
                .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                .setOutputImageFormat(ImageAnalysis.OUTPUT_IMAGE_FORMAT_RGBA_8888)
                .build()
            analysis.setAnalyzer(cameraExecutor, ::onFrame)

            // Glasses usually expose a single camera; fall back to whatever exists.
            val selector = when {
                provider.hasCamera(CameraSelector.DEFAULT_BACK_CAMERA) -> CameraSelector.DEFAULT_BACK_CAMERA
                provider.hasCamera(CameraSelector.DEFAULT_FRONT_CAMERA) -> CameraSelector.DEFAULT_FRONT_CAMERA
                else -> {
                    statsView.text = "no camera found via CameraX"
                    return@addListener
                }
            }

            try {
                provider.unbindAll()
                provider.bindToLifecycle(this, selector, preview, analysis)
                statsView.text = "camera ok, tap Start to stream"
            } catch (e: Exception) {
                Log.e(TAG, "bind failed", e)
                statsView.text = "camera bind failed: ${e.message}"
            }
        }, ContextCompat.getMainExecutor(this))
    }

    private fun onFrame(image: ImageProxy) {
        try {
            if (!streaming) return
            val now = SystemClock.elapsedRealtime()
            if (now - lastFrameAt < 1000L / targetFps) return  // throttle to targetFps
            lastFrameAt = now

            val captureTs = System.currentTimeMillis()
            val bmp: Bitmap = image.toBitmap()
            val out = ByteArrayOutputStream(64 * 1024)
            bmp.compress(Bitmap.CompressFormat.JPEG, jpegQuality, out)
            bmp.recycle()

            sender.send(FrameCodec.pack(seq++, captureTs, out.toByteArray()))
            updateStats(now)
        } catch (e: Exception) {
            Log.e(TAG, "frame error", e)
        } finally {
            image.close()
        }
    }

    private fun updateStats(now: Long) {
        if (now - lastStatsAt < 1000) return
        val dt = (now - lastStatsAt).coerceAtLeast(1) / 1000.0
        val fps = (sender.sent - lastStatsSent) / dt
        val kbps = (sender.bytesSent - lastStatsBytes) * 8 / dt / 1000
        lastStatsAt = now; lastStatsSent = sender.sent; lastStatsBytes = sender.bytesSent
        val txt = "%s | %.1f fps | %.0f kbps | sent %d | dropped %d".format(
            if (sender.connected) "LIVE" else "not connected", fps, kbps, sender.sent, sender.dropped
        )
        runOnUiThread { statsView.text = txt }
    }

    private fun hasCameraPermission() =
        ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED

    override fun onRequestPermissionsResult(code: Int, perms: Array<out String>, results: IntArray) {
        super.onRequestPermissionsResult(code, perms, results)
        if (code == REQ_CAMERA && hasCameraPermission()) startCamera()
        else statsView.text = "camera permission denied"
    }

    override fun onDestroy() {
        super.onDestroy()
        stopStreaming()
        cameraExecutor.shutdown()
    }

    companion object {
        private const val TAG = "SGStream"
        private const val REQ_CAMERA = 1
    }
}
