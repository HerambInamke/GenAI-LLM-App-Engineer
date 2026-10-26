# Dead Air evaluation report

Generated 2026-10-26 14:47 UTC · measurements: offline providers (pipeline only)

| Metric | Result | Target | Status |
|---|---|---|---|
| NFR-1 caller latency (median, 30 turns) | 0 ms (p95 0 ms) | < 1500 ms | PASS |
| NFR-2 barge-in stop < 300 ms | 100% of 20 (p95 62 ms) | >= 95% | PASS |
| NFR-3 planted false claims caught | 100/100 | >= 90% | PASS |
| NFR-3 true claims blocked | 0/100 | < 10% | PASS |
| NFR-5 repetition (24 h, banter/feud) | 0 violations in 59 lines | 0 | PASS |
| Unsourced claims aired (gate log) | 0 | 0 | PASS |
| NFR-6 cost per hour | $0.000 (46 blocks) | < $2.00 | PASS |
| Listener rating | 0.00/5 from 0 raters | 10 raters | FAIL |
| NFR-4 soak | 0.5 h (accelerated, offline providers), 0 unhandled, 39 TTS fallbacks | 0 unhandled, fallback works | PASS |

Gate decisions in the station log: {'pass': 463}

NFR-1 here times the pipeline with offline providers. Run `python -m deadair.eval report --live` with API keys for real provider latency.

The NFR-3 claim set is generated from fixture headlines (`deadair/eval/planted.py`), so it is a regression check, not an independent benchmark.
