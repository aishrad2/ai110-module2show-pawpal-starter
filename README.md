# PawPal+ (Module 2 Project)

You are building **PawPal+**, a Streamlit app that helps a pet owner plan care tasks for their pet.

## Scenario

A busy pet owner needs help staying consistent with pet care. They want an assistant that can:

- Track pet care tasks (walks, feeding, meds, enrichment, grooming, etc.)
- Consider constraints (time available, priority, owner preferences)
- Produce a daily plan and explain why it chose that plan

Your job is to design the system first (UML), then implement the logic in Python, then connect it to the Streamlit UI.

## ✨ Features

Each feature below is implemented in `pawpal_system.py` and named with the method that
does the work.

**Scheduling**
- **Owner-level daily planning** — one plan covers every pet, because the owner's free
  time is a single shared budget. `Scheduler.build_plan()` reads the whole workload
  through `Owner.get_all_tasks()` and never touches `pet.tasks` directly, so adding a
  second pet changes the plan without changing the scheduler.
- **Multiple availability windows** — a real day is 07:00–08:30 and 18:00–19:30, not one
  block. `TimeSlot` + `Owner.total_available_minutes()`; overlapping windows are trimmed
  so the same minute is never offered twice.
- **Pinned-time honouring** — a task the owner requested at a specific time claims that
  time first, before anything is scored. `CareTask.is_pinned()`.
- **Priority ranking** — `CareTask.weight()` scores `priority * 100 - duration`, so
  priority dominates and shorter tasks break ties, fitting more care into the day.
- **Explained output** — every scheduled task carries *why* it got its slot, and every
  skipped task carries *why* it was left out. `DailyPlan.explain()`.

**Sorting by time**
- **`Scheduler.sort_by_time()`** returns tasks in true chronological order. It parses
  `"HH:MM"` into minutes rather than sorting the strings, so a user typing `"7:00"` still
  lands before `"18:00"`. Untimed tasks sink to the bottom and order by title. It accepts
  an optional slice, so it composes with the filter.

**Filtering**
- **`Scheduler.filter_tasks(pet_name=..., completed=...)`** — both filters optional, both
  stacking, `None` meaning "don't care". Pet names match case- and whitespace-insensitively
  because they come from a text box. `Scheduler.tasks_for(pet)` is the identity-based
  counterpart.

**Conflict warnings**
- **`Scheduler.detect_conflicts()`** flags pairs of requested times that overlap — across
  different pets as well as within one, since the owner is one person. It tests true
  interval overlap, not matching start times, so a task nested inside another's duration
  is caught. Findings are `TaskConflict` objects; **nothing raises**, and the plan is
  still built.

**Daily and weekly recurrence**
- **`Scheduler.complete_task()`** queues the next occurrence of a recurring task on the
  same pet, dated with `timedelta` so month ends and leap days need no special casing and
  weekly tasks keep their weekday. The new instance carries a future `due_date`, so it is
  held out of *today's* plan rather than double-booking the owner.

**Verification**
- 32 tests covering all of the above plus the empty and degenerate cases — see
  [Testing PawPal+](#-testing-pawpal).

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
python -m pytest
```

### What the tests cover

32 tests in `tests/test_pawpal.py`, grouped by behaviour. Each group has its happy path
and its edge cases.

| Area | Tests | Covers |
|------|-------|--------|
| **Sorting** | 5 | Chronological order regardless of insertion order; unpadded `"7:00"` sorting before `"18:00"`; untimed tasks sinking to the bottom and then ordering by title; the sorter composing with a filtered slice; malformed times (`"abc"`, `"25:00"`) treated as unscheduled rather than crashing. |
| **Filtering** | 5 | By pet name (case- and whitespace-insensitive); by completion status, asserting the two halves partition the whole list; both filters stacking; no filters returning everything; an unknown pet name returning `[]`. |
| **Recurrence** | 6 | A completed daily task queueing tomorrow's instance on the same pet, unfinished, with its other fields intact; `timedelta` crossing a month end (2026-02-28 → 2026-03-01); a weekly task jumping 7 days and keeping its weekday; `once` queueing nothing; completing twice not breeding two copies; the queued instance staying out of *today's* plan. |
| **Conflict detection** | 7 | Overlapping times reported, not raised; conflicts found across different pets; two tasks at the exact same minute; three mutually overlapping tasks yielding all 3 pairs; back-to-back tasks (07:00–07:30 and 07:30–07:40) **not** flagged; unpinned and completed tasks ignored; `build_plan` warning while still producing a plan. |
| **Empty / degenerate** | 6 | A pet with no tasks; an owner with no pets; an owner with no free time; a task longer than every window; a zero-duration task; a weekly task on the wrong weekday. Each returns a plan with a stated reason rather than an exception. |
| **Multi-pet budgeting** | 1 | Two pets with 30 min of work each in a 45-min window book 30 minutes and skip one task — proving the owner's time is spent once, not once per pet. |
| **Base model** | 2 | `mark_complete()` flips status; `add_task()` grows the pet's list. |

### Sample run

```
============================= test session starts =============================
platform win32 -- Python 3.11.9, pytest-9.2.0, pluggy-1.7.0
rootdir: C:\Users\aishw\git\Codepath\ai110-module2show-pawpal-starter
plugins: anyio-4.16.0
collected 32 items

tests\test_pawpal.py ................................                    [100%]

============================= 32 passed in 0.09s ==============================
```

### Confidence level: ★★★★☆ (4 / 5)

**Why four and not five.** The suite passes, and it is not passing vacuously — I checked.
Mutating the overlap test in `detect_conflicts()` from `<` to `<=` makes
`test_back_to_back_tasks_do_not_conflict` fail with a bogus 0-minute conflict, so that
boundary is genuinely pinned by a test rather than merely asserted in a comment. The
`"7:00"` sorting test fails under naive string comparison, which is the regression it
exists to catch. Every branch of the recurrence logic and every skip reason in
`build_plan` is exercised.

**Why not five.** Three honest gaps:

- **Placement is tested by outcome, not exhaustively.** `FreeTime.book()` splitting a
  window into two leftovers is covered incidentally by the multi-pet test, but there is no
  test that deliberately books out the middle of a window and asserts both leftovers
  remain usable.
- **No test for overlapping `TimeSlot`s.** `_windows()` trims them so the same minute is
  never offered twice; nothing proves it.
- **Dates are only tested at day granularity.** There is no coverage of a task pinned near
  midnight, and the model has no concept of a task spanning midnight at all — it would be
  silently clipped by the window logic.

**What I would test next**, in order: window-splitting leftovers, overlapping availability
slots, and a property-style check that `scheduled_minutes()` never exceeds
`total_available_minutes()` for randomly generated task sets.

## 📐 Smarter Scheduling

> The method mapping below reflects what is implemented in `pawpal_system.py` and drawn in
> **`diagrams/uml_final.mmd`**. The Phase 1 sketch is kept at `diagrams/uml_draft.mmd` for
> comparison — the header comment in the final diagram lists exactly what changed and why.

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

### What the UI lets you do

| Area | Control | What it calls |
|------|---------|---------------|
| Owner & pet | Owner name, pet name, species | `Owner`, `Pet`, auto-registered on first use |
| Add a task | Title, duration, priority, frequency, requested start | `Scheduler.add_task()` |
| Browse tasks | **Show pet** dropdown, **Show status** radio | `Scheduler.filter_tasks(pet_name=..., completed=...)` |
| Task order | Table is always chronological | `Scheduler.sort_by_time()` on the filtered slice |
| Conflicts | Amber warning panel above the buttons | `Scheduler.detect_conflicts()` |
| Build the day | **Generate schedule** | `Scheduler.build_plan(weekday, on_date)` |
| Finish a task | **Mark done ·** buttons under the plan | `Scheduler.complete_task()` → queues the next occurrence |
| Start over | **Reset day (reopen tasks)** | `Scheduler.reset_day()` |

### Example workflow

1. **Name the owner and the first pet.** Type `Jordan` and `Mochi`, pick `dog`. The pet is
   registered the first time you add a task to it — no separate "create pet" step.
2. **Add a pinned task.** Title `Morning walk`, 30 minutes, `high`, frequency `daily`,
   requested start `07:00`. Click **Add task**.
3. **Add a second pet's task.** Change the pet name to `Biscuit`, species `cat`, add
   `Feeding`, 10 minutes, `high`, requested start `07:30`.
4. **Add a deliberate clash.** Switch back to `Mochi`, add `Meds`, 10 min, `high`, at
   `07:45`. Then with `Biscuit` selected add `Brushing`, 15 min, `medium`, also at `07:45`.
5. **Watch the conflict warning appear immediately** — before you generate anything. It
   names both tasks, the overlap in minutes, and which one will be dropped, so the fix is
   obvious and the task list you need to edit is right above it.
6. **Filter and sort.** Set **Show pet** to `Mochi` and **Show status** to `Still to do`.
   The table narrows to Mochi's outstanding tasks, still in clock order. Set it back to
   *All pets* / *All*.
7. **Generate the schedule.** Metrics show booked minutes, free time left, and how many
   tasks did not fit. The schedule table lists each task with the window it landed in and
   the scheduler's reason for that slot.
8. **Read the "Not scheduled" table.** `Brushing` appears there with
   *"requested 07:45 collides with an earlier task"* — the warning from step 5, now with
   its consequence made concrete.
9. **Mark `Morning walk` done.** A green banner confirms *"Morning walk repeats daily —
   next one queued for \<tomorrow\>"*. The task list gains tomorrow's instance, dated
   forward, and the rebuilt plan leaves it out of today rather than booking it twice.
10. **Open "Why does the plan look like this?"** for the full `DailyPlan.explain()` text:
    the budget, every scheduled task with its reason, every skipped task with its reason,
    and the minutes left over.

### Key Scheduler behaviors this demonstrates

- **Sorting** — the task table is chronological whatever order you added things in, and a
  requested time of `7:00` sorts before `18:00` rather than after it.
- **Filtering** — the two dropdowns map straight onto `filter_tasks`'s two optional
  arguments; selecting *All* passes `None`, meaning "don't care".
- **Conflict warnings** — surfaced before planning, non-blocking, naming both tasks and
  the consequence. An overlap never stops a plan from being produced.
- **Recurrence** — completing a daily or weekly task queues the next one automatically,
  dated so it does not pollute today.
- **Shared time budget** — Mochi's and Biscuit's tasks compete for the *same* minutes.
  Planning each pet separately would double-book Jordan; planning at the owner level
  cannot.

### Sample CLI output

The same logic without Streamlit, from `python main.py`. Abridged between sections; the
conflict check, the sorted view, the filtered views and the recurrence rollover all come
from one run.

```
====================================================================
Today's Schedule — Jordan (Sunday)
====================================================================
⚠ Conflict for Biscuit and Mochi: 'Brushing' (07:45-08:00) overlaps 'Meds' (07:45-07:55) by 10 min.
⚠ Conflict for Mochi: 'Training' (18:15-18:40) overlaps 'Puzzle toy' (18:20-18:30) by 10 min.

TIME         PET       TASK             MIN  PRIORITY WINDOW
--------------------------------------------------------------------
07:00-07:30  Mochi     Morning walk      30  high     Morning
07:30-07:40  Biscuit   Feeding           10  high     Morning
07:45-07:55  Mochi     Meds              10  high     Morning
07:55-08:10  Biscuit   Litter box        15  medium   Morning
08:10-08:30  Biscuit   Nail trim         20  low      Morning
18:15-18:40  Mochi     Training          25  medium   Evening

Not scheduled today:
  Biscuit · Evening play (15 min) — already done today
  Biscuit · Brushing (15 min) — requested 07:45 collides with an earlier task
  Mochi · Puzzle toy (10 min) — requested 18:20 collides with an earlier task

110 of 180 free minutes used; 70 left over.

====================================================================
Conflict check
====================================================================
Found 2 overlapping pair(s):
  ⚠ Conflict for Biscuit and Mochi: 'Brushing' (07:45-08:00) overlaps 'Meds' (07:45-07:55) by 10 min.  [different pets]
  ⚠ Conflict for Mochi: 'Training' (18:15-18:40) overlaps 'Puzzle toy' (18:20-18:30) by 10 min.  [same pet]

Nothing was raised and nothing crashed — the plan above was still
built. The task that lost each overlap is listed under 'Not scheduled'.

====================================================================
Every task, sorted by requested time
====================================================================
TIME     PET       TASK             MIN  PRIORITY STATUS
--------------------------------------------------------------------
07:00    Mochi     Morning walk      30  high     to do
07:30    Biscuit   Feeding           10  high     to do
07:45    Biscuit   Brushing          15  medium   to do
07:45    Mochi     Meds              10  high     to do
18:15    Mochi     Training          25  medium   to do
18:20    Mochi     Puzzle toy        10  low      to do
18:40    Biscuit   Evening play      15  medium   done
—        Biscuit   Litter box        15  medium   to do
—        Biscuit   Nail trim         20  low      to do

Tasks with no requested time sort to the bottom, then by title.

====================================================================
Filtered views
====================================================================
Mochi's tasks (4):
  07:00  Morning walk
  07:45  Meds
  18:15  Training
  18:20  Puzzle toy

Biscuit's tasks (5):
  07:30  Feeding
  07:45  Brushing
  18:40  Evening play
  —      Litter box
  —      Nail trim

Still to do (8): Training, Meds, Morning walk, Puzzle toy, Feeding, Litter box, Nail trim, Brushing
Already done (1): Evening play

Mochi, still to do (4): Training, Meds, Morning walk, Puzzle toy
(pet name matched case-insensitively — 'mochi' found 'Mochi')

====================================================================
Recurring tasks roll forward on completion
====================================================================
Completed: Mochi · Training (daily)
  -> next instance queued for Monday 09 Nov (today + 1 day), still at 18:15, completed=False
  -> tasks across all pets: 9 -> 10

Completed: Biscuit · Nail trim (weekly)
  -> next instance queued for Sunday 15 Nov (today + 7 days), still at no fixed time, completed=False
  -> tasks across all pets: 10 -> 11

Dates come from timedelta(days=1) for daily and timedelta(days=7) for
weekly, so month ends and leap days take care of themselves, and a
weekly task keeps landing on the same weekday.

Queued for later (2): Training, Nail trim
These are skipped when today's plan is rebuilt — see the reasons below.

  Mochi · Training — next daily occurrence, due Mon 09 Nov
  Biscuit · Nail trim — next weekly occurrence, due Sun 15 Nov
```

> Note: the demo uses the real current date, so the weekday in the header and the rollover
> dates will differ when you run it. The weekly nail trim is scheduled above only because
> that run happened on a Sunday.

**Screenshot or video** *(optional)*: <!-- Insert a screenshot or link to a demo video here -->
