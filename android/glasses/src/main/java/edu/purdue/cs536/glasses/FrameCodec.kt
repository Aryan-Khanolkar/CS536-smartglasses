package edu.purdue.cs536.glasses

import java.nio.ByteBuffer
import java.nio.ByteOrder

/**
 * Wire format (must match laptop/protocol.py):
 *   [seq: int32 BE][captureTsMs: int64 BE][JPEG bytes]
 */
object FrameCodec {
    const val HEADER_SIZE = 12

    fun pack(seq: Int, captureTsMs: Long, jpeg: ByteArray): ByteArray {
        val buf = ByteBuffer.allocate(HEADER_SIZE + jpeg.size).order(ByteOrder.BIG_ENDIAN)
        buf.putInt(seq)
        buf.putLong(captureTsMs)
        buf.put(jpeg)
        return buf.array()
    }
}
