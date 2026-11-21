# GTA VI trophy rarity forecaster

A small, dependency-free Python program that forecasts, for every
PlayStation 5 trophy of Grand Theft Auto VI, the percent of tracked
players who will have earned it at a case's target time, as five
quantiles (5%, 25%, 50%, 75%, 95%).

## How it works

- Work happens on the log-odds (logit) scale, matching the contest's
  scoring: equal logit moves matter equally for rare and common
  trophies.
- Each trophy's drift is estimated from the contrast between the
  average of its earliest reads and the average of its latest reads,
  which resists single noisy reads.
- The drift is projected over a saturating horizon
  (`h * 42 / (h + 42)` hours) and the total move of the median is
  capped, because launch-week growth bends rather than running
  straight for a week.
- Drift and volatility are estimated from the most recent 48 hours
  of reads only, because launch-week curves bend.
- The quantile spread grows with the square root of the horizon and
  adapts to each trophy's own observed step size, shrunk toward the
  plain stay-put spread of 0.5 logit units per root day, and it
  opens a little wider when the drift has moved the median.

## Running it

The grader runs `python3 /bot/main.py` with one case file in
`/input`. Locally:

```
mkdir -p out
MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
```

This writes one `<id>.out` file per `<id>.in` case, in the format
`{"trophies": [{"id": n, "q": [q05, q25, q50, q75, q95]}, ...]}`.
The program is deterministic: two runs on the same case produce
byte-identical output. Python 3.13 standard library only, no
network.

## Layout

- `main.py` — folder handling and case file I/O
- `model.py` — the forecasting model
- `LICENSE` — MIT license
- `.makefun/owner.json` — entrant wallet claim file
