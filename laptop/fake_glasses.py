"""Python stand-in for the glasses: sends frames to a relay's /ingest.

Uses your webcam if one is available (--webcam), otherwise a synthetic test pattern.

    python fake_glasses.py --url ws://localhost:8080/ingest
    python fake_glasses.py --url ws://<phone-ip>:8080/ingest --webcam
"""
import argparse
import asyncio
import time

import cv2
import numpy as np
import websockets

from protocol import pack


def synthetic(i: int, w=640, h=480):
    img = np.zeros((h, w, 3), np.uint8)
    x = (i * 8) % w
    cv2.rectangle(img, (x, 180), (x + 80, 300), (255, 160, 0), -1)
    cv2.putText(img, f"frame {i}", (20, 460), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
    return img


async def run(url, fps, quality, webcam, duration):
    cap = cv2.VideoCapture(0) if webcam else None
    period = 1.0 / fps
    seq = 0
    t0 = time.time()
    async with websockets.connect(url, max_size=None, ping_interval=None) as ws:
        print(f"streaming to {url} at {fps} fps")
        while duration is None or time.time() - t0 < duration:
            t = time.time()
            if cap is not None:
                ok, img = cap.read()
                if not ok:
                    break
            else:
                img = synthetic(seq)
            ok, jpg = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
            await ws.send(pack(seq, int(time.time() * 1000), jpg.tobytes()))
            seq += 1
            await asyncio.sleep(max(0.0, period - (time.time() - t)))
    print(f"sent {seq} frames")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="ws://localhost:8080/ingest")
    ap.add_argument("--fps", type=float, default=15)
    ap.add_argument("--quality", type=int, default=70)
    ap.add_argument("--webcam", action="store_true")
    ap.add_argument("--duration", type=float, default=None)
    a = ap.parse_args()
    asyncio.run(run(a.url, a.fps, a.quality, a.webcam, a.duration))
