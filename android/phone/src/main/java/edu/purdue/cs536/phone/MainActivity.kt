package edu.purdue.cs536.phone

import android.graphics.BitmapFactory
import android.os.Bundle
import android.os.SystemClock
import android.widget.ImageView
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import java.net.Inet4Address
import java.net.NetworkInterface
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean

/**
 * Runs ON THE PHONE. Starts the relay, shows the incoming stream, and prints
 * the address the glasses should connect to.
 */
class MainActivity : AppCompatActivity() {

    private val port = 8080
    private lateinit var server: RelayServer
    private lateinit var frameView: ImageView
    private lateinit var statsView: TextView
    private lateinit var addressView: TextView

    private val decoder = Executors.newSingleThreadExecutor()
    private val decoding = AtomicBoolean(false)
    private var lastStatsAt = 0L
    private var lastFrames = 0L
    private var lastBytes = 0L
    private var lastEvent = ""

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        frameView = findViewById(R.id.frame)
        statsView = findViewById(R.id.stats)
        addressView = findViewById(R.id.address)

        val ip = localIp() ?: "unknown-ip"
        addressView.text = "Glasses -> ws://$ip:$port/ingest\nLaptop  -> ws://$ip:$port/view  (or adb forward tcp:$port tcp:$port)"

        server = RelayServer(port, ::showFrame) { ev ->
            lastEvent = ev
            runOnUiThread { statsView.text = ev }
        }
        server.start()
    }

    /** Decode + display, skipping frames if the UI is still busy with the previous one. */
    private fun showFrame(frame: ByteArray) {
        updateStats()
        if (!decoding.compareAndSet(false, true)) return
        decoder.execute {
            try {
                val hdr = FRAME_HEADER_SIZE
                val bmp = BitmapFactory.decodeByteArray(frame, hdr, frame.size - hdr)
                if (bmp != null) runOnUiThread { frameView.setImageBitmap(bmp) }
            } finally {
                decoding.set(false)
            }
        }
    }

    private fun updateStats() {
        val now = SystemClock.elapsedRealtime()
        if (now - lastStatsAt < 1000) return
        val dt = (now - lastStatsAt).coerceAtLeast(1) / 1000.0
        val fps = (server.framesIn - lastFrames) / dt
        val kbps = (server.bytesIn - lastBytes) * 8 / dt / 1000
        lastStatsAt = now; lastFrames = server.framesIn; lastBytes = server.bytesIn
        val txt = "%.1f fps | %.0f kbps in | %d frames\n%s".format(fps, kbps, server.framesIn, lastEvent)
        runOnUiThread { statsView.text = txt }
    }

    private fun localIp(): String? =
        NetworkInterface.getNetworkInterfaces().toList()
            .filter { it.isUp && !it.isLoopback }
            .flatMap { it.inetAddresses.toList() }
            .firstOrNull { it is Inet4Address }
            ?.hostAddress

    override fun onDestroy() {
        super.onDestroy()
        try { server.stop(1000) } catch (_: Exception) {}
        decoder.shutdown()
    }

    companion object { private const val FRAME_HEADER_SIZE = 12 }
}
