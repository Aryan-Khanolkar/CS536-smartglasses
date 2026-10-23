# CS536 Bonus Project: Smart Glass App

Context for Claude Code. Read this before doing anything in this repo.

## The project

Purdue CS536 (Data Networks) optional bonus project, Prof. Chunyi Peng. Develop an app on INMO Air 2 smart glasses and evaluate it in the wild. Final submission due **Nov 30, 2026**, in-class demo and presentation **Dec 4, 2026**.

| Part | What | Status |
| --- | --- | --- |
| A | Live-stream the glasses camera to an Android phone, relayed to a laptop | **Done** |
| B | AI app on top of the stream: **AR Tape Measure** | Pending professor's approval, feasibility test this weekend |
| C | Field evaluation over PAL3.0 Wi-Fi and 5G: network KPIs + app KPIs | Not started |
| D | One enhancement based on Part C results, plus preliminary evaluation | Not started |
| E | 4-6 page ACM report, 10-min talk, live demo of A and B | Not started |

Git tags expected by the course: `BONUS-PartA`, `BONUS-PartB`, `BONUS-PartC`, `BONUS-PartD`. Part C trace-processing scripts must live in a folder named `Bonus-PartC/`.

## Hardware and setup

- **Glasses:** INMO Air 2, Android 9 (SDK 28), adb serial `YM00DEC8P06371`. Developer mode via Settings > About > My Glasses, long-press the right touchpad twice, password `20210108`. Wi-Fi works on both 2.4 GHz and 5 GHz (seen at 5.56 GHz on home Wi-Fi); WPA2 (WPA3 untested). No touchscreen: a touchpad tap toggles streaming. The USB link to the laptop is flaky (adb "read failed" drops); streaming itself goes over Wi-Fi.
- **Phone:** OnePlus 12R (CPH2611, Android 14), adb serial `c1a1aa06`. It replaced the Pixel 5 (Oct 22). Right now glasses and phone are on home Wi-Fi (IPv4, relay at `ws://192.168.4.91:8080`). For the demo and Part C, use the OnePlus hotspot (2.4 GHz, WPA2). Avoid iPhone hotspots: they can be IPv6-only for Android 13+ phones.
- **Laptop:** Windows, PowerShell. The repo may be inside OneDrive, which can cause Gradle file-lock errors. adb is at `%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe` (not on PATH). Python deps live in `laptop/.venv` (Python 3.14, CPU-only torch). Keep Android Studio closed while using adb from the terminal: closing it kills the adb server.
- **Start the glasses stream without touching them:** `adb -s YM00DEC8P06371 shell am start -S -n edu.purdue.cs536.glasses/.MainActivity --ez autostart true --es url ws://<phone-ip>:8080/ingest`. Then `adb -s c1a1aa06 forward tcp:8080 tcp:8080` for the laptop.
- INMO's Air 2 developer docs (https://gitee.com/inmolens/docs): the RGB camera is camera ID 0 via the standard Android camera API, touchpad gestures arrive as standard key codes, and the SDK offers 6DoF head tracking (`ArServiceSession`).

## Repo layout

- `android/glasses/`: app on the glasses. Camera capture, JPEG frames over WebSocket (OkHttp) to the phone.
- `android/phone/`: app on the phone (OnePlus 12R). WebSocket relay on port 8080. Glasses connect to `/ingest`, laptop to `/view`.
- `laptop/viewer.py`: shows the stream via `adb forward tcp:8080 tcp:8080`, logs a per-frame CSV trace to `laptop/logs/`.
- `laptop/sim_relay.py`, `laptop/fake_glasses.py`: Python stand-ins for testing without hardware.
- `Bonus-PartC/analyze.py`: turns traces into KPIs (fps, throughput, loss, jitter, stalls, latency) and plots.
- `feasibility/`: the Part B feasibility test kit (see below).
- Frame wire format: `[seq int32 BE][capture_ts_ms int64 BE][JPEG bytes]`, defined in `laptop/protocol.py` and `FrameCodec.kt`. **If Part A changed this format, update `feasibility/capture.py` to match.**

## Part B: AR Tape Measure

The user aims a crosshair on the glasses display at an object and taps the right touchpad. Within a second or two the glasses show its size and distance, e.g. "42 x 30 cm, 1.4 m away". It does not identify objects, only measures them (detection, translation, color and Lens-style apps are taken by other teams).

Pipeline per tap:
1. Capture the current frame and undistort it with the calibration.
2. **Depth:** monocular metric depth model (Depth Anything V2 Metric Indoor, or Apple Depth Pro) gives meters per pixel.
3. **Segmentation:** SAM (SAM 2 later) prompted with the crosshair point returns 3 candidate masks; a double tap cycles them.
4. **Geometry:** distance = median depth inside the eroded mask; real width = pixel width x distance / focal length (same for height).
5. Send the result back to the glasses display with the mask outline.

Scope: rigid objects with clear edges, roughly 10 cm to 2 m, indoors at 0.5 to 3 m, measuring the face pointing at the camera. Out of scope: glass and mirrors, tiny or thin objects, outdoor or far scenes.

Networking angle (Parts C and D): the models are too heavy for the phone, so each tap is an offloading decision. Compare inference on phone, laptop (edge) and cloud, and different upload resolutions. Measure tap-to-result latency (upload, inference, return), measurement error against a tape measure, throughput and failures over Wi-Fi and 5G. Part D: pick placement and resolution per tap from measured RTT and throughput to meet a latency budget, with on-phone fallback when the link drops.

## Part B build plan (once approved)

Data path, with the return leg new:

```
Glasses --tap + frame--> Phone relay --> Laptop inference server (SAM + Depth Base + geometry)
   ^                                              |
   +------------- result + outline <--------------+
```

| Part | Work | Status |
| --- | --- | --- |
| Glasses app | Crosshair overlay; right-touchpad tap sends a "measure" request with the current frame; show "W x H cm, D m" + outline; double tap cycles SAM's 3 outlines | New |
| Phone relay | Carry messages both ways (today it forwards video one way) | Small change |
| Laptop server | Turn `feasibility/measure_test.py` logic into a service: frame in, undistort + SAM (crosshair point) + Depth Base + geometry + reference correction, result out | Logic proven in feasibility |
| Settings + control (required by the handout) | Settings: server URL, model (Small/Base), upload resolution, reference object. Runtime start / stop / pause | New |
| Reference setup | One-time "aim at an object of known size" to fit the scale+shift correction | New UI, same math |

Milestones (submission Nov 30, demo Dec 4):

| By | Milestone |
| --- | --- |
| Nov 2 | End-to-end MVP: tap on glasses -> laptop measures -> number shows on glasses |
| Nov 9 | Double-tap outline cycling, settings, start/stop/pause, reference setup, "nothing found" handling |
| Nov 16 | Speed work + tap-to-result latency logging (upload / inference / return). Mid-term one-pager due |
| Nov 16-28 | Part C field runs (PAL3.0 and 5G) use this app, so Part B must be stable by mid-Nov |
| Nov 30 | Tag `BONUS-PartB`, submit; demo rehearsal on the OnePlus hotspot |

Risks:
- **Speed:** ~7.5 s per tap on the laptop CPU (SAM ~3.8 s, Depth Base ~3 s) against a 1-2 s goal. Options: faster SAM variants (MobileSAM, EfficientSAM, SAM 2 Tiny), the laptop's Intel Arc GPU via OpenVINO, or a cloud GPU. This trade-off is also the Part C/D offloading story.
- **Point-only prompt:** the glasses can't drag a box, and a single point sometimes picks the wrong outline in clutter (seen in feasibility). Mitigations: double-tap cycling; maybe auto-pick the outline with the most uniform depth. Test early.

Model licenses (free, run locally; check before quoting in the report): Depth Anything V2 Small and SAM are Apache 2.0; Depth Anything V2 Base is CC BY-NC 4.0 (non-commercial); Depth Pro uses Apple's research license.

## Current focus: feasibility test

The professor will approve Part B only if accuracy looks achievable. Pass bar: **corrected error under ~10% at 0.5 to 3 m**. Full steps are in `feasibility/README.md`.

- `feasibility/capture.py`: live stream with a center crosshair; S saves the raw frame.
- `feasibility/calibrate.py`: checkerboard photos to focal length, optical center and distortion, saved to `feasibility/calib.json`.
- `feasibility/measure_test.py`: per photo, click (or Enter for crosshair), SAM masks (N cycles, Enter accepts), depth model, then error vs tape values in `feasibility/objects.csv`, raw and after a one-time reference-object scale correction, broken down by distance. Clicks are cached in `feasibility/clicks.json`.

The geometry and calibration code were verified on synthetic data. The depth and SAM code runs unchanged on CPU with `transformers` 5.x (`laptop/.venv`). `measure_test.py` now also accepts a dragged box as the SAM prompt (more reliable than a click in cluttered scenes) and has `--redo` to re-pick selected photos.

### Status (Oct 23)

- Tasks 1-4 done. Calibration: `feasibility/calib.json`, fx ~490 px (±2%), 0.13 px reprojection error. The camera's own metadata (452 px) and the `--hfov 70` default are ~8-9% off, so don't use them.
- Test set: 20 photos in `objects.csv` (box reference at 1 and 2 m, plus box, paper, monitor, chair, suitcase, guitar at 1 / 2 / 2.5 m). Floor-object distances are slant distances from a ~1.67 m eye height, so their ground truth is less certain.
- Best result: Depth Anything V2 Metric Indoor **Base** + box prompts + a scale-and-shift correction fitted on the reference shots gives distance ~6% mean error and size ~8-11% mean (`results_base.csv`). Small model: ~20% distance error (`results.csv`).
- Task 5: the Base model is done; Depth Pro is not tried yet. Task 6: summary for the professor in progress.

### Tasks, in order

1. Check that `feasibility/capture.py` matches the current frame format from Part A.
2. Install deps: `pip install torch transformers pillow opencv-python websockets numpy`. Run `measure_test.py` on a webcam photo or any image with a fake `objects.csv` row so both models download and run end to end on CPU. Fix any errors.
3. Help me calibrate the glasses camera and capture the test shots, following `feasibility/README.md`.
4. Run the test, then help me interpret `results.csv`: which objects or distances are worst, and whether the reference correction helps.
5. If time allows, compare against the Base depth model and Depth Pro, and try fixes for the worst cases.
6. Summarize the results in a short table I can send to the professor.

## Rules

- Explain what you'll do before running anything that changes the glasses or phone.
- Keep changes focused on the current task. Don't refactor unrelated code.
- If Gradle hits OneDrive file-lock errors, tell me instead of working around it silently.
- **Git: never add "Co-Authored-By" or any other AI attribution line to commit messages.** Commit with clear messages, but don't push or tag unless I ask.
- Explain things with an analogy first, then the technical detail, and spell out abbreviations the first time.
