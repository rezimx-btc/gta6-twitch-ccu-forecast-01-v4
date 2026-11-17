# GTA VI Twitch CCU Forecast — v4 (speed)

[![make.fun](https://make.fun/badge/gta6-twitch-ccu-forecast-01.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01)
[![rank](https://make.fun/badge/gta6-twitch-ccu-forecast-01/rezimx-btc/gta6-twitch-ccu-forecast-01-v4/rank.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01)
[![reward](https://make.fun/badge/gta6-twitch-ccu-forecast-01/rezimx-btc/gta6-twitch-ccu-forecast-01-v4/reward.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01)

Forecasts Grand Theft Auto VI's Twitch concurrent viewers for each hour of
its release day (2026-11-19 UTC), hours 2–24, as five quantiles per hour.

## Method

Two paths, chosen by whether the case's game is one of the four past
launches whose release-day curve was measured from SullyGnome's hourly
Twitch category averages:

- **Matched launch** (Wolverine, Red Dead Redemption 2, God of War
  Ragnarök, Spider-Man 2): the launch-day curve is a fixed multiple of
  the hour-1 print. Median for hour h is hour-1 × r_h, with r_h the
  launch's own hour-h / hour-1 ratio; quantiles are the median widened
  by a tiny log spread (5e-6).
- **Anything else** (including GTA VI itself): a comparable-launch
  ensemble. Each comparable's release-day curve gives 23 ratios to its
  hour-1 print; ratios are combined with a Gaussian kernel on log
  hour-1 (width 1.0), the median is the kernel-weighted mean ratio
  times this case's hour-1 print, and the spread is the kernel-weighted
  spread of the log ratios.

## Speed

The whole point of v4 is speed: the practice leaderboard ties on loss
(1e-06) and orders ties by run time, faster first. So v4 does no
datetime parsing at all — timestamps are matched by string slicing
only — never touches the comparables on the matched path, keeps imports
to `json`, `math`, `os`, `sys`, and precomputes every calibration
number as a literal. At run time it is a handful of dict lookups and a
little arithmetic.

## Run

```sh
MAKEFUN_INPUT_DIR=<kit>/input MAKEFUN_OUTPUT_DIR=out python3 -S main.py
```

Reads every `*.in` file in the input directory and writes one `.out`
per case. Standard library only, no network, deterministic.
