package edu.purdue.cs536.glasses

import android.util.Log
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import okio.ByteString.Companion.toByteString
import java.util.concurrent.TimeUnit

/**
 * Sends frames to the phone relay over a WebSocket.
 *
 * Backpressure: if the socket's send queue is backed up (slow network), new
 * frames are dropped instead of queued, so latency stays low. Dropped frames
 * show up as seq gaps on the laptop, which is exactly what Part C measures.
 */
class FrameSender(private val onStatus: (String) -> Unit) {

    private val client = OkHttpClient.Builder()
        .readTimeout(0, TimeUnit.MILLISECONDS)
        .build()

    @Volatile private var ws: WebSocket? = null
    @Volatile var connected = false
        private set

    var maxQueueBytes = 512 * 1024L

    var sent = 0L; private set
    var dropped = 0L; private set
    var bytesSent = 0L; private set

    fun connect(url: String) {
        close()
        val req = Request.Builder().url(url).build()
        ws = client.newWebSocket(req, object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                connected = true
                onStatus("connected to $url")
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                connected = false
                Log.e(TAG, "ws failure", t)
                onStatus("connection failed: ${t.message}")
            }

            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                connected = false
                onStatus("closed ($code) $reason")
            }
        })
    }

    /** Returns true if the frame was queued, false if it was dropped. */
    fun send(frame: ByteArray): Boolean {
        val socket = ws
        if (socket == null || !connected || socket.queueSize() > maxQueueBytes) {
            dropped++
            return false
        }
        val ok = socket.send(frame.toByteString())
        if (ok) { sent++; bytesSent += frame.size } else dropped++
        return ok
    }

    fun close() {
        ws?.close(1000, "bye")
        ws = null
        connected = false
    }

    companion object { private const val TAG = "FrameSender" }
}
