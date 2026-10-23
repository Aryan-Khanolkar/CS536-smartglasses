# Feasibility test: AR Tape Measure

Goal: find out how accurately one glasses frame can give an object's distance and size.
Pass bar: corrected error under ~10% at 0.5 to 3 m.

## Before you start (on the laptop, about 20 min)

```
pip install torch transformers pillow opencv-python websockets numpy
```

Then run `measure_test.py` once on any photo so the models download (a few hundred MB) before the weekend.

Things to have ready:
- A printed checkerboard taped flat to cardboard (OpenCV's 10 x 7-square pattern works, search "opencv checkerboard pattern pdf")
- A tape measure
- ~10 objects with flat front faces: boxes, books, monitor, chair back, door, cabinet
- One box you measure very carefully: this is the reference object

## 1. Stream from the glasses

Same as Part A: glasses app streaming to the phone app, phone plugged into the laptop, then:

```
adb -s <phone-serial> forward tcp:8080 tcp:8080
```

## 2. Calibrate the camera (about 30 min)

```
python feasibility/capture.py --out feasibility/calib
```

Hold the checkerboard in front of the glasses and press **S** 15 to 20 times:
different angles, near and far, and some with the board near the edges of the frame. Then:

```
python feasibility/calibrate.py --images feasibility/calib --square-cm <your square size> --cols 9 --rows 6
```

Check the printed reprojection error: under 0.5 px is good. Over 1 px, retake the photos.

## 3. Capture the test shots (about 1 hour)

```
python feasibility/capture.py --out feasibility/captures
```

For each object, at 1 m, 2 m and 3 m:
1. Measure the distance from the glasses to the object's front face with the tape. Stand still.
2. Put the green crosshair on the object and press **S**.
3. Write the printed file name plus the tape values into `feasibility/objects.csv`.

Also shoot the reference box at 1 m and 2 m and mark those rows `ref=1`.

## 4. Run the test

```
python feasibility/measure_test.py
```

For each photo: click the object (or Enter for the crosshair), press **N** until the colored outline covers
exactly the face you measured, then **Enter**. Clicks are saved, so reruns are automatic.

It prints the error stats (raw and after reference correction), the error by distance range, and writes
`feasibility/results.csv`.

Optional second run with a bigger depth model to compare:
```
python feasibility/measure_test.py --depth-model depth-anything/Depth-Anything-V2-Metric-Indoor-Base-hf --out feasibility/results_base.csv
```

## What to send the professor

- Mean and worst error for distance and size, raw and corrected
- Error by distance (1 / 2 / 3 m)
- One or two example photos with the outline and the measured vs true values
