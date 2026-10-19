"""Frame wire format shared by glasses, phone and laptop.

Every WebSocket binary message is one frame:

    [ seq: int32 big-endian ][ capture_ts_ms: int64 big-endian ][ JPEG bytes ... ]

seq            increments by 1 per frame captured on the glasses (gaps = dropped frames)
capture_ts_ms  glasses wall clock (ms since epoch) when the frame was captured

Keep this in sync with FrameCodec.kt in the Android apps.
"""
import struct

HEADER = struct.Struct(">iq")  # 4 + 8 = 12 bytes
HEADER_SIZE = HEADER.size


def pack(seq: int, capture_ts_ms: int, jpeg: bytes) -> bytes:
    return HEADER.pack(seq, capture_ts_ms) + jpeg


def unpack(msg: bytes):
    seq, ts = HEADER.unpack_from(msg, 0)
    return seq, ts, msg[HEADER_SIZE:]
