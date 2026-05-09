# Local Tailored Planner Roadmap

## Vision

Turn this project into a single-user, local-first coaching system that can:
- build an athlete profile
- capture goals and constraints
- generate a tailored marathon-first training plan
- maintain triathlon fitness where needed
- adjust future weeks using feedback
- export workouts for Garmin, Zwift, Intervals.icu, and swim text

The system should use:
- deterministic training rules as the source of truth
- a local LLM as a planning assistant
- validation before any plan changes are accepted

## Product Direction

### V1 goals

- Single athlete, local machine only
- CLI-first workflow
- Marathon-first planning
- Triathlon maintenance support
- Local model via Ollama
- Rule engine remains authoritative
- Export support stays compatible with current FIT, ZWO, JSON, and swim-text outputs

### Non-goals for V1

- Multi-athlete coaching workflow
- Cloud sync
- Team accounts
- Fully autonomous model-driven planning
- Web app as the primary interface

## End-to-End Workflow

### 1. Athlete intake

Collect and persist:
- athlete identity
- age / DOB
- location
- training background
- recent training volume
- recent long run
- run threshold HR and pace
- cycling threshold HR and FTP/power zones
- swim background and pool length
- platform/device preferences

### 2. Goal setup

Collect and persist:
- primary goal
- race date
- race type
- secondary goals
- target outcome
- aggressiveness preference
- whether triathlon fitness is maintenance or co-primary

### 3. Constraints

Collect and persist:
- available training days
- preferred rest day
- max session duration per day
- pool access
- trainer/bike access
- injury history
- impact tolerance
- travel/work constraints

### 4. Plan generation

System should:
- build a phased block
- generate weekly sessions
- vary workouts without becoming random
- protect key marathon sessions
- preserve recovery structure
- export machine-readable and user-readable outputs

### 5. Weekly adaptation

Collect weekly feedback:
- completed sessions
- missed sessions
- fatigue
- soreness
- injury flags
- confidence/readiness
- schedule disruption

Then:
- ask local model for suggestions
- validate suggestions
- update future weeks safely

## Architecture

### Rule engine

Responsible for:
- progression logic
- long-run growth
- recovery weeks
- taper logic
- session distribution
- safety constraints
- workout template selection

### Local model assistant

Responsible for:
- personalization
- variation suggestions
- adapting to missed sessions
- explaining rationale
- selecting among allowed template options

Must not:
- directly own progression
- bypass validation
- write exports directly

### Validator

Responsible for rejecting:
- excessive weekly volume jumps
- excessive long-run jumps
- too many hard sessions close together
- broken race-week alignment
- malformed model output
- plans that violate protected marathon rules

### Export layer

Responsible for:
- FIT export
- ZWO export
- plan JSON
- plan summary JSON
- swim text output

## Planned Repo Structure

```text
profiles/
  athlete_profile.json
  goal_profile.json
  constraints.json
  weekly_feedback.json

plans/
  current_plan.json
  week_01.json
  week_02.json

engine/
  progression.py
  templates.py
  weekly_builder.py

assistant/
  ollama_client.py
  prompts.py
  response_parser.py

validators/
  training_rules.py
  schema_checks.py

exporters/
  fit_export.py
  zwo_export.py
  json_export.py
  swim_text_export.py
