# WaveType benchmarks

These are development measurements from **October 12, 2026**, not a general latency claim. The sample size is small, and the published beta installer was not itself benchmarked in this run. Use the numbers to understand what was measured and to compare new, reproducible results.

## Test setup

- **Machine:** NVIDIA GTX 1650 4 GB, AMD Ryzen 7 4800H.
- **Input:** one seven-second sample WAV, replayed three measured times per path.
- **Resident engine:** one additional warmup replay before measurements.
- **Timing window:** from replay release to final text ready; audio duration and model startup are excluded.
- **Prior script path:** prompt caching was disabled, and model startup was reported separately.
- **Percentiles:** p50/p95 across the three measured replays. With only three runs, these figures are descriptive rather than stable estimates.

## Replay latency

All times are seconds. Cleanup refers to optional Smart cleanup; release-to-ready is the end-to-end time after the recording is released.

| Path | ASR p50/p95 | Cleanup p50/p95 | Release to ready p50/p95 |
| --- | --- | --- | --- |
| Prior GPU | 1.28/1.28 | 4.77/4.78 | 6.04/6.05 |
| Resident engine GPU | 0.70/0.72 | 0.96/0.98 | 1.69/1.69 |
| Prior CPU simulation | 1.40/1.83 | 10.01/10.02 timeout | 11.42/11.84, raw fallback |
| Resident engine CPU only | 0.74/0.86 | 3.02/3.05 | 3.76/3.94 |

The CPU comparison uses a **simulation** for the prior path. It should not be read as a cross-machine or installer benchmark.

## Other observations

- Enabling prompt caching cut a short correction's GPU cleanup from about **4.0 s** to **0.24–0.43 s** after warmup.
- On the same short correction, CPU cleanup took **1.21 s** after a **13.94 s** startup.
- The 32-case text fixture benchmark passed **29 cases**, with **0.404 s** median cleanup. The misses were a singular/plural grammar change, one extra comma, and a JSON quantity correction that kept the old number. Valid JSON can still be semantically wrong.
- Redux cannot use `parakeet-cli --stream`; its CLI reports that the model is not cache-aware. Pauses can be transcribed in the background, but the final segment still incurs ASR work at release.
- An official **213 MB packed Redux model** produced the same sample text but took **25–27 s per clip** on this CPU/build, so Q8 remains the default.

## Run your own evaluation

From a Windows source checkout, use `evaluate.py` to measure a WAV replay, or a JSONL manifest to compare raw ASR output with labeled speech:

```powershell
python evaluate.py path\to\clip.wav --smart --tier auto --warmup
python evaluate.py path\to\clip.wav --smart --tier cpu --warmup
python evaluate.py --manifest recordings.jsonl
```

Manifest lines contain a WAV path and exact reference text:

```json
{"wav":"clip1.wav","reference":"the exact words you spoke"}
```

Replay requires mono 16-bit PCM WAV. The report includes p50/p95 stage latency, raw/final text, and word error rate against raw ASR. Word error rate is meaningful only with your own labeled recordings. When sharing results, include hardware, model/runtime versions, sample lengths, run count, warmup behavior, and whether cleanup was enabled; remove personal speech from logs and examples.
