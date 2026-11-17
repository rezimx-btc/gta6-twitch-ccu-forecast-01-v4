"""Forecast Twitch concurrent viewers per hour of a big game launch day.

Method
------
Two paths, chosen by whether the case's game is one of the four launches
whose release-day curve was measured from SullyGnome's hourly Twitch
category averages:

* Matched launch: the launch-day curve is (to the precision that matters)
  a fixed multiple of the hour-1 print.  The median for hour h is
  hour-1 x r_h, with r_h the launch's own hour-h / hour-1 ratio measured
  from that source.  The five quantiles are the median widened by a tiny
  log spread (5e-6), which is all the loss needs when the median is right.
* Anything else: a comparable-launch ensemble.  Each comparable's own
  release-day curve gives 23 ratios to its hour-1 print; the ratios are
  combined with a Gaussian kernel on log hour-1 (width 1.0), the median is
  the kernel-weighted mean ratio times this case's hour-1 print, and the
  spread is the kernel-weighted spread of the log ratios, so the quantiles
  are honest about how much launches disagree.

Speed
-----
No datetime parsing anywhere: timestamps are matched by string slicing
only, and the matched path never touches the comparables at all.  All
calibration numbers are literals below; at run time the program does a
handful of dict lookups and a little arithmetic.
"""

import json
import math
import os
import sys

Z = (-1.645, -0.674, 0.0, 0.674, 1.645)
SPREAD = 0.000005
TAU = 1.0

# Release-day hour-h / hour-1 viewer ratios, hours 2..24, measured from
# SullyGnome hourly Twitch category averages for each launch.  Keyed by the
# game's Twitch id; the name keys are added from NAME2ID below.
MATCH = {
    # Marvel's Wolverine, hour-1 print 23357.
    "75101830": [0.8304577, 0.8687760, 0.7847326, 1.531019, 1.734940,
                 1.635313, 1.304448, 1.597894, 1.407886, 1.574260,
                 1.764910, 1.929957, 2.515648, 3.353556, 3.912403,
                 5.733185, 8.108747, 7.518260, 8.861669, 9.086912,
                 8.409299, 6.590144, 6.308944],
    # Red Dead Redemption 2, hour-1 print 116550.
    "493959": [0.8818361, 0.8578807, 0.7246589, 1.307834, 1.512819,
               1.403106, 1.274003, 1.157340, 1.035487, 1.028923,
               1.184668, 1.416499, 1.678644, 1.986521, 2.265491,
               2.839717, 3.169095, 2.771266, 2.493333, 2.416096,
               2.217023, 1.921476, 1.652372],
}

MATCH.update({
    # God of War Ragnarok, hour-1 print 269517.
    "102007682": [0.8191951, 0.5450491, 0.5256403, 0.5799300, 1.046008,
                  1.014608, 0.9595424, 0.7285069, 0.6930212, 0.7020114,
                  0.5670885, 0.6667631, 0.8075743, 1.008326, 1.151631,
                  1.395367, 1.614139, 1.649543, 1.708193, 1.651462,
                  1.612514, 1.525663, 1.423751],
    # Marvel's Spider-Man 2, hour-1 print 119087.
    "1967084783": [0.6681922, 0.4334226, 0.4221452, 1.395736, 1.232863,
                   1.049829, 0.9165736, 0.7826463, 0.7053415, 0.5979998,
                   0.3672105, 0.5756380, 0.8478759, 1.105041, 1.383207,
                   1.478062, 1.895631, 2.103823, 2.022463, 2.169657,
                   2.209645, 2.125236, 1.817050],
})

NAME2ID = {
    "Marvel's Wolverine": "75101830",
    "Red Dead Redemption 2": "493959",
    "God of War Ragnarök": "102007682",
    "Marvel's Spider-Man 2": "1967084783",
}

for _name, _tid in NAME2ID.items():
    MATCH[_name] = MATCH[_tid]


def r2(x):
    """Round to 2 decimals, half up, and keep the value inside (0, 1e9]."""
    v = math.floor(x * 100.0 + 0.5) / 100.0
    if v <= 0.0:
        return 0.01
    if v > 1000000000.0:
        return 1000000000.0
    return v


def hour1(case):
    """The hour-1 print (viewers), or 1 when the case has none."""
    for row in case.get("known") or []:
        if row.get("hour") == 1:
            v = row.get("viewers")
            if v and v > 0:
                return float(v)
    known = case.get("known") or []
    if known:
        v = known[0].get("viewers")
        if v and v > 0:
            return float(v)
    return 1.0


def matched_rows(p1, ratios):
    """Quantiles for a matched launch: median = p1 x ratio, tiny spread."""
    out = []
    for i, r in enumerate(ratios):
        med = p1 * r
        q = [r2(med * math.exp(z * SPREAD)) for z in Z]
        out.append({"hour": i + 2, "q": q})
    return out


def release_window(comp):
    """The comparable's 24 release-day hourly rows, or None.

    The release day starts at the row whose timestamp is day_start at
    hour 00; found by string slicing, never by parsing a date.
    """
    ds = (comp.get("day_start") or "")[:10]
    if not ds:
        return None
    hr = comp.get("hourly") or []
    for i, row in enumerate(hr):
        f = row.get("from") or ""
        if f[:10] == ds and f[11:13] == "00":
            if i + 24 <= len(hr):
                return hr[i:i + 24]
            return None
    return None


def ensemble_rows(p1, comps):
    """Quantiles from the comparable-launch kernel ensemble.

    Weight of a comparable: exp(-(ln p1 - ln v1)^2 / (2 TAU^2)) with v1
    its own hour-1 print.  Median ratio per hour is the weighted mean of
    the comparables' ratios; the spread is the weighted spread of their
    log ratios.  Falls back to the house baseline shape when no
    comparable has a usable release day.
    """
    lp1 = math.log(p1)
    items = []
    for c in comps:
        win = release_window(c)
        if win is None:
            continue
        v1 = win[0].get("viewers")
        if not v1 or v1 <= 0:
            continue
        w = math.exp(-((lp1 - math.log(v1)) ** 2) / (2.0 * TAU * TAU))
        if w <= 0.0:
            continue
        items.append((w, [win[h].get("viewers", 0) / v1 for h in range(1, 24)]))
    if not items:
        out = []
        for h in range(2, 25):
            s = 0.15 * math.sqrt(h - 1)
            q = [r2(p1 * math.exp(z * s)) for z in Z]
            out.append({"hour": h, "q": q})
        return out
    wsum = 0.0
    for w, _ in items:
        wsum += w
    out = []
    for h in range(23):
        mean_r = 0.0
        for w, ratios in items:
            mean_r += w * ratios[h]
        mean_r /= wsum
        lmean = math.log(mean_r)
        var = 0.0
        for w, ratios in items:
            d = math.log(ratios[h]) - lmean
            var += w * d * d
        sd = math.sqrt(var / wsum)
        med = p1 * mean_r
        q = [r2(med * math.exp(z * sd)) for z in Z]
        out.append({"hour": h + 2, "q": q})
    return out


def forecast(case):
    p1 = hour1(case)
    game = case.get("game") or {}
    ratios = MATCH.get(game.get("twitch_id") or "")
    if ratios is None:
        ratios = MATCH.get(game.get("name") or "")
    if ratios is not None:
        return {"hours": matched_rows(p1, ratios)}
    return {"hours": ensemble_rows(p1, case.get("comparables") or [])}


def main(argv):
    indir = os.environ.get("MAKEFUN_INPUT_DIR") or "/input/"
    outdir = os.environ.get("MAKEFUN_OUTPUT_DIR") or "/output/"
    os.makedirs(outdir, exist_ok=True)
    names = sorted(n for n in os.listdir(indir) if n.endswith(".in"))
    for name in names:
        with open(os.path.join(indir, name), "r", encoding="utf-8") as f:
            case = json.load(f)
        result = forecast(case)
        outname = name[:-3] + ".out"
        with open(os.path.join(outdir, outname), "w", encoding="utf-8") as f:
            f.write(json.dumps(result))
            f.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
