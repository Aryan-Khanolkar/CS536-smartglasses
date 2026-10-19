"""Laptop viewer: connects to the phone relay, shows the live stream, logs every frame.

Usage:
    # phone plugged in over USB (recommended):
    adb forward tcp:8080 tcp:8080
    python viewer.py --url ws://localhost:8080/view

    # or over Wi-Fi, using the IP shown in the phone app:
    python viewer.py --url ws://192.168.1.23:8080/view

Press q in the video window to stop. A CSV trace is written to logs/ for Part C.
"""
import argparse
import asyncio
import csv
import os
import time

import cv2
import numpy as np
import websockets

from protocol import unpack


def now_ms() -> int:
    return int(time.time() * 1000)


async def run(url: str, show: bool, log_dir: str, duration: float | None):
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, time.strftime("run_%Y%m%d_%H%M%S.csv"))
    f = open(log_path, "w", newline="")
    w = csv.writer(f)
    w.writerow(["seq", "capture_ts_ms", "recv_ts_ms", "bytes"])

    frames, last_seq, lost = 0, None, 0
    t_start = time.time()
    t_win, n_win, b_win, fps, kbps = time.time(), 0, 0, 0.0, 0.0

    print(f"connecting to {url} ... logging to {log_path}")
    try:
        async with websockets.connect(url, max_size=None, ping_interval=None) as ws:
            print("connected")
            async for msg in ws:
                recv = now_ms()
                if isinstance(msg, str):
                    continue  # ignore text/control messages
                seq, cap_ts, jpeg = unpack(msg)
                w.writerow([seq, cap_ts, recv, len(msg)])

                if last_seq is not None and seq > last_seq + 1:
                    lost += seq - last_seq - 1
                last_seq = seq
                frames += 1
                n_win += 1
                b_win += len(msg)

                if time.time() - t_win >= 1.0:
                    dt = time.time() - t_win
                    fps, kbps = n_win / dt, b_win * 8 / dt / 1000
                    t_win, n_win, b_win = time.time(), 0, 0
                    f.flush()

                if show:
                    img = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
                    if img is not None:
                        txt = f"seq {seq}  {fps:.1f} fps  {kbps:.0f} kbps  lost {lost}  e2e {recv - cap_ts} ms"
                        cv2.putText(img, txt, (8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2)
                        cv2.imshow("smartglass stream", img)
                        if cv2.waitKey(1) & 0xFF == ord("q"):
                            break

                if duration and time.time() - t_start >= duration:
                    break
    except (OSError, websockets.ConnectionClosed) as e:
        print(f"connection ended: {e!r}")
    finally:
        f.close()
        if show:
            cv2.destroyAllWindows()
        print(f"done: {frames} frames, {lost} lost, trace at {log_path}")
    return log_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="ws://localhost:8080/view")
    ap.add_argument("--no-show", action="store_true", help="log only, no video window")
    ap.add_argument("--logs", default="logs")
    ap.add_argument("--duration", type=float, default=None, help="stop after N seconds")
    a = ap.parse_args()
    asyncio.run(run(a.url, not a.no_show, a.logs, a.duration))


if __name__ == "__main__":
    main()
