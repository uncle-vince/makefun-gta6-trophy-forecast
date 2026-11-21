"""Forecasting core for the GTA VI trophy rarity entry.

Idea in one paragraph: a trophy earn rate is a proportion, so all of
the arithmetic happens on log-odds, where a move from 1% to 2% counts
about as much as a move from 33% to 50%.  Each trophy's recent
log-odds path is summarised by a robust drift estimate, that drift is
projected forward with a saturating horizon so a long forecast does
not simply extend a launch-week slope forever, and the five reported
quantiles fan out around the projected centre with a width that
follows how jumpy that trophy has actually been.
"""

import math
from datetime import datetime, timezone

# Quantile levels the contest asks for, and the matching cut points
# of a standard normal distribution.
TAU_LEVELS = (0.05, 0.25, 0.5, 0.75, 0.95)
NORMAL_CUTS = (-1.645, -0.674, 0.0, 0.674, 1.645)

# Rates are printed to two decimals, so 0 and 100 have no usable
# log-odds; keep every rate inside this open interval instead.
LOW_PCT = 0.01
HIGH_PCT = 99.99

# Spread of the plain stay-put forecast, in log-odds per root day.
# Trophy-specific widths are pulled part-way toward this anchor.
ANCHOR_SPREAD = 0.5

# Hours over which a drift is allowed to keep accumulating.  The
# effective projection length is h * S / (h + S), which is close to
# h for short horizons and levels off near S for long ones.
SATURATION_HOURS = 42.0

# No trophy's centre may travel further than this in log-odds,
# however steep its recent path looks.
MOVE_LIMIT = 1.45


def _bounded_rate(pct):
    """Clamp a percent into the range that has finite log-odds."""
    if pct < LOW_PCT:
        return LOW_PCT
    if pct > HIGH_PCT:
        return HIGH_PCT
    return pct


def to_log_odds(pct):
    """Convert a percent (0-100 scale) to log-odds."""
    p = _bounded_rate(pct) / 100.0
    return math.log(p / (1.0 - p))


def to_percent(log_odds):
    """Convert log-odds back to a percent."""
    return 100.0 / (1.0 + math.exp(-log_odds))


def round_to_grid(value):
    """Round to four decimal places, halves away from zero.

    Rates are never negative here, so adding one half and flooring
    is enough.  Whole numbers are returned as ints so the JSON text
    stays compact and stable between runs.
    """
    units = math.floor(value * 10000.0 + 0.5)
    result = units / 10000.0
    return int(result) if result == int(result) else result


def moment_in_hours(text, origin):
    """Hours between the origin epoch and an ISO-8601 timestamp."""
    stamp = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return (stamp.timestamp() - origin) / 3600.0


def _window_drift(hours, log_odds):
    """Drift per hour from the contrast of two window averages.

    The earliest two fifths of the observations are averaged into
    one point and the latest two fifths into another; the slope of
    the line through those two points is far less sensitive to a
    single odd read than an endpoint difference, and it needs no
    iterative fitting.  Short series fall back to no drift.
    """
    count = len(hours)
    if count < 3:
        if count == 2 and hours[1] > hours[0]:
            return (log_odds[1] - log_odds[0]) / (hours[1] - hours[0])
        return 0.0
    width = max(1, (2 * count) // 5)
    head_t = sum(hours[:width]) / width
    head_y = sum(log_odds[:width]) / width
    tail_t = sum(hours[count - width:]) / width
    tail_y = sum(log_odds[count - width:]) / width
    span = tail_t - head_t
    if span <= 1e-9:
        return 0.0
    return (tail_y - head_y) / span


def _typical_step(hours, log_odds):
    """Mean absolute log-odds step, rescaled to a per-root-day pace."""
    paces = []
    for idx in range(len(hours) - 1):
        gap_days = (hours[idx + 1] - hours[idx]) / 24.0
        if gap_days <= 0:
            continue
        jump = abs(log_odds[idx + 1] - log_odds[idx])
        paces.append(jump / math.sqrt(max(gap_days, 0.02)))
    if not paces:
        return ANCHOR_SPREAD
    return sum(paces) / len(paces)


# Drift and pace are estimated from at most this many hours of
# recent history: launch-week curves bend, and reads from the first
# night say little about the pace two days later.
RECENT_WINDOW_HOURS = 48.0


def quantiles_for_series(hours, rates, horizon_minutes):
    """Five quantile percents for one trophy's observed series."""
    series = [to_log_odds(r) for r in rates]
    centre = series[-1]

    # Keep the newest observation, then trim the estimation window
    # to the recent past; the centre itself never moves with the trim.
    keep = [idx for idx, hour in enumerate(hours)
            if hour >= hours[-1] - RECENT_WINDOW_HOURS]
    if len(keep) >= 3:
        est_hours = [hours[idx] for idx in keep]
        est_series = [series[idx] for idx in keep]
    else:
        est_hours, est_series = hours, series

    horizon_h = horizon_minutes / 60.0
    drift = _window_drift(est_hours, est_series)
    reach = horizon_h * SATURATION_HOURS / (horizon_h + SATURATION_HOURS)
    shift = drift * reach
    if shift > MOVE_LIMIT:
        shift = MOVE_LIMIT
    elif shift < -MOVE_LIMIT:
        shift = -MOVE_LIMIT
    centre += shift

    if len(est_series) >= 3:
        pace = _typical_step(est_hours, est_series)
        pace = min(1.05, max(0.14, pace))
        sigma = 0.7 * ANCHOR_SPREAD + 0.3 * pace
    else:
        sigma = ANCHOR_SPREAD
    half_width = sigma * math.sqrt(horizon_minutes / 1440.0)
    # A centre that has been moved by the drift is less certain than
    # one that stayed put, so the fan opens a little with the move.
    half_width *= 1.0 + 0.22 * min(1.0, abs(shift))

    return [round_to_grid(to_percent(centre + cut * half_width))
            for cut in NORMAL_CUTS]


def build_forecast(case):
    """Turn one parsed case object into its forecast object."""
    if tuple(case["levels"]) != TAU_LEVELS:
        raise ValueError("case levels do not match the contest levels")
    reads = case["history"]
    if not reads:
        raise ValueError("case carries no history reads")

    first = datetime.fromisoformat(reads[0]["at"].replace("Z", "+00:00"))
    origin = first.timestamp()
    read_hours = [moment_in_hours(read["at"], origin) for read in reads]

    out_rows = []
    for position, trophy in enumerate(case["trophies"]):
        seen_hours = []
        seen_rates = []
        for hour, read in zip(read_hours, reads):
            value = read["rates"][position]
            if value is not None:
                seen_hours.append(hour)
                seen_rates.append(value)
        if not seen_rates:
            seen_hours, seen_rates = [0.0], [0.0]
        out_rows.append({
            "id": trophy["id"],
            "q": quantiles_for_series(seen_hours, seen_rates,
                                      case["horizon_minutes"]),
        })
    return {"trophies": out_rows}
