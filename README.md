# CS536 Bonus: Smart Glass Streaming + AI

Live-stream the INMO Air glasses camera to an Android phone and on to a laptop, then run an AI app (object detection) on top, measure it in the wild, and improve it.

```
 INMO glasses                 Android phone                   Laptop
 (glasses app)                (phone app, relay)              (viewer.py)
 camera -> JPEG -> WebSocket  -> :8080/ingest ... :8080/view  -> display + CSV trace
```

Each frame on the wire = `[seq int32][capture_ts_ms int64][JPEG]` (big-endian). See `laptop/protocol.py`.

## Repo layout

| Path | What |
| --- | --- |
| `android/glasses` | App that runs on the glasses: camera preview, then streams frames |
| `android/phone` | App that runs on the phone: WebSocket relay + live preview |
| `laptop/viewer.py` | Shows the stream and logs one CSV row per frame |
| `laptop/sim_relay.py`, `laptop/fake_glasses.py` | Python stand-ins so you can test without hardware |
| `Bonus-PartC/analyze.py` | Turns traces into KPIs (fps, throughput, loss, jitter, stalls, latency) and plots |

## Setup

1. Install Android Studio and Android Platform Tools (`adb`).
2. `pip install -r laptop/requirements.txt`
3. Open the `android/` folder in Android Studio and let Gradle sync.

## Step 1: sanity check on the glasses

1. Enable developer mode on the glasses (Air 2: Settings > About > My Glasses, long-press right touchpad twice, password `20210108`).
2. Plug them in over USB, confirm `adb devices` lists them.
3. In Android Studio, pick the `glasses` run config and the glasses as the target device, then Run.
4. You should see the camera preview. If you do, camera access works and the hard unknown is gone.

## Step 2: full pipeline (Part A)

1. Put the glasses and phone on the same Wi-Fi.
2. Run the `phone` app on the phone. It prints its address, e.g. `ws://192.168.1.23:8080/ingest`.
3. On the glasses app, enter that `/ingest` URL and tap **Start**.
4. Connect the laptop to the phone:
   ```
   adb -s <phone-serial> forward tcp:8080 tcp:8080
   python laptop/viewer.py --url ws://localhost:8080/view
   ```
5. Stream for more than 1 minute, then `git tag BONUS-PartA && git push --tags`.

## Testing without hardware

```
python laptop/sim_relay.py                       # terminal 1 (pretends to be the phone)
python laptop/viewer.py                          # terminal 2
python laptop/fake_glasses.py --webcam           # terminal 3 (pretends to be the glasses)
```

## Part C: analyzing traces

```
python Bonus-PartC/analyze.py "laptop/logs/*.csv" --out Bonus-PartC/results
```

End-to-end latency compares the glasses' clock to the laptop's, so it's only accurate if both clocks are synced (turn on automatic network time on both). Before each session, record the offset or use a sync step so latency numbers are trustworthy.

## Tags

`BONUS-PartA`, `BONUS-PartB`, `BONUS-PartC`, `BONUS-PartD`. Add `chunyip` as a collaborator on this private repo.
