import argparse
import json
from copy import deepcopy
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parent
PROFILE_PATH = ROOT / "athlete_profile.json"
OUTPUT_DIR = ROOT / "outputs"

DAY_ORDER = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]

DAY_ABBREVIATIONS = {
    "Monday": "Mon",
    "Tuesday": "Tue",
    "Wednesday": "Wed",
    "Thursday": "Thu",
    "Friday": "Fri",
    "Saturday": "Sat",
    "Sunday": "Sun",
}


@dataclass(frozen=True)
class WeekTargets:
    week_number: int
    phase: str
    long_run_km: int
    weekly_run_km: int
    marathon_pace_km: int
    threshold_repeats: int
    threshold_minutes: int
    long_ride_minutes: int
    endurance_ride_minutes: int
    notes: list[str]


def load_profile() -> dict[str, Any]:
    return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))


def next_monday(from_date: date) -> date:
    offset = (7 - from_date.weekday()) % 7
    return from_date if offset == 0 else from_date + timedelta(days=offset)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a 15-week marathon + triathlon training block."
    )
    parser.add_argument(
        "--start-date",
        help="Plan start date in YYYY-MM-DD format. Defaults to the next Monday.",
    )
    parser.add_argument(
        "--week",
        type=int,
        help="Generate only a single plan week by week number, for example --week 1. Use --week 16 for the standalone race week.",
    )
    return parser.parse_args()


def resolve_start_date(raw_start_date: str | None) -> date:
    if raw_start_date:
        return datetime.strptime(raw_start_date, "%Y-%m-%d").date()
    return next_monday(date.today())


def phase_for_week(week_number: int, total_weeks: int) -> str:
    if week_number >= total_weeks - 1:
        return "taper"
    if week_number % 4 == 0:
        return "recovery"
    return "build"


def build_week_targets(profile: dict[str, Any]) -> list[WeekTargets]:
    total_weeks = profile["goals"]["weeks_to_goal"]
    current_weekly_km = profile["running"]["weekly_km"]

    weekly_km = current_weekly_km
    build_targets: list[WeekTargets] = []
    long_run_sequence = [16, 18, 20, 18, 22, 24, 26, 22, 24, 26, 28, 24, 32, 24, 16]

    for week_number in range(1, total_weeks + 1):
        phase = phase_for_week(week_number, total_weeks)
        long_run = long_run_sequence[week_number - 1]

        if week_number == 1:
            weekly_km = current_weekly_km
        elif phase == "build":
            weekly_km = min(weekly_km + 4, 62)
        elif phase == "recovery":
            weekly_km = max(weekly_km - 8, 34)
        else:
            taper_targets = {
                total_weeks - 1: max(weekly_km - 10, 34),
                total_weeks: max(weekly_km - 18, 26),
            }
            weekly_km = taper_targets[week_number]

        marathon_pace_km = 0
        if week_number % 2 == 0 and phase != "recovery" and long_run >= 18:
            marathon_pace_km = min(max((long_run - 12) // 2, 4), 10)

        if phase == "build":
            threshold_repeats = 3 if week_number < 6 else 4
            threshold_minutes = 8 if week_number < 4 else 10
            long_ride_minutes = min(120 + (week_number * 5), 180)
            endurance_ride_minutes = min(70 + week_number * 3, 95)
            notes = ["Progressive load week focused on aerobic volume."]
        elif phase == "recovery":
            threshold_repeats = 3
            threshold_minutes = 6
            long_ride_minutes = 105
            endurance_ride_minutes = 60
            notes = ["Recovery week to consolidate the previous block."]
        else:
            threshold_repeats = 2
            threshold_minutes = 6
            long_ride_minutes = 75 if week_number == total_weeks - 1 else 45
            endurance_ride_minutes = 50 if week_number == total_weeks - 1 else 0
            notes = ["Taper week with reduced volume and retained sharpness."]

        build_targets.append(
            WeekTargets(
                week_number=week_number,
                phase=phase,
                long_run_km=long_run,
                weekly_run_km=weekly_km,
                marathon_pace_km=marathon_pace_km,
                threshold_repeats=threshold_repeats,
                threshold_minutes=threshold_minutes,
                long_ride_minutes=long_ride_minutes,
                endurance_ride_minutes=endurance_ride_minutes,
                notes=notes,
            )
        )

    return build_targets


def build_week_16_targets() -> WeekTargets:
    return WeekTargets(
        week_number=16,
        phase="race",
        long_run_km=42,
        weekly_run_km=28,
        marathon_pace_km=0,
        threshold_repeats=0,
        threshold_minutes=0,
        long_ride_minutes=0,
        endurance_ride_minutes=0,
        notes=["Standalone race week ending with the goal marathon."],
    )


def hr_zone_range(
    profile: dict[str, Any], zone_name: str, zone_group: str = "heart_rate_zones"
) -> tuple[int | None, int | None]:
    raw = profile["running"][zone_group][zone_name.lower()].replace(" ", "")
    if raw.startswith("<"):
        return None, int(raw[1:])
    if raw.startswith(">"):
        return int(raw[1:]), None
    low, high = raw.split("-")
    return int(low), int(high)


def power_zone_range(profile: dict[str, Any], zone_name: str) -> tuple[float, float]:
    raw = profile["cycling"]["power_zones"][zone_name.lower()].replace(" ", "")
    low, high = raw.split("-")
    return float(low), float(high)


def format_duration(seconds: int) -> str:
    minutes = round(seconds / 60)
    return f"{minutes}m"


def format_km_from_meters(distance_m: int) -> str:
    return f"{distance_m / 1000:.2f} km"


def lthr_percent_range(hr_low: int | None, hr_high: int | None, threshold_hr: int) -> str:
    if hr_low is None or hr_high is None or threshold_hr <= 0:
        return "LTHR"
    low_pct = round((hr_low / threshold_hr) * 100)
    high_pct = round((hr_high / threshold_hr) * 100)
    return f"{low_pct}-{high_pct}% LTHR"


def ftp_percent_range(power_low: float, power_high: float) -> str:
    low_pct = round(power_low * 100)
    high_pct = round(power_high * 100)
    if low_pct == high_pct:
        return f"{low_pct}% FTP"
    return f"{low_pct}-{high_pct}% FTP"


def hr_zone_label(profile: dict[str, Any], target: dict[str, Any], zone_group: str = "heart_rate_zones") -> str:
    low = target.get("low")
    high = target.get("high")
    for zone_name, raw in profile["running"][zone_group].items():
        cleaned = raw.replace(" ", "")
        if cleaned.startswith("<"):
            if low is None and high == int(cleaned[1:]):
                return zone_name.upper()
        elif cleaned.startswith(">"):
            if low == int(cleaned[1:]) and high is None:
                return zone_name.upper()
        else:
            zone_low, zone_high = cleaned.split("-")
            if low == int(zone_low) and high == int(zone_high):
                return zone_name.upper()
    return "HR"


def power_zone_label(target: dict[str, Any]) -> str:
    return str(target.get("zone", "power")).upper()


def make_workout(
    day: str,
    sport: str,
    title: str,
    description: str,
    export_formats: list[str],
    segments: list[dict[str, Any]],
    tags: list[str] | None = None,
    notes: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "day": day,
        "sport": sport,
        "title": title,
        "description": description,
        "tags": tags or [],
        "notes": notes or [],
        "export_formats": export_formats,
        "segments": segments,
    }


def fun_workout_name(week_number: int, label: str, sport: str) -> str:
    title_map = {
        "swim": {
            "Technique Swim": [
                "Splash and Dash",
                "Lane Whisperer",
                "Aqua Acrobatics",
                "Water Wizardry",
                "Freestyle Folklore",
                "The Bubble Factory",
                "Chlorine and Charm",
                "Stroke School",
            ],
            "Steady Swim": [
                "Pool Party Cruise",
                "Liquid Patience",
                "Calm Waters Club",
                "Blue Line Grooves",
                "Steady Splash Society",
                "The Long Glide",
                "Quiet Water Hustle",
                "No Wake Zone",
            ],
            "Optional Swim": [
                "Bonus Splash",
                "If You Feel Like It Float",
                "Victory Lap Lite",
                "Wet Noodle Reset",
                "Optional Ocean Energy",
                "Poolside Bonus Round",
                "Easy Breezy Backstroke-ish",
                "A Little Dip",
            ],
        },
        "run": {
            "Threshold Run": [
                "Run, Bitch",
                "Your Mama Didnt Raise a Quitter",
                "Quit Crying, Keep Moving",
                "Nobody Cares, Hit Pace",
                "Suffer With Dignity",
                "This Is Why We Train",
                "Stop Negotiating",
                "Cry Later, Run Now",
            ],
            "Aerobic Run": [
                "Too Easy to Complain",
                "Boring, Do It Anyway",
                "Jog, You Drama Queen",
                "Just Shut Up and Shuffle",
                "Nobody Asked, Keep Running",
                "This Is the Easy One",
                "Dont Make It a Whole Thing",
                "Move Your Feet",
            ],
            "Recovery Run": [
                "Shuffle Therapy",
                "Legs in Warranty",
                "Jog and Repair",
                "Recovery Rumble",
                "Gentle Repair Service",
                "Rust Removal Run",
                "Easy Button Miles",
                "Sore but Sovereign",
            ],
            "Brick Run": [
                "Transition Damage Control",
                "Congratulations, Its a Brick",
                "Bike Legs, Cry About It",
                "Fresh Out of Good Ideas",
                "Wobble Now, Thank Me Later",
                "Straight Off the Bike, Genius",
                "Brick Please",
                "You Chose Multisport",
            ],
            "Long Run": [
                "Lord of the Long Run",
                "Endurance Odyssey",
                "The Weekend Epic",
                "Mileage Monarchy",
                "The Sunday Saga",
                "Kingdom of Kilometers",
                "Long Haul Legend",
                "Epic of Endurance",
            ],
            "Marathon Pace Tune-Up": [
                "Race Pace Tease",
                "Pace Invader",
                "Dress Rehearsal Run",
                "Marathon Mood Setter",
                "Pace With Purpose",
                "Goal Pace Prelude",
                "Just a Taste of Race",
                "Marathon Meter Check",
            ],
            "Easy Run": [
                "Feather Feet",
                "Soft Shoe Shuffle",
                "Gentle Miles Society",
                "Keep It Chill",
                "Cloud Jogger",
                "The Nice and Easy",
                "Sunday Shoes Energy",
                "Low Drama Mileage",
            ],
            "Shakeout Run": [
                "Jiggle the Nerves Out",
                "Pre-Race Wiggle",
                "Shakeout Shenanigans",
                "Loose Legs Express",
                "The Calm Before the Storm",
                "Pre-Race Pep Rally",
                "Nervous Energy Disposal",
                "Final Flutter",
            ],
            "Marathon Race": [
                "The Big Dance",
                "Forty Two and Through",
                "Glory Day",
                "Main Character Marathon",
                "The Grand Tour",
                "Legend Mode",
                "All Roads Lead Here",
                "Victory in Motion",
            ],
        },
        "bike": {
            "Endurance Ride": [
                "Spin to Win",
                "Cadence Crusade",
                "Chain Gang Chill",
                "Pedal Powered Zen",
                "Rolling Meditation",
                "Crank It Kindly",
                "Endurance on Wheels",
                "The Steady Spinner",
            ],
            "Long Ride": [
                "Wheels of Destiny",
                "The Rolling Chronicle",
                "Saddle Saga",
                "The Great Spinabout",
                "Tour de Vinit",
                "Miles of Smiles on Wheels",
                "The Epic Excursion",
                "Saddle Up Supreme",
            ],
            "Easy Spin": [
                "Leg Loosener Deluxe",
                "Tiny Chainring Energy",
                "Spin and Grin",
                "Easy Gear Glory",
                "Feather Pedal Parade",
                "Low Watt Luxury",
                "Kind Legs Club",
                "Chainring Chillout",
            ],
        },
    }
    options = title_map.get(sport, {}).get(label, [label])
    funny = options[(week_number - 1) % len(options)]
    return funny


def workout_title(week_number: int, day: str, label: str, sport: str) -> str:
    week_label = f"W{week_number:02d}"
    day_label = DAY_ABBREVIATIONS.get(day, day[:3])
    funny = slugify(fun_workout_name(week_number, label, sport))
    return f"{week_label}_{day_label}_{funny}"


def build_run_threshold(profile: dict[str, Any], targets: WeekTargets) -> dict[str, Any]:
    z2_low, z2_high = hr_zone_range(profile, "z2", "heart_rate_zones")
    z4_low, z4_high = hr_zone_range(profile, "z4", "heart_rate_zones")
    pace_range = profile["running"]["threshold_pace_min_per_km"]

    workout_variant = targets.week_number % 4
    segments = [
        {
            "type": "warmup",
            "duration_sec": 15 * 60,
            "target": {"metric": "heart_rate", "low": z2_low, "high": z2_high},
            "description": "Easy jog warm-up in Z2",
        }
    ]

    if workout_variant == 1:
        for repeat_index in range(targets.threshold_repeats):
            segments.append(
                {
                    "type": "work",
                    "duration_sec": targets.threshold_minutes * 60,
                    "target": {"metric": "heart_rate", "low": z4_low, "high": z4_high},
                    "description": (
                        f"Threshold repeat {repeat_index + 1} at "
                        f"{pace_range['from']}-{pace_range['to']} /km"
                    ),
                }
            )
            if repeat_index < targets.threshold_repeats - 1:
                segments.append(
                    {
                        "type": "recovery",
                        "duration_sec": 3 * 60,
                        "target": {"metric": "heart_rate", "low": z2_low, "high": z2_high},
                        "description": "Easy jog recovery",
                    }
                )
        workout_description = (
            f"{targets.threshold_repeats} x {targets.threshold_minutes} min at threshold. "
            "Primary quality session for the week."
        )
    elif workout_variant == 2:
        for repeat_index in range(4):
            segments.append(
                {
                    "type": "work",
                    "duration_sec": 6 * 60,
                    "target": {"metric": "heart_rate", "low": z4_low, "high": z4_high},
                    "description": f"Cruise interval {repeat_index + 1} at {pace_range['from']}-{pace_range['to']} /km",
                }
            )
            if repeat_index < 3:
                segments.append(
                    {
                        "type": "recovery",
                        "duration_sec": 2 * 60,
                        "target": {"metric": "heart_rate", "low": z2_low, "high": z2_high},
                        "description": "Easy jog float recovery",
                    }
                )
        workout_description = "4 x 6 min cruise intervals at threshold with short float recoveries."
    elif workout_variant == 3:
        segments.append(
            {
                "type": "work",
                "duration_sec": 20 * 60,
                "target": {"metric": "heart_rate", "low": z4_low, "high": z4_high},
                "description": f"20 min continuous tempo at {pace_range['from']}-{pace_range['to']} /km",
            }
        )
        workout_description = "Continuous threshold tempo to build sustained marathon strength."
    else:
        for repeat_index in range(2):
            segments.append(
                {
                    "type": "work",
                    "duration_sec": 15 * 60,
                    "target": {"metric": "heart_rate", "low": z4_low, "high": z4_high},
                    "description": f"Long threshold block {repeat_index + 1} at {pace_range['from']}-{pace_range['to']} /km",
                }
            )
            if repeat_index == 0:
                segments.append(
                    {
                        "type": "recovery",
                        "duration_sec": 4 * 60,
                        "target": {"metric": "heart_rate", "low": z2_low, "high": z2_high},
                        "description": "Easy jog recovery",
                    }
                )
        workout_description = "2 x 15 min threshold blocks to build sustained aerobic power."

    segments.append(
        {
            "type": "cooldown",
            "duration_sec": 10 * 60,
            "target": {"metric": "heart_rate", "low": z2_low, "high": z2_high},
            "description": "Easy cool-down jog",
        }
    )

    return make_workout(
        day="Tuesday",
        sport="run",
        title=workout_title(targets.week_number, "Tuesday", "Threshold Run", "run"),
        description=workout_description,
        export_formats=["fit"],
        segments=segments,
        tags=["quality", "threshold", targets.phase],
    )


def build_easy_run(profile: dict[str, Any], day: str, title: str, km: int) -> dict[str, Any]:
    z2_low, z2_high = hr_zone_range(profile, "z2", "heart_rate_zones")
    z3_low, z3_high = hr_zone_range(profile, "z3", "heart_rate_zones")
    duration_minutes = round(km * 6.4)
    week_number = int(title.split()[1])
    is_thursday = day == "Thursday"
    variant = week_number % 4 if is_thursday else 0

    if is_thursday and variant == 1:
        segments = [
            {
                "type": "steady",
                "duration_sec": duration_minutes * 60,
                "target": {"metric": "heart_rate", "low": z2_low, "high": z2_high},
                "description": f"Steady aerobic running {km}km",
            }
        ]
        description = f"{km} km relaxed aerobic running in Z2."
    elif is_thursday and variant == 2:
        easy_km = max(km - 3, 8)
        steady_km = km - easy_km
        segments = [
            {
                "type": "steady",
                "duration_sec": round(easy_km * 6.4) * 60,
                "target": {"metric": "heart_rate", "low": z2_low, "high": z2_high},
                "description": f"Easy aerobic running {easy_km}km",
            },
            {
                "type": "steady",
                "duration_sec": round(steady_km * 6.0) * 60,
                "target": {"metric": "heart_rate", "low": z3_low, "high": z3_high},
                "description": f"Steady finish {steady_km}km",
            },
        ]
        description = f"{km} km steady-state aerobic run with a stronger finish."
    elif is_thursday and variant == 3:
        first_km = max(km - 4, 8)
        finish_km = km - first_km
        segments = [
            {
                "type": "steady",
                "duration_sec": round(first_km * 6.4) * 60,
                "target": {"metric": "heart_rate", "low": z2_low, "high": z2_high},
                "description": f"Easy aerobic running {first_km}km",
            },
            {
                "type": "steady",
                "duration_sec": round(finish_km * 5.8) * 60,
                "target": {"metric": "heart_rate", "low": z3_low, "high": z3_high},
                "description": f"Progression finish {finish_km}km",
            },
        ]
        description = f"{km} km progression run finishing controlled and strong."
    elif is_thursday and variant == 0 and km >= 10:
        first_km = max(km - 3, 7)
        mp_km = km - first_km
        segments = [
            {
                "type": "steady",
                "duration_sec": round(first_km * 6.4) * 60,
                "target": {"metric": "heart_rate", "low": z2_low, "high": z2_high},
                "description": f"Easy aerobic running {first_km}km",
            },
            {
                "type": "steady",
                "duration_sec": round(mp_km * 5.75) * 60,
                "target": {"metric": "heart_rate", "low": z3_low, "high": z3_high},
                "description": f"Marathon pace finish {mp_km}km",
            },
        ]
        description = f"{km} km aerobic run with a short marathon-pace finish."
    else:
        segments = [
            {
                "type": "steady",
                "duration_sec": duration_minutes * 60,
                "target": {"metric": "heart_rate", "low": z2_low, "high": z2_high},
                "description": f"Steady aerobic running {km}km",
            }
        ]
        description = f"{km} km relaxed aerobic running in Z2."

    return make_workout(
        day=day,
        sport="run",
        title=workout_title(
            int(title.split()[1]),
            day,
            "Aerobic Run"
            if "Aerobic Run" in title
            else "Brick Run"
            if "Brick Run" in title
            else "Recovery Run"
            if "Recovery Run" in title
            else "Easy Run",
            "run",
        ),
        description=description,
        export_formats=["fit"],
        segments=segments,
        tags=["easy", "aerobic"],
        notes=[
            f"Planned distance is {km} km.",
            "FIT export currently uses estimated duration rather than a distance target for this run.",
        ],
    )


def build_long_run(profile: dict[str, Any], targets: WeekTargets, day: str) -> dict[str, Any]:
    z2_low, z2_high = hr_zone_range(profile, "z2", "heart_rate_zones")
    z3_low, z3_high = hr_zone_range(profile, "z3", "heart_rate_zones")
    easy_km = targets.long_run_km - targets.marathon_pace_km

    if targets.marathon_pace_km > 0:
        first_easy_km = max(easy_km - 2, 8)
        final_easy_km = targets.long_run_km - first_easy_km - targets.marathon_pace_km
        segments = [
            {
                "type": "steady",
                "duration_sec": round(first_easy_km * 6.5) * 60,
                "target": {"metric": "heart_rate", "low": z2_low, "high": z2_high},
                "description": f"{first_easy_km}km easy aerobic running",
            },
            {
                "type": "steady",
                "duration_sec": round(targets.marathon_pace_km * 5.75) * 60,
                "target": {"metric": "heart_rate", "low": z3_low, "high": z3_high},
                "description": f"{targets.marathon_pace_km}km at marathon pace",
            },
        ]
        if final_easy_km > 0:
            segments.append(
                {
                    "type": "steady",
                    "duration_sec": round(final_easy_km * 6.5) * 60,
                    "target": {"metric": "heart_rate", "low": z2_low, "high": z2_high},
                    "description": f"{final_easy_km}km easy cooldown running",
                }
            )
        description = (
            f"{targets.long_run_km} km long run with "
            f"{targets.marathon_pace_km} km at marathon pace."
        )
    else:
        segments = [
            {
                "type": "steady",
                "duration_sec": round(targets.long_run_km * 6.5) * 60,
                "target": {"metric": "heart_rate", "low": z2_low, "high": z2_high},
                "description": f"Long aerobic run {targets.long_run_km}km",
            }
        ]
        description = (
            f"{targets.long_run_km} km easy-long run. Keep it mostly aerobic and controlled."
        )

    return make_workout(
        day=day,
        sport="run",
        title=workout_title(targets.week_number, day, "Long Run", "run"),
        description=description,
        export_formats=["fit"],
        segments=segments,
        tags=["long_run", targets.phase],
        notes=[
            f"Planned distance is {targets.long_run_km} km.",
            "FIT export currently uses estimated duration rather than a distance target for this long run.",
        ],
    )


def build_swim(day: str, title: str, distance_m: int, description: str) -> dict[str, Any]:
    del distance_m
    week_number = int(title.split()[1])
    session_type = "steady" if "Steady Swim" in title or "Optional Swim" in title else "technique"

    def repeat_block(set_name: str, stroke: str, reps: int, rep_distance: int, rest_sec: int) -> list[dict[str, Any]]:
        block = []
        for repeat_number in range(4):
            block.append(
                {
                    "type": "active",
                    "distance_m": rep_distance,
                    "target": {"metric": "none"},
                    "description": f"{set_name} rep {repeat_number + 1}",
                    "stroke": stroke,
                }
            )
            block.append(
                {
                    "type": "recovery",
                    "duration_sec": rest_sec,
                    "target": {"metric": "none"},
                    "description": f"{set_name} rest",
                }
            )
        return block

    technique_templates = [
        [
            {"type": "warmup", "distance_m": 200, "target": {"metric": "none"}, "description": "Warmup", "stroke": "freestyle"},
            *repeat_block("Drill Set", "drill", 4, 50, 20),
            *repeat_block("Kick Set", "kick", 4, 50, 20),
            *repeat_block("Pull Set", "pull", 4, 50, 20),
            {"type": "cooldown", "distance_m": 100, "target": {"metric": "none"}, "description": "Cooldown", "stroke": "choice"},
        ],
        [
            {"type": "warmup", "distance_m": 300, "target": {"metric": "none"}, "description": "Warmup", "stroke": "freestyle"},
            *repeat_block("Drill Set", "drill", 4, 50, 15),
            *repeat_block("Pull Set", "pull", 4, 100, 20),
            {"type": "cooldown", "distance_m": 200, "target": {"metric": "none"}, "description": "Cooldown", "stroke": "choice"},
        ],
        [
            {"type": "warmup", "distance_m": 200, "target": {"metric": "none"}, "description": "Warmup", "stroke": "freestyle"},
            *repeat_block("Kick Set", "kick", 4, 50, 20),
            *repeat_block("Drill Set", "drill", 4, 75, 20),
            *repeat_block("Pull Set", "pull", 4, 75, 20),
            {"type": "cooldown", "distance_m": 100, "target": {"metric": "none"}, "description": "Cooldown", "stroke": "choice"},
        ],
    ]

    steady_templates = [
        [
            {"type": "warmup", "distance_m": 200, "target": {"metric": "none"}, "description": "Warmup", "stroke": "freestyle"},
            *repeat_block("Main Set", "freestyle", 4, 100, 20),
            *repeat_block("Pull Set", "pull", 4, 50, 15),
            {"type": "cooldown", "distance_m": 100, "target": {"metric": "none"}, "description": "Cooldown", "stroke": "choice"},
        ],
        [
            {"type": "warmup", "distance_m": 300, "target": {"metric": "none"}, "description": "Warmup", "stroke": "freestyle"},
            *repeat_block("Main Set", "freestyle", 4, 150, 20),
            *repeat_block("Kick Set", "kick", 4, 50, 20),
            {"type": "cooldown", "distance_m": 100, "target": {"metric": "none"}, "description": "Cooldown", "stroke": "choice"},
        ],
        [
            {"type": "warmup", "distance_m": 300, "target": {"metric": "none"}, "description": "Warmup", "stroke": "freestyle"},
            *repeat_block("Main Set", "freestyle", 4, 200, 20),
            {"type": "cooldown", "distance_m": 100, "target": {"metric": "none"}, "description": "Cooldown", "stroke": "choice"},
        ],
    ]

    if week_number % 4 == 0:
        segments = [
            {"type": "warmup", "distance_m": 200, "target": {"metric": "none"}, "description": "Warmup", "stroke": "freestyle"},
            *repeat_block("Drill Set", "drill", 4, 50, 20),
            {"type": "cooldown", "distance_m": 100, "target": {"metric": "none"}, "description": "Cooldown", "stroke": "choice"},
        ]
    else:
        templates = steady_templates if session_type == "steady" else technique_templates
        segments = templates[(week_number - 1) % len(templates)]

    return make_workout(
        day=day,
        sport="swim",
        title=workout_title(
            int(title.split()[1]),
            day,
            "Technique Swim" if "Technique Swim" in title else "Steady Swim" if "Steady Swim" in title else "Optional Swim",
            "swim",
        ),
        description=description,
        export_formats=["txt"],
        segments=segments,
        tags=["swim", "maintenance"],
    )


def build_bike(
    profile: dict[str, Any], day: str, title: str, minutes: int, description: str, tags: list[str]
) -> dict[str, Any]:
    z2_low, z2_high = power_zone_range(profile, "z2")
    z3_low, z3_high = power_zone_range(profile, "z3")
    week_number = int(title.split()[1])
    is_wednesday = day == "Wednesday"
    variant = week_number % 4 if is_wednesday else 1

    if is_wednesday and variant == 1:
        segments = [
            {
                "type": "freeride",
                "duration_sec": minutes * 60,
                "target": {"metric": "power_zone", "zone": "z2", "low": z2_low, "high": z2_high},
                "description": f"{description} Keep power in Z2.",
            }
        ]
        session_description = description
    elif is_wednesday and variant == 2:
        segments = [
            {
                "type": "freeride",
                "duration_sec": 15 * 60,
                "target": {"metric": "power_zone", "zone": "z2", "low": z2_low, "high": z2_high},
                "description": "Easy endurance spin",
            },
            {
                "type": "freeride",
                "duration_sec": 4 * 60,
                "target": {"metric": "power_zone", "zone": "z3", "low": z3_low, "high": z3_high},
                "description": "Cadence focus surge",
            },
            {
                "type": "freeride",
                "duration_sec": max((minutes - 19), 20) * 60,
                "target": {"metric": "power_zone", "zone": "z2", "low": z2_low, "high": z2_high},
                "description": "Return to aerobic endurance",
            },
        ]
        session_description = "Aerobic ride with a short cadence-focus block."
    elif is_wednesday and variant == 3:
        segments = [
            {
                "type": "freeride",
                "duration_sec": 10 * 60,
                "target": {"metric": "power_zone", "zone": "z2", "low": z2_low, "high": z2_high},
                "description": "Easy warm-up spin",
            },
            {
                "type": "freeride",
                "duration_sec": 3 * 8 * 60,
                "target": {"metric": "power_zone", "zone": "z3", "low": z3_low, "high": z3_high},
                "description": "Tempo-lite aerobic intervals",
            },
            {
                "type": "freeride",
                "duration_sec": max((minutes - 34), 15) * 60,
                "target": {"metric": "power_zone", "zone": "z2", "low": z2_low, "high": z2_high},
                "description": "Cool aerobic spin",
            },
        ]
        session_description = "Aerobic ride with tempo-lite intervals to keep variety."
    else:
        segments = [
            {
                "type": "freeride",
                "duration_sec": 10 * 60,
                "target": {"metric": "power_zone", "zone": "z2", "low": z2_low, "high": z2_high},
                "description": "Easy endurance spin",
            },
            {
                "type": "freeride",
                "duration_sec": 5 * 60,
                "target": {"metric": "power_zone", "zone": "z3", "low": z3_low, "high": z3_high},
                "description": "Short controlled tempo",
            },
            {
                "type": "freeride",
                "duration_sec": max((minutes - 15), 15) * 60,
                "target": {"metric": "power_zone", "zone": "z2", "low": z2_low, "high": z2_high},
                "description": "Aerobic finish spin",
            },
        ]
        session_description = "Aerobic ride with a short controlled tempo touch."

    return make_workout(
        day=day,
        sport="bike",
        title=workout_title(
            int(title.split()[1]),
            day,
            "Easy Spin" if "Easy Spin" in title else "Long Ride" if "Long Ride" in title else "Endurance Ride",
            "bike",
        ),
        description=session_description,
        export_formats=["zwo", "fit"],
        segments=segments,
        tags=tags,
    )


def allocate_run_distances(targets: WeekTargets) -> tuple[int, int]:
    if targets.phase == "race":
        return 0, 6
    if targets.phase == "recovery":
        return 6, 12
    if targets.phase == "taper":
        return 5, 10
    return 6, 14


def has_brick_run(targets: WeekTargets) -> bool:
    return targets.phase == "build" and targets.week_number % 2 == 1


def should_swap_brick_for_swim(profile: dict[str, Any], targets: WeekTargets) -> bool:
    return (
        bool(profile["preferences"].get("swap_brick_run_for_swim_on_even_build_weeks", False))
        and targets.phase == "build"
        and targets.week_number % 2 == 0
    )


def build_week(profile: dict[str, Any], start_date: date, targets: WeekTargets) -> dict[str, Any]:
    preferences = profile["preferences"]
    recovery_km, aerobic_km = allocate_run_distances(targets)

    if targets.phase == "race":
        sessions = [
            build_easy_run(
                profile,
                "Tuesday",
                f"Week {targets.week_number} Marathon Pace Tune-Up",
                aerobic_km,
            ),
            build_bike(
                profile,
                "Wednesday",
                f"Week {targets.week_number} Easy Spin",
                30,
                "Very easy aerobic spin to stay loose.",
                ["bike", "recovery", targets.phase],
            ),
            build_easy_run(
                profile,
                "Thursday",
                f"Week {targets.week_number} Easy Run",
                5,
            ),
            build_swim("Friday", f"Week {targets.week_number} Optional Swim", 1000, "Optional easy swim or full rest."),
            make_workout(
                day="Saturday",
                sport="run",
                title=f"Week {targets.week_number} Shakeout Run",
                description="20-25 min very easy shakeout with a few relaxed strides.",
                export_formats=["fit"],
                segments=[
                    {
                        "type": "steady",
                        "duration_sec": 25 * 60,
                        "target": {"metric": "heart_rate", "low": 145, "high": 160},
                        "description": "Easy shakeout run",
                    }
                ],
                tags=["race_week", "shakeout"],
            ),
            make_workout(
                day="Sunday",
                sport="run",
                title=f"Week {targets.week_number} Marathon Race",
                description="Goal marathon race day.",
                export_formats=["fit"],
                segments=[
                    {
                        "type": "steady",
                        "duration_sec": round(42.2 * 5.9) * 60,
                        "target": {"metric": "heart_rate", "low": 160, "high": 172},
                        "description": "Marathon race",
                    }
                ],
                tags=["race", "goal_event"],
            ),
        ]
    else:
        sessions = [
            build_run_threshold(profile, targets),
            build_easy_run(
                profile,
                "Thursday",
                f"Week {targets.week_number} Aerobic Run",
                aerobic_km,
            ),
            build_swim("Friday", f"Week {targets.week_number} Steady Swim", 2000, "2000 m continuous aerobic swim with light cadence focus."),
            build_bike(
                profile,
                preferences["long_ride_days"][0],
                f"Week {targets.week_number} Long Ride",
                targets.long_ride_minutes,
                "Long aerobic ride. Stay comfortable, smooth, and controlled throughout.",
                ["bike", "long_ride", targets.phase],
            ),
            build_long_run(profile, targets, preferences["long_run_days"][0]),
        ]

        if has_brick_run(targets):
            sessions.insert(
                -1,
                build_easy_run(
                    profile,
                    "Saturday" if preferences["long_run_days"][0] == "Sunday" else "Sunday",
                    f"Week {targets.week_number} Brick Run",
                    recovery_km,
                ),
            )
        elif should_swap_brick_for_swim(profile, targets):
            sessions.insert(
                -1,
                build_swim(
                    "Saturday" if preferences["long_run_days"][0] == "Sunday" else "Sunday",
                    f"Week {targets.week_number} Optional Swim",
                    1200,
                    "Optional swim instead of the short brick run to reduce impact load.",
                ),
            )

    if targets.endurance_ride_minutes > 0:
        sessions.insert(
            2,
            build_bike(
                profile,
                "Wednesday",
                f"Week {targets.week_number} Endurance Ride",
                targets.endurance_ride_minutes,
                "Steady aerobic ride with smooth cadence and easy fueling practice.",
                ["bike", "endurance", targets.phase],
            ),
        )

    dated_sessions = []
    for session in sessions:
        session_copy = deepcopy(session)
        session_date = start_date + timedelta(days=DAY_ORDER.index(session_copy["day"]))
        session_copy["date"] = session_date.isoformat()
        session_copy["week_number"] = targets.week_number
        dated_sessions.append(session_copy)

    return {
        "week_number": targets.week_number,
        "phase": targets.phase,
        "start_date": start_date.isoformat(),
        "end_date": (start_date + timedelta(days=6)).isoformat(),
        "run_weekly_target_km": targets.weekly_run_km,
        "long_run_target_km": targets.long_run_km,
        "notes": targets.notes,
        "sessions": dated_sessions,
    }


def slugify(value: str) -> str:
    clean = []
    for char in value.lower():
        clean.append(char if char.isalnum() else "_")
    return "_".join(part for part in "".join(clean).split("_") if part)


def export_stem(workout: dict[str, Any]) -> str:
    return slugify(workout["title"])


def zwo_export_stem(workout: dict[str, Any]) -> str:
    week_label = f"W{int(workout['week_number']):02d}"
    title = workout["title"]
    prefix = f"{week_label}_"
    title_slug = slugify(title[len(prefix):] if title.startswith(prefix) else title)
    return f"{week_label}_Z_{title_slug}"


def zwo_workout_name(workout: dict[str, Any]) -> str:
    return zwo_export_stem(workout)


def zwo_workout_element(workout: dict[str, Any]) -> ET.Element:
    root = ET.Element("workout_file")
    ET.SubElement(root, "author").text = "Codex"
    ET.SubElement(root, "name").text = zwo_workout_name(workout)
    ET.SubElement(root, "description").text = workout["description"]
    ET.SubElement(root, "sportType").text = "bike"
    workout_element = ET.SubElement(root, "workout")

    for segment in workout["segments"]:
        if segment.get("duration_sec", 0) <= 0:
            continue
        target = segment.get("target", {})
        if target.get("metric") == "power_zone":
            ET.SubElement(
                workout_element,
                "SteadyState",
                Duration=str(segment["duration_sec"]),
                Power=str((target["low"] + target["high"]) / 2),
            )
        elif segment["type"] in {"warmup", "cooldown"}:
            ET.SubElement(
                workout_element,
                "Warmup" if segment["type"] == "warmup" else "Cooldown",
                Duration=str(segment["duration_sec"]),
                PowerLow="0.50",
                PowerHigh="0.60",
            )
        else:
            ET.SubElement(
                workout_element,
                "FreeRide",
                Duration=str(segment["duration_sec"]),
            )

    return root


def write_zwo(workout: dict[str, Any], export_dir: Path) -> Path:
    filename = f"{zwo_export_stem(workout)}.zwo"
    path = export_dir / filename
    tree = ET.ElementTree(zwo_workout_element(workout))
    ET.indent(tree, space="  ")
    tree.write(path, encoding="utf-8", xml_declaration=True)
    return path


def write_fit(workout: dict[str, Any], export_dir: Path) -> Path | None:
    try:
        from fit_tool.fit_file_builder import FitFileBuilder
        from fit_tool.profile.messages.file_id_message import FileIdMessage
        from fit_tool.profile.messages.workout_message import WorkoutMessage
        from fit_tool.profile.messages.workout_step_message import WorkoutStepMessage
        from fit_tool.profile.profile_type import DisplayMeasure, FileType, Sport, SubSport, Intensity, SwimStroke, WorkoutCapabilities, WorkoutStepDuration, WorkoutStepTarget
    except ImportError:
        return None

    path = export_dir / f"{export_stem(workout)}.fit"
    builder = FitFileBuilder(auto_define=True, min_string_size=50)

    file_id = FileIdMessage()
    file_id.type = FileType.WORKOUT
    file_id.manufacturer = 1
    file_id.product = 1
    file_id.serial_number = 1
    file_id.time_created = int(datetime.now().timestamp() * 1000)
    builder.add(file_id)

    workout_message = WorkoutMessage()
    workout_message.workout_name = workout["title"]
    sport_map = {
        "run": Sport.RUNNING,
        "bike": Sport.CYCLING,
        "swim": Sport.SWIMMING,
    }
    workout_message.sport = sport_map.get(workout["sport"], Sport.RUNNING)
    if workout["sport"] == "swim":
        workout_message.sub_sport = SubSport.LAP_SWIMMING
        workout_message.pool_length = 25
        workout_message.pool_length_unit = DisplayMeasure.METRIC
        workout_message.capabilities = 0
    else:
        workout_message.capabilities = WorkoutCapabilities.INTERVAL
    workout_message.num_valid_steps = len(workout["segments"])
    builder.add(workout_message)

    for index, segment in enumerate(workout["segments"]):
        step = WorkoutStepMessage()
        step.message_index = index
        step.wkt_step_name = segment["description"][:15]
        if segment["type"] == "recovery":
            step.intensity = Intensity.REST
        elif segment["type"] == "warmup":
            step.intensity = Intensity.WARMUP
        elif segment["type"] == "cooldown":
            step.intensity = Intensity.COOLDOWN
        else:
            step.intensity = Intensity.ACTIVE
        if "distance_m" in segment:
            step.duration_type = WorkoutStepDuration.DISTANCE
            step.duration_distance = float(segment["distance_m"] / 10)
        else:
            step.duration_type = WorkoutStepDuration.TIME
            step.duration_value = int(segment["duration_sec"] * 1000)
        step.notes = segment["description"]

        target = segment.get("target", {})
        if target.get("metric") == "open":
            step.target_type = WorkoutStepTarget.OPEN
        elif target.get("metric") == "none":
            step.target_type = None
        elif target.get("metric") == "heart_rate":
            step.target_type = WorkoutStepTarget.HEART_RATE
            if target.get("low") is not None:
                step.custom_target_value_low = int(target["low"])
            if target.get("high") is not None:
                step.custom_target_value_high = int(target["high"])
        elif target.get("metric") == "power_zone":
            step.target_type = WorkoutStepTarget.POWER
            step.custom_target_value_low = int(target["low"] * 100)
            step.custom_target_value_high = int(target["high"] * 100)
        if workout["sport"] == "swim" and segment.get("stroke"):
            stroke_map = {
                "freestyle": SwimStroke.FREESTYLE,
                "drill": SwimStroke.DRILL,
                "kick": SwimStroke.IM if hasattr(SwimStroke, "IM") else SwimStroke.FREESTYLE,
                "pull": SwimStroke.FREESTYLE,
                "choice": SwimStroke.FREESTYLE,
            }
            step.target_type = WorkoutStepTarget.SWIM_STROKE
            step.target_stroke_type = stroke_map.get(segment["stroke"], SwimStroke.FREESTYLE)
        builder.add(step)

    fit_file = builder.build()
    path.write_bytes(fit_file.to_bytes())
    return path


def format_swim_workout_text(workout: dict[str, Any]) -> str:
    total_distance = sum(segment.get("distance_m", 0) for segment in workout["segments"])
    lines = [
        f"{workout['title']}",
        f"Date: {workout['date']}",
        "Sport: Swimming",
        "Pool length: 25m",
        f"Total distance: {format_km_from_meters(total_distance)}",
        "",
    ]

    lines.extend(
        [
            "Warmup",
            f"- Warmup {format_km_from_meters(200)}",
            "",
            "4x",
            f"- Drill {format_km_from_meters(50)}",
            "- 20s intensity=rest",
            "",
            "4x",
            f"- Kick {format_km_from_meters(50)}",
            "- 20s intensity=rest",
            "",
            "4x",
            f"- Pull {format_km_from_meters(50)}",
            "- 20s intensity=rest",
            "",
            "Cooldown",
            f"- Swim {format_km_from_meters(100)}",
        ]
    )

    return "\n".join(lines) + "\n"


def write_swim_text(workout: dict[str, Any], export_dir: Path) -> Path:
    filename = f"{export_stem(workout)}.txt"
    path = export_dir / filename
    path.write_text(format_swim_workout_text(workout), encoding="utf-8")
    return path


def week_export_dir(base_dir: Path, workout: dict[str, Any]) -> Path:
    path = base_dir / f"week {workout['week_number']}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def export_plan(plan: dict[str, Any], profile: dict[str, Any]) -> dict[str, list[str]]:
    def week_rest_day(week: dict[str, Any]) -> str:
        scheduled_days = {session["day"] for session in week["sessions"]}
        for day in DAY_ORDER:
            if day not in scheduled_days:
                return day
        return "none"

    def week_brick_day(week: dict[str, Any]) -> str:
        sports_by_day: dict[str, set[str]] = {}
        for session in week["sessions"]:
            sports_by_day.setdefault(session["day"], set()).add(session["sport"])
        for day in DAY_ORDER:
            sports = sports_by_day.get(day, set())
            if "bike" in sports and "run" in sports:
                return day
        return "none"

    json_dir = OUTPUT_DIR / "json"
    workout_dir = OUTPUT_DIR / "fit and zwo"
    zwo_dir = workout_dir
    fit_dir = workout_dir
    swim_dir = OUTPUT_DIR / "swim_text"
    json_dir.mkdir(parents=True, exist_ok=True)
    workout_dir.mkdir(parents=True, exist_ok=True)
    swim_dir.mkdir(parents=True, exist_ok=True)

    json_filename = "week_plan.json" if len(plan["weeks"]) == 1 else "full_plan.json"
    plan_path = json_dir / json_filename
    plan_path.write_text(json.dumps(plan, indent=2), encoding="utf-8")

    def session_target_summary(session: dict[str, Any]) -> str:
        parts = []
        for segment in session["segments"]:
            target = segment.get("target", {})
            if target.get("metric") == "heart_rate":
                low = target.get("low")
                high = target.get("high")
                parts.append(f"HR {low}-{high}" if low is not None and high is not None else "HR")
            elif target.get("metric") == "power_zone":
                zone = str(target.get("zone", "")).upper()
                low = target.get("low")
                high = target.get("high")
                parts.append(f"{zone} {int(low*100)}-{int(high*100)}% FTP")
            elif target.get("metric") == "none":
                if "distance_m" in segment:
                    parts.append(
                        format_km_from_meters(int(segment["distance_m"]))
                        if session["sport"] == "swim"
                        else f"{segment['distance_m']}m"
                    )
                elif "duration_sec" in segment:
                    parts.append(f"{segment['duration_sec']}s")
        seen = []
        for part in parts:
            if part not in seen:
                seen.append(part)
        return ", ".join(seen)

    def session_segment_summary(session: dict[str, Any]) -> list[str]:
        lines = []
        run_lthr = int(profile["running"]["threshold_hr_bpm"])
        for segment in session["segments"]:
            target = segment.get("target", {})
            prefix = f"- {segment['description']}"
            if "duration_sec" in segment:
                detail = format_duration(int(segment["duration_sec"]))
            elif "distance_m" in segment:
                detail = (
                    format_km_from_meters(int(segment["distance_m"]))
                    if session["sport"] == "swim"
                    else f"{int(segment['distance_m'])}m"
                )
            else:
                detail = ""

            if target.get("metric") == "heart_rate":
                zone_text = hr_zone_label(profile, target)
                lines.append(f"{prefix} {detail} {zone_text}".strip())
            elif target.get("metric") == "power_zone":
                zone_text = power_zone_label(target)
                lines.append(f"{prefix} {detail} {zone_text}".strip())
            elif detail:
                lines.append(f"{prefix} {detail}".strip())
            else:
                lines.append(prefix)
        return lines

    summary = {
        f"week{week['week_number']}": {
            "phase": week["phase"],
            "start_date": week["start_date"],
            "end_date": week["end_date"],
            "run_weekly_target_km": week["run_weekly_target_km"],
            "long_run_target_km": week["long_run_target_km"],
            "rest_day": week_rest_day(week),
            "brick_day": week_brick_day(week),
            "has_brick": week_brick_day(week) != "none",
            "notes": week["notes"],
            "sessions": [
                {
                    "day": session["day"],
                    "sport": session["sport"],
                    "title": session["title"],
                    "description": session["description"],
                    "target_summary": session_target_summary(session),
                    "generated_summary": session_segment_summary(session),
                }
                for session in week["sessions"]
            ],
        }
        for week in plan["weeks"]
    }
    summary_filename = "week_summary.json" if len(plan["weeks"]) == 1 else "plan_summary.json"
    summary_path = json_dir / summary_filename
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    exported = {"json": [str(plan_path), str(summary_path)], "zwo": [], "fit": [], "swim_text": []}

    for week in plan["weeks"]:
        for session in week["sessions"]:
            if "zwo" in session["export_formats"] and session["sport"] == "bike":
                exported["zwo"].append(str(write_zwo(session, week_export_dir(zwo_dir, session))))
            if "fit" in session["export_formats"]:
                fit_path = write_fit(session, week_export_dir(fit_dir, session))
                if fit_path is not None:
                    exported["fit"].append(str(fit_path))
            if "txt" in session["export_formats"] and session["sport"] == "swim":
                exported["swim_text"].append(str(write_swim_text(session, week_export_dir(swim_dir, session))))

    return exported


def build_plan(
    profile: dict[str, Any], start_date: date, selected_week: int | None = None
) -> dict[str, Any]:
    total_weeks = profile["goals"]["weeks_to_goal"]
    max_week = total_weeks + 1
    if selected_week is not None and not 1 <= selected_week <= max_week:
        raise ValueError(f"--week must be between 1 and {max_week}")

    weeks = []
    if selected_week == max_week:
        targets = build_week_16_targets()
        week_start = start_date + timedelta(days=(targets.week_number - 1) * 7)
        weeks.append(build_week(profile, week_start, targets))
    else:
        for targets in build_week_targets(profile):
            if selected_week is not None and targets.week_number != selected_week:
                continue
            week_start = start_date + timedelta(days=(targets.week_number - 1) * 7)
            weeks.append(build_week(profile, week_start, targets))

    return {
        "athlete": profile["athlete"],
        "goal": profile["goals"],
        "plan_start_date": start_date.isoformat(),
        "plan_end_date": weeks[-1]["end_date"],
        "weeks": weeks,
    }


def main() -> None:
    args = parse_args()
    profile = load_profile()
    start_date = resolve_start_date(args.start_date)
    plan = build_plan(profile, start_date, args.week)
    exported = export_plan(plan, profile)
    summary = {
        "weeks_generated": len(plan["weeks"]),
        "selected_week": args.week,
        "plan_start_date": plan["plan_start_date"],
        "plan_end_date": plan["plan_end_date"],
        "json_files": len(exported["json"]),
        "zwo_files": len(exported["zwo"]),
        "fit_files": len(exported["fit"]),
        "swim_text_files": len(exported["swim_text"]),
        "fit_dependency": "installed" if exported["fit"] else "missing_or_not_available",
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
