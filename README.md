# TriBaseMarathonPlan

Marathon plan generator with triathlon base.

This repo now has a starter structure for generating a dated 15-week training block from your athlete profile.

## Files

- `athlete_profile.json`: normalized athlete inputs for the generator
- `generate_week.py`: builds a 15-week plan and exports workout files
- `outputs/json/full_plan.json`: complete dated plan output
- `outputs/json/plan_summary.json`: compact summary keyed as `week1`, `week2`, and so on
- `outputs/fit and zwo/week N/`: run and bike structured workouts as `.fit`, plus bike `.zwo` files grouped by week
- `outputs/swim_text/week N/`: swim workouts exported as plain text for manual Garmin entry, grouped by week
- `overview.txt`: free-form athlete notes and background context

## What the scaffold does

The generator currently creates a full 15-week block that matches the profile in broad strokes:

- progressive build weeks with every fourth week as recovery
- taper in the final two weeks
- 4 run touches anchored by one threshold session and one long run
- swim on preferred days
- one endurance ride and one long ride
- bike workouts exported to `.zwo`
- run and bike workouts prepared for `.fit` export
- swim workouts exported as plain text

## How to run

If Python is available locally, run:

```powershell
py generate_week.py
```

To choose a specific start date:

```powershell
py generate_week.py --start-date 2026-03-23
```

To generate just week 1 for testing:

```powershell
py generate_week.py --week 1 --start-date 2026-03-23
```

To generate the standalone race week:

```powershell
py generate_week.py --week 16 --start-date 2026-03-23
```

If `py` does not work on your machine, use the Python executable installed in your environment.

## FIT export dependency

`zwo` export uses only the Python standard library.

`fit` export requires the `fit-tool` package to be installed in the Python environment used to run the script. If it is not installed, the script will still generate the full plan JSON and all `.zwo` files, but `.fit` files will be skipped.

## Good next steps

- add race-specific pace sessions and marathon-pace long-run segments
- add cycling FTP and swim pace targets to improve workout precision
- tune the FIT exporter against the exact device and Intervals.icu import behavior you use
