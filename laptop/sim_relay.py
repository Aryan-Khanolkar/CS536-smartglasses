"""Python stand-in for the phone app, so you can test without the phone.

Accepts the glasses (or fake_glasses.py) on /ingest and forwards every frame
to all viewers connected on /view. Same paths and port as the real phone app.

    python sim_relay.py            # listens on 0.0.0.0:8080
"""
import argparse
import asyncio

import websockets

viewers: set = set()


async def handler(ws):
    path = ws.request.path
    if path == "/view":
        viewers.add(ws)
        print(f"viewer connected ({len(viewers)} total)")
        try:
            await ws.wait_closed()
        finally:
            viewers.discard(ws)
            print("viewer left")
    elif path == "/ingest":
        print("glasses connected")
        n = 0
        async for msg in ws:
            n += 1
            for v in list(viewers):
                try:
                    await v.send(msg)
                except websockets.ConnectionClosed:
                    viewers.discard(v)
        print(f"glasses left after {n} frames")
    else:
        await ws.close(code=1008, reason="use /ingest or /view")


async def main(port: int):
    async with websockets.serve(handler, "0.0.0.0", port, max_size=None, ping_interval=None):
        print(f"relay listening on :{port}  (/ingest, /view)")
        await asyncio.Future()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8080)
    asyncio.run(main(ap.parse_args().port))
