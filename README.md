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
collected 2 items

tests\test_pawpal.py ..                                                  [100%]

============================== 2 passed in 0.01s ==============================
```

## 📐 Smarter Scheduling

> The method mapping below reflects what is implemented in `pawpal_system.py` and drawn in
> `diagrams/uml_draft.mmd`.

| Feature | Method(s) | Notes |
|---------|-----------|-------|
| Task sorting | `CareTask.weight()`, `Scheduler.ranked_tasks()` | `PRIORITY_RANK[priority] * 100 - duration_minutes`. Priority is the dominant term; duration breaks ties in favour of shorter tasks, so more of the day's care fits. An unrecognised priority is treated as low. |
| Filtering | `Scheduler.build_plan()` | A task that fits no remaining window is recorded in `DailyPlan.skipped` as a `PlanEntry` carrying a `reason`. Completed, not-due, and zero-duration tasks are filtered out the same way. |
| Conflict handling | `CareTask.is_pinned()`, `Scheduler.build_plan()` | Tasks with an owner-requested `start_time` are placed first, earliest request first. A requested time that collides with an earlier one or falls outside every `TimeSlot` is skipped with a reason. |
| Multi-pet budgeting | `Owner.get_all_tasks()`, `Scheduler.build_plan()`, `Owner.total_available_minutes()` | The scheduler reads the whole workload through `Owner.get_all_tasks()` — never `pet.tasks` — so one plan covers the owner's day across every pet and the shared time budget is spent once rather than once per pet. Overlapping `TimeSlot`s are trimmed so the same minute is never offered twice. |
| Recurring tasks | `CareTask.frequency`, `CareTask.day_of_week`, `CareTask.is_due()` | `daily` and `once` tasks are due whenever asked; a `weekly` task is due only on its `day_of_week`. `Scheduler.build_plan(weekday)` filters on this. |
| Completion status | `CareTask.completed`, `mark_complete()`, `Scheduler.reset_day()` | Finished tasks are left out of the plan so the owner's time is not booked twice; `reset_day()` reopens them for the next day. |

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
