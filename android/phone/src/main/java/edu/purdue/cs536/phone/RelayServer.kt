package edu.purdue.cs536.phone

import android.util.Log
import org.java_websocket.WebSocket
import org.java_websocket.handshake.ClientHandshake
import org.java_websocket.server.WebSocketServer
import java.net.InetSocketAddress
import java.nio.ByteBuffer
import java.util.Collections

/**
 * WebSocket relay running on the phone.
 *   /ingest  <- glasses connect here and push frames
 *   /view    <- laptop (or anything else) connects here and receives every frame
 *
 * Frames are forwarded untouched, so the header from the glasses
 * (seq + capture timestamp) reaches the laptop for Part C analysis.
 */
class RelayServer(
    port: Int,
    private val onFrame: (ByteArray) -> Unit,
    private val onEvent: (String) -> Unit,
) : WebSocketServer(InetSocketAddress(port)) {

    private val viewers = Collections.synchronizedSet(mutableSetOf<WebSocket>())

    @Volatile var framesIn = 0L; private set
    @Volatile var bytesIn = 0L; private set

    init {
        isReuseAddr = true
        connectionLostTimeout = 10
    }

    override fun onStart() = onEvent("relay listening on :$port")

    override fun onOpen(conn: WebSocket, handshake: ClientHandshake) {
        when (handshake.resourceDescriptor) {
            "/view" -> { viewers.add(conn); onEvent("viewer connected (${viewers.size})") }
            "/ingest" -> onEvent("glasses connected from ${conn.remoteSocketAddress}")
            else -> conn.close(1008, "use /ingest or /view")
        }
    }

    override fun onMessage(conn: WebSocket, message: ByteBuffer) {
        if (conn.resourceDescriptor != "/ingest") return
        val bytes = ByteArray(message.remaining()).also { message.get(it) }
        framesIn++
        bytesIn += bytes.size

        synchronized(viewers) {
            for (v in viewers) if (v.isOpen) v.send(bytes)
        }
        onFrame(bytes)
    }

    override fun onMessage(conn: WebSocket, message: String) { /* unused for now */ }

    override fun onClose(conn: WebSocket, code: Int, reason: String, remote: Boolean) {
        if (viewers.remove(conn)) onEvent("viewer left (${viewers.size})")
        else onEvent("glasses disconnected ($code)")
    }

    override fun onError(conn: WebSocket?, ex: Exception) {
        Log.e("RelayServer", "error", ex)
        onEvent("error: ${ex.message}")
    }
}
