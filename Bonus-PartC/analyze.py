"""Part C: turn viewer.py CSV traces into KPIs and plots.

    python analyze.py ../laptop/logs/*.csv --out results/

Per run it reports:
  frames, duration, fps, throughput (kbps), frame loss (seq gaps),
  inter-arrival jitter (std of gaps), stalls (gaps > --stall-ms),
  end-to-end latency (recv - capture; only meaningful if glasses and laptop
  clocks are synced, see README).
"""
import argparse
import glob
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def kpis(df: pd.DataFrame, stall_ms: float) -> dict:
    df = df.sort_values("recv_ts_ms")
    dur_s = (df.recv_ts_ms.iloc[-1] - df.recv_ts_ms.iloc[0]) / 1000 or 1e-9
    gaps = np.diff(df.recv_ts_ms.values)
    seq_span = df.seq.max() - df.seq.min() + 1
    lat = (df.recv_ts_ms - df.capture_ts_ms).values
    stalls = gaps[gaps > stall_ms]
    return {
        "frames": len(df),
        "duration_s": round(dur_s, 1),
        "fps": round(len(df) / dur_s, 2),
        "throughput_kbps": round(df.bytes.sum() * 8 / dur_s / 1000, 1),
        "loss_pct": round(100 * (1 - len(df) / seq_span), 2),
        "jitter_ms": round(float(np.std(gaps)), 1) if len(gaps) else 0,
        "stalls": int(len(stalls)),
        "stall_time_s": round(float(stalls.sum()) / 1000, 2),
        "latency_p50_ms": round(float(np.percentile(lat, 50)), 1),
        "latency_p95_ms": round(float(np.percentile(lat, 95)), 1),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("traces", nargs="+")
    ap.add_argument("--out", default="results")
    ap.add_argument("--stall-ms", type=float, default=500)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    paths = sorted(p for pat in a.traces for p in glob.glob(pat))
    rows, lat_all = [], []
    for p in paths:
        df = pd.read_csv(p)
        if len(df) < 2:
            continue
        k = kpis(df, a.stall_ms)
        k["run"] = os.path.basename(p)
        rows.append(k)
        lat_all.append((k["run"], (df.recv_ts_ms - df.capture_ts_ms).values))

        # per-run timeline: throughput per second + latency
        t = (df.recv_ts_ms - df.recv_ts_ms.iloc[0]) / 1000
        sec = t.astype(int)
        tput = df.groupby(sec).bytes.sum() * 8 / 1000
        fig, ax = plt.subplots(2, 1, figsize=(8, 5), sharex=True)
        ax[0].plot(tput.index, tput.values)
        ax[0].set_ylabel("throughput (kbps)")
        ax[1].plot(t, df.recv_ts_ms - df.capture_ts_ms, lw=0.8)
        ax[1].set_ylabel("e2e latency (ms)")
        ax[1].set_xlabel("time (s)")
        fig.suptitle(k["run"])
        fig.tight_layout()
        fig.savefig(os.path.join(a.out, k["run"].replace(".csv", "_timeline.png")), dpi=120)
        plt.close(fig)

    if not rows:
        print("no usable traces")
        return

    summary = pd.DataFrame(rows).set_index("run")
    summary.to_csv(os.path.join(a.out, "summary.csv"))
    print(summary.to_string())

    # latency CDF across runs
    fig, ax = plt.subplots(figsize=(6, 4))
    for name, lat in lat_all:
        x = np.sort(lat)
        ax.plot(x, np.arange(1, len(x) + 1) / len(x), label=name[:24])
    ax.set_xlabel("end-to-end latency (ms)")
    ax.set_ylabel("CDF")
    if len(lat_all) <= 8:
        ax.legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(os.path.join(a.out, "latency_cdf.png"), dpi=120)
    print(f"\nplots and summary.csv written to {a.out}/")


if __name__ == "__main__":
    main()
