# PawPal+ (Module 2 Project)

You are building **PawPal+**, a Streamlit app that helps a pet owner plan care tasks for their pet.

## Scenario

A busy pet owner needs help staying consistent with pet care. They want an assistant that can:

- Track pet care tasks (walks, feeding, meds, enrichment, grooming, etc.)
- Consider constraints (time available, priority, owner preferences)
- Produce a daily plan and explain why it chose that plan

Your job is to design the system first (UML), then implement the logic in Python, then connect it to the Streamlit UI.

## What you will build

Your final app should:

- Let a user enter basic owner + pet info
- Let a user add/edit tasks (duration + priority at minimum)
- Generate a daily schedule/plan based on constraints and priorities
- Display the plan clearly (and ideally explain the reasoning)
- Include tests for the most important scheduling behaviors

## Getting started

### Setup

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Suggested workflow

1. Read the scenario carefully and identify requirements and edge cases.
2. Draft a UML diagram (classes, attributes, methods, relationships).
3. Convert UML into Python class stubs (no logic yet).
4. Implement scheduling logic in small increments.
5. Add tests to verify key behaviors.
6. Connect your logic to the Streamlit UI in `app.py`.
7. Refine UML so it matches what you actually built.

## 🖥️ Sample Output

Paste a sample of your app's CLI or Streamlit output here so a reader can see what a generated plan looks like:

Real output from `DailyPlan.explain()` for one owner with two pets, free 07:00-08:30 and
18:00-19:30:

```
Daily plan for Jordan — 2 pet(s), 7 task(s) considered, 180 min of free time.

Scheduled (5):
  07:00-07:10  Biscuit · Feeding (10 min, high) in Morning — high priority (score 290), earliest window with room
  07:10-07:40  Mochi · Morning walk (30 min, high) in Morning — high priority (score 270), earliest window with room
  07:45-07:55  Mochi · Meds (10 min, high) in Morning — owner asked for 07:45
  07:55-08:10  Biscuit · Litter box (15 min, medium) in Morning — medium priority (score 185), earliest window with room
  18:00-18:25  Mochi · Training (25 min, medium) in Evening — medium priority (score 175), earliest window with room

Skipped (2):
  Biscuit · Nail trim (20 min, low) — weekly task, not due on Tuesday
  Biscuit · Spa afternoon (120 min, low) — no window had 120 free minutes left

90 of 180 free minutes used; 90 left over.
```

## 🧪 Testing PawPal+

```bash
# Run the full test suite:
pytest

# Run with coverage:
pytest --cov
```

Sample test output:

```
============================= test session starts =============================
collected 13 items

tests\test_pawpal.py .............                                       [100%]

============================== 13 passed in 0.07s =============================
```

The suite covers task completion and attachment, the recurring-task rollover (daily,
weekly, `once`, double-completion, month-end arithmetic, and the queued instance staying
out of today's plan), and conflict detection (same pet, different pets, back-to-back tasks
that must *not* conflict, unpinned/completed tasks being ignored, and `build_plan` warning
while still scheduling).

## 📐 Smarter Scheduling

> The method mapping below reflects what is implemented in `pawpal_system.py` and drawn in
> `diagrams/uml_draft.mmd`.

| Feature | Method(s) | Notes |
|---------|-----------|-------|
| **Sorting by time** | **`Scheduler.sort_by_time()`** | Tasks in clock order by requested `start_time`, earliest first. Tasks with no requested time sink to the bottom; same-minute ties break by title. |
| **Sorting by priority** | **`CareTask.weight()`, `Scheduler.ranked_tasks()`** | `PRIORITY_RANK[priority] * 100 - duration_minutes`. Priority dominates; duration breaks ties in favour of shorter tasks, so more of the day's care fits. An unrecognised priority is treated as low. |
| **Filtering** | **`Scheduler.filter_tasks()`**, `Scheduler.tasks_for()` | `filter_tasks(pet_name=..., completed=...)` — both filters optional, both stack, `None` means "don't care". Pet names match case-insensitively. `tasks_for(pet)` is the identity-based counterpart. |
| **Conflict detection** | **`Scheduler.detect_conflicts()`, `Scheduler.conflict_warnings()`, `TaskConflict`** | Finds pairs of outstanding pinned tasks whose times overlap, same pet or not. Returns warnings; never raises. See below. |
| **Recurring tasks** | **`Scheduler.complete_task()`, `CareTask.create_next_occurrence()`, `CareTask.next_due_date()`** | Completing a `daily`/`weekly` task queues the next instance on the same pet, dated forward with `timedelta`. See below. |
| Due-date / weekday gating | `CareTask.is_due()`, `CareTask.due_date`, `CareTask.day_of_week` | Two gates: a task with a future `due_date` is not due yet; a `weekly` task is due only on its `day_of_week`. `Scheduler.build_plan(weekday, on_date)` filters on both. |
| Plan placement | `Scheduler.build_plan()`, `Scheduler._triage()`, `FreeTime` | Triage into pinned/flexible/skipped, then two passes: pinned tasks claim their requested time, flexible tasks take the earliest opening with room. `FreeTime` tracks the shrinking free intervals. |
| Multi-pet budgeting | `Owner.get_all_tasks()`, `Owner.total_available_minutes()` | The scheduler reads the whole workload through `Owner.get_all_tasks()` — never `pet.tasks` — so one plan covers every pet and the shared time budget is spent once, not once per pet. Overlapping `TimeSlot`s are trimmed so the same minute is never offered twice. |
| Completion status | `CareTask.completed`, `CareTask.mark_complete()`, `Scheduler.reset_day()` | Finished tasks are left out of the plan so the owner's time is not booked twice; `reset_day()` reopens them. |

### Conflict detection — `Scheduler.detect_conflicts()`

Two tasks conflict when the owner has asked for times that overlap. The test is interval
overlap, not string equality:

```python
start_a < end_b and start_b < end_a
```

so a task *inside* another task's duration is caught, not just two tasks sharing the same
`start_time`. Only outstanding **pinned** tasks are compared — a task with no requested
time has no time to clash over. Conflicts are found **across pets as well as within one**:
the owner is one person, and they cannot brush the cat and walk the dog in the same ten
minutes.

Each finding is a `TaskConflict` carrying both tasks and the overlap in minutes;
`TaskConflict.message()` renders the warning line, and `conflict_warnings()` returns them
as plain strings. **Nothing raises.** `build_plan()` puts the warnings on
`DailyPlan.warnings` and still produces a plan — the task that loses an overlap lands in
`DailyPlan.skipped` with its own reason.

```
⚠ Conflict for Biscuit and Mochi: 'Brushing' (07:45-08:00) overlaps 'Meds' (07:45-07:55) by 10 min.
⚠ Conflict for Mochi: 'Training' (18:15-18:40) overlaps 'Puzzle toy' (18:20-18:30) by 10 min.
```

### Recurring tasks — `Scheduler.complete_task()`

Marking a recurring task complete automatically queues its next occurrence:

```python
follow_up = scheduler.complete_task(walk, on_date=date.today())
# walk.completed  -> True
# follow_up.due_date -> tomorrow, follow_up.completed -> False
```

The interval comes from `REPEAT_AFTER` — `timedelta(days=1)` for `daily`,
`timedelta(days=7)` for `weekly` — so month ends and leap days are handled by the calendar
rather than by hand, and a weekly task keeps landing on the same weekday. A `once` task
returns `None`: there is no next time. Completing an already-complete task also returns
`None`, so finishing something twice cannot breed two copies.

The new instance is attached to the same pet immediately, but carries a future `due_date`,
so `build_plan(weekday, on_date)` skips it today ("next daily occurrence, due Mon 09 Nov")
instead of double-booking the owner. Dates are counted from the **completion day**, not
from "now", so finishing Monday's walk late on Tuesday still schedules the next one for
Tuesday rather than drifting a day further each time.

`mark_complete()` itself stays a plain state flip — the rollover lives on `Scheduler`
because attaching the new instance needs the pet, which the scheduler already has in hand.

### How the Scheduler talks to the Owner

```python
scheduler = Scheduler(owner)
plan = scheduler.build_plan("Tuesday")   # reads owner.get_all_tasks() internally
print(plan.explain())
```

`Scheduler` holds an `Owner`, not a `Pet`. Every read of the work to be done goes through
`Owner.get_all_tasks()`, which flattens every pet's list into one and stamps each task with its
pet. Adding a second pet therefore changes the plan without changing a line of the scheduler.

## 📸 Demo Walkthrough

Describe your app in numbered steps so a reader can follow along without watching a video:

1. <!-- Describe this step -->
2. <!-- Describe this step -->
3. <!-- Describe this step -->
4. <!-- Describe this step -->
5. <!-- Add more steps as needed -->

**Screenshot or video** *(optional)*: <!-- Insert a screenshot or link to a demo video here -->
