"""Grab still frames from the live glasses stream for the feasibility test.

Connects to the phone relay like viewer.py does, shows the stream, and saves
the current frame when you press S. Frames are saved exactly as the glasses
sent them (same resolution and JPEG quality the real app will use).

    adb -s <phone-serial> forward tcp:8080 tcp:8080
    python feasibility/capture.py --out feasibility/captures

Keys:  S = save frame    C = toggle crosshair    Q = quit

Tip: name things as you go. After each save the console prints the file name;
write it into objects.csv next to the tape-measure values.
"""
import argparse
import asyncio
import os
import struct
import time

import cv2
import numpy as np
import websockets

HEADER = struct.Struct(">iq")  # [seq int32][capture_ts_ms int64], same as laptop/protocol.py


async def run(url: str, out_dir: str):
    os.makedirs(out_dir, exist_ok=True)
    state = {"saved": 0, "crosshair": True}
    print(f"connecting to {url} ... frames will be saved to {out_dir}")
    # The glasses/phone link drops now and then; reconnect instead of losing the session.
    while True:
        try:
            if await stream(url, out_dir, state):
                break  # Q pressed
        except (OSError, websockets.ConnectionClosed) as e:
            print(f"connection lost ({e!r}), reconnecting in 2 s ...")
            await asyncio.sleep(2)
    cv2.destroyAllWindows()
    print(f"done, {state['saved']} frames in {out_dir}")


async def stream(url: str, out_dir: str, state: dict) -> bool:
    """Show and save frames until Q (returns True) or the connection drops (raises)."""
    async with websockets.connect(url, max_size=None, ping_interval=None) as ws:
        print("connected. S = save, C = crosshair, Q = quit")
        async for msg in ws:
            if isinstance(msg, str):
                continue
            jpeg = msg[HEADER.size:]
            img = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
            if img is None:
                continue

            view = img.copy()
            h, w = view.shape[:2]
            if state["crosshair"]:  # same aim point the app will use
                cv2.drawMarker(view, (w // 2, h // 2), (0, 255, 0), cv2.MARKER_CROSS, 24, 2)
            cv2.putText(view, f"saved: {state['saved']}   [S]ave [C]rosshair [Q]uit", (8, 22),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2)
            cv2.imshow("capture", view)

            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                return True
            if key == ord("c"):
                state["crosshair"] = not state["crosshair"]
            if key == ord("s"):
                name = time.strftime("img_%Y%m%d_%H%M%S") + f"_{state['saved']:03d}.jpg"
                with open(os.path.join(out_dir, name), "wb") as f:
                    f.write(jpeg)  # raw bytes from the glasses, no re-encoding
                state["saved"] += 1
                print(f"saved {name}  ({w}x{h})")
    raise websockets.ConnectionClosed(None, None)  # server ended the stream cleanly; reconnect


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="ws://localhost:8080/view")
    ap.add_argument("--out", default="feasibility/captures")
    a = ap.parse_args()
    asyncio.run(run(a.url, a.out))
