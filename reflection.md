# PawPal+ Project Reflection

## 1. System Design

**a. Initial design**

Core actions (started with 1–3; added 4–5 since my first three were all input):

1. Input owner info and constraints
2. Add/edit tasks
3. Add a pet
4. Generate a daily plan
5. Explain the plan

Objects (started with Pet, Task, User):

| Class | Responsibility | Attributes | Key methods |
|-------|----------------|-----------|-------------|
| `Owner` | The person providing the care. Stores their identity and the time budget they have today, and acts as the root of the model: every pet, and through each pet every task, is reachable from an owner. | `name`, `start_time`, `available_minutes`, `pets` | `add_pet()` |
| `Pet` | A single animal in the owner's care. Stores the descriptive facts a plan may need — species and age both affect what care is appropriate — and owns the list of tasks belonging to it. | `name`, `species`, `age_years`, `tasks` | `add_task()` |
| `CareTask` | One unit of care to perform: a walk, a feeding, a dose of medication. Stores what it is, how long it takes, and how important it is, which is everything the scheduler needs to rank it. | `title`, `duration_minutes`, `priority`, `start_time` | `weight()` |
| `DailyPlan` | The result of scheduling: which tasks made it into the day, in what order, and which were left out. Owns both the scheduling algorithm and the explanation of its own output. | `pet`, `entries`, `skipped` | `build()`, `explain()`, `to_table()` |

`CareTask.weight()` is the ranking score that settles which task wins when two compete
for the same minutes: priority is the dominant term, and duration breaks ties in favour
of shorter tasks so that more of the day's care fits.

`DailyPlan.build()` does the scheduling: sort by `CareTask.weight()`, drop tasks that
don't fit in `available_minutes`, assign start times in order. `explain()` states why each
task was chosen or skipped.

Considered and left out to keep it simple: a separate `Scheduler`, a `ScheduledTask`
split from `CareTask`, `TimeWindow`, and `OwnerPreferences`. If any becomes necessary
during implementation, that's a design change for 1b.

**b. Design changes**

Yes — three changes, two of which were classes I'd explicitly deferred in 1a.

**1. `DailyPlan` is now per *owner*, not per pet.**

This was the real bug. The owner's free time is a single shared pool, but
`build(owner, pet)` produced one plan per pet, and each call independently spent the
*whole* budget. An owner with two pets got two plans that both claimed 08:00–08:30 —
the design silently double-booked them, and the "split the budget across pets" logic had
nowhere to live because no object owned the full day.

The signature itself was the evidence: `build()` already required the `Owner` in order to
read its constraints. A method that takes the owner for its limits and the pet for its
data is really an owner-level operation. `DailyPlan` therefore holds `owner` and is built
with `build(owner)`; a per-pet view is now a grouping over the entries rather than a
separate object.

**2. Added `PlanEntry` — the `ScheduledTask` I'd deferred.**

Once the plan spans every pet, each scheduled item has to record *which* pet it is for.
That could not go on `CareTask`: it would create a `Pet → CareTask → Pet` cycle, and
`CareTask` is a reusable template that should not carry scheduling results. `PlanEntry`
therefore pairs a pet with a task and holds the outputs — the assigned `start_time`, the
`slot_label` it was placed in, and a `reason`.

This also separated the two jobs `CareTask.start_time` had been doing at once. It is now
strictly an *input*: a time the owner requests for that task ("meds at 08:00"), with a
blank value meaning the scheduler may place it anywhere. The time a task is actually
assigned lives on the entry. Two benefits follow: building a plan never mutates the pet's
own data, so re-planning is repeatable, and a requested time becomes a real constraint
that `build()` must honour and check for collisions.

**3. `Owner.available_timeslots` replaced `start_time` + `available_minutes`.**

A single contiguous block cannot express the availability a busy owner actually has: free
07:00–08:00, occupied through the day, free again 18:00–19:30. Modelling it as one stretch
would permit a 19:00 walk to be scheduled at 09:30. Availability is therefore a list of
`TimeSlot` objects — the `TimeWindow` from my deferred list, adopted after all. This turns
`build()` from "subtract until the budget runs out" into packing tasks across several
windows, which is more work but is the problem the scenario actually poses.

I also added `Owner.remove_pet()` to pair with `add_pet()`, and
`Owner.total_available_minutes()` so the explanation can report the day's whole budget.

**Final class set**

| Class | Responsibility | Attributes | Key methods |
|-------|----------------|-----------|-------------|
| `TimeSlot` | One window during which the owner is free. Converts a start and end time into a capacity the scheduler can spend. | `label`, `start_time`, `end_time` | `minutes()` |
| `Owner` | The person providing the care. Stores their identity and their free windows for the day, and is the root of the model and the subject of the plan. | `name`, `available_timeslots`, `pets` | `add_pet()`, `remove_pet()`, `total_available_minutes()` |
| `Pet` | A single animal in the owner's care. Stores the descriptive facts a plan may need and owns the list of tasks belonging to it. | `name`, `species`, `age_years`, `tasks` | `add_task()` |
| `CareTask` | A reusable template for one unit of care. Stores what it is, how long it takes, how important it is, and optionally the time the owner requests for it. | `title`, `duration_minutes`, `priority`, `start_time` | `is_pinned()`, `weight()` |
| `PlanEntry` | One task placed in, or rejected from, the day. Keeps every scheduling result — the pet, the assigned time, the window used, and the reason — off the reusable `CareTask`. | `pet`, `task`, `start_time`, `slot_label`, `reason` | — |
| `DailyPlan` | The owner's whole day across all their pets. Owns the scheduling algorithm, the resulting entries, the skipped entries, and the explanation of both. | `owner`, `entries`, `skipped` | `build()`, `explain()`, `to_table()` |

---

## 2. Scheduling Logic and Tradeoffs

**a. Constraints and priorities**

The scheduler weighs five constraints:

1. **Availability** — the owner's free windows (`TimeSlot`), as a list rather than one
   block, because a real day is 07:00–08:30 and 18:00–19:30 with work in between.
2. **Duration** — a task has to actually fit in the minutes that remain.
3. **Requested time** — a `start_time` the owner typed is a hard constraint, not a hint.
4. **Priority** — `high`/`medium`/`low`, the tiebreaker when tasks compete for minutes.
5. **Due date and frequency** — whether the task belongs to *today* at all.

**How I ranked them.** The ordering fell out of asking which constraint, if violated,
produces output the owner cannot use.

Availability and duration come first because violating them makes the plan *fiction* —
a schedule that books 40 minutes into a 30-minute window is not a worse plan, it is not a
plan. These are hard limits and nothing overrides them.

Requested time comes next, above priority, and this was the real decision. The scheduler
knows a task is `high` priority; the owner knows the vet said *give the meds at 08:00*.
When those two conflict, the owner's specific knowledge beats the program's general rule.
So `build_plan` runs pinned tasks in a first pass and lets them claim their minutes before
any scoring happens — an explicit wish always wins over a computed score.

Priority only arbitrates what is left: flexible tasks competing for the leftover gaps.
`weight() = priority * 100 - duration` makes priority dominant with duration as a
tiebreaker that favours shorter tasks, so when two `medium` tasks compete, the one that
leaves more room for everything else wins.

Frequency/due-date sits slightly apart — it is a filter applied *before* ranking rather
than a thing being traded off, since a task that isn't due today shouldn't compete for
today's minutes at all.

**What I deliberately did not model:** owner preferences beyond requested times (no "I
prefer walks before breakfast"), travel or setup time between tasks, and tasks that span
midnight. The first two would be the next additions; the third is a real gap I'd have to
redesign `TimeSlot` to handle.

**b. Tradeoffs**

**The tradeoff: conflict detection *reports* overlaps instead of resolving them.**

`Scheduler.detect_conflicts()` finds every pair of outstanding pinned tasks whose
requested times overlap and returns a `TaskConflict` for each. What it does *not* do is
act on them. It does not raise, it does not refuse to build the plan, and it does not try
to shuffle either task to a time that would work. `build_plan()` hangs the warnings off
`DailyPlan.warnings`, then proceeds exactly as it would have anyway: the earlier-requested
task gets its slot, and the loser lands in `skipped` with "requested 07:45 collides with
an earlier task". The owner sees both the warning and a usable plan.

Two smaller decisions sit inside that one:

- **True overlap, not exact-time equality.** The obvious cheap version is to flag two
  tasks only when their `start_time` strings match. That would catch Mochi's meds and
  Biscuit's brushing (both 07:45) and completely miss Mochi's 18:20 puzzle toy sitting
  inside his own 18:15–18:40 training session — the more common and more annoying case.
  Comparing intervals (`start_a < end_b and start_b < end_a`) costs one extra line and
  catches both, so duration is part of the test.
- **Pinned tasks only, compared pairwise.** Tasks with no requested time are excluded:
  they have no time to clash over, and the scheduler is free to drop them in a gap. The
  comparison is a plain nested loop over the pinned tasks — O(n²).

**Why it is reasonable here.**

An overlap is not necessarily a mistake, and the program is in no position to tell. If the
owner has asked for meds at 07:45 and brushing at 07:45, the information the program holds
is strictly less than the information the owner holds: maybe one of them is quick enough
to overlap in practice, maybe the brushing time was a typo, maybe the meds genuinely must
be 07:45 and the brushing can slide. Auto-resolving means picking one of those stories and
silently acting on it, which produces a plan the owner did not ask for and cannot see the
reasoning behind. Raising is worse still — one typo in one field and the whole day fails
to plan, which is the opposite of what a planning assistant is for.

The O(n²) scan is the same kind of call. A realistic day is five to fifteen pinned tasks,
so the quadratic version runs in microseconds and the sorted-sweep alternative would buy
nothing measurable while costing real clarity. Picking the simple, obviously-correct
algorithm is the right trade at this size; it would be the wrong one at ten thousand
tasks, and that is the condition under which I would revisit it.

**What it costs.** The owner has to do the fixing. The scheduler will cheerfully warn
about the same conflict every single day until someone edits one of the two times, and a
plan with four warnings is only as useful as the owner's willingness to read them. A
future iteration could offer a suggested resolution — "move brushing to 08:00, the next
free 15 minutes" — but offering it is still different from doing it, and the *offering*
is the part that keeps the owner in charge.

---

## 3. AI Collaboration

**a. How you used AI**

I used AI for design brainstorming, implementation, debugging, and documentation — in all
four cases as a collaborator whose output I verified, not as a source of finished answers.

**What I used it for:**
- **Design brainstorming** — going back and forth on the class set, especially the
  `DailyPlan`-per-pet vs. per-owner question that turned out to be the project's real bug.
- **Implementation** — drafting the scheduling passes, the recurrence rollover, and the
  conflict scan from a spec I described rather than from a blank page.
- **Debugging and refreshers** — asking how a piece of code works, including code I'd
  written earlier and lost the thread on.
- **Documentation** — docstrings and README prose, which is where AI output needed the
  least correction and saved the most time.

**Prompt styles that worked best**, roughly in order of value:

1. **Asking it to critique its own output.** "Is this more Pythonic but harder to read?"
   produced a genuinely useful split between the two refactors worth keeping and the one
   worth rejecting — far better than "refactor this", which would have applied all three.
2. **Asking *which* and *why*, not "fix it".** "What is the most complicated algorithm
   here, and how would you simplify it?" got a ranked answer with reasoning I could argue
   with. "Clean this up" would have gotten edits I'd have had to reverse-engineer.
3. **Asking for the failure mode.** "What are the most important edge cases for a
   scheduler with sorting and recurring tasks?" surfaced the back-to-back boundary case
   and the unpadded `"7:00"` trap, both of which I'd have missed and both of which became
   real tests.
4. **Making it argue against me.** Asking it to check my reasoning rather than confirm it
   — and pushing back when it agreed too readily. An assistant that validates everything
   is worse than no assistant, because it feels like verification without being any.

**What worked least:** open-ended "make this better" requests. They produce plausible
changes with no stated reasoning, which is the hardest kind of output to review — I ended
up reconstructing the intent before I could judge the code.

**b. Judgment and verification**

**The clearest rejection: collapsing the two scheduling passes.**

I asked the assistant which function in `pawpal_system.py` had the most complicated
algorithm and how to simplify it. It identified `build_plan()` and proposed three changes:
extract the triage loop into its own method, wrap the free-interval list in a `FreeTime`
class, and **collapse the two placement passes into one helper taking a "finder" callable**,
since the passes differ only in how they locate a slot.

I took the first two and rejected the third.

The first two are renaming, not cleverness — `free[index:index+1] = leftovers` is the
densest line in the file, and `FreeTime.book()` says what it does. But the third trades a
reader's comprehension for a line count. Folding both passes behind
`_place(task, free, finder, reason)` means anyone reading `build_plan` has to chase a
lambda to find out what "find a slot" means in each case, and the two passes also *fail*
differently — one reports "your requested time collides", the other "no window had enough
minutes left". Twelve honest duplicated lines beat one abstraction that hides two
different failure modes behind one parameter. It is the more Pythonic version and the
worse code. I left a comment in `build_plan` saying so, so the next person doesn't
"helpfully" re-apply it.

**How I verified things rather than trusting them.**

- **Ran it.** Captured `main.py` output before and after the refactor and compared — it
  was byte-identical, which is what made the refactor safe to keep.
- **Mutation-tested the assertions.** A green suite only proves the tests ran. I changed
  the overlap test in `detect_conflicts()` from `<` to `<=` and confirmed
  `test_back_to_back_tasks_do_not_conflict` actually failed, with a bogus 0-minute
  conflict. Then reverted. Same idea for sorting: I checked that naive string comparison
  really does put `"18:00"` before `"7:00"`, so the test defends a real regression instead
  of restating the implementation.
- **Questioned confident claims.** When the assistant generated a suite that passed on the
  first run, I treated that as a reason for suspicion rather than satisfaction, which is
  what prompted the mutation checks above.
- **Checked the repo, not just the diff.** Before committing I looked at what `git add .`
  would actually stage, and found a stray tracked worktree gitlink and a corrupted
  `.gitignore` line (UTF-16 bytes appended to `.DS_Store` with no newline, silently
  killing the rule below it). Neither was mine and neither belonged in a feature commit,
  so I staged files explicitly instead.

**The honest limit of my verification:** I confirmed the *outputs* match my intent, but I
have not proved the placement algorithm is optimal — only that it is consistent and that
it explains itself. A greedy first-fit can leave a better arrangement on the table, and I
accepted that knowingly rather than discovered it.

**c. AI strategy**

**Which assistant features were most effective**, in order:

1. **Multi-file editing in one pass.** Recurrence was not a one-file change — it touched
   `CareTask` (a new `due_date` field and the rollover methods), `Scheduler`
   (`complete_task` returning the next instance), `build_plan` (a new date gate and skip
   reason), `main.py`, `app.py` and the tests. Having the assistant hold all of those at
   once meant the date parameter threaded through consistently instead of me patching one
   call site at a time and finding the mismatches later.
2. **Running the code and reading its own output.** The assistant ran `main.py` and
   `pytest` directly, so claims about behaviour were checked rather than predicted. This
   is also what made the refactor safe — capturing output before and after and comparing.
3. **Chat for explanation rather than generation.** The most valuable single exchange
   wasn't code at all: asking which function was most complicated and why. That produced
   a ranked argument I could disagree with, and I did.
4. **Repo awareness.** It noticed the corrupted `.gitignore` line and the stray tracked
   worktree while staging a commit — neither was something I'd asked about, and neither
   would I have caught by reading the diff.

**How separate chat sessions helped.** Running design, implementation, and testing in
different sessions kept each one honest. The practical benefit was in the testing session
specifically: a session that has just spent an hour writing `build_plan` is primed to
believe `build_plan` works, and writes tests that confirm it. Coming at the finished
`pawpal_system.py` as something to *attack* produced different tests — the back-to-back
boundary case, the empty-owner case, the malformed-time case — because the question
changed from "does this do what I meant?" to "what would break this?". Separate sessions
also kept each one short enough that I could still see the whole context I was working in,
rather than trusting that something agreed 200 messages ago still held.

The cost is real and worth naming: context has to be re-established each time, and twice I
had to re-explain a design decision the earlier session already knew. For anything smaller
than this project that overhead would not pay for itself.

---

## 4. Testing and Verification

**a. What you tested**

32 tests in `tests/test_pawpal.py`, grouped into five behaviours, each with its happy path
and its edge cases:

| Behaviour | Why it needed tests |
|-----------|---------------------|
| **Sorting** (5) | The "smart" claim rests on ordering being right. The key test is that `"7:00"` sorts before `"18:00"` — naive string comparison gets this backwards, and the bug would look like a cosmetic glitch rather than a logic error. |
| **Filtering** (5) | Two optional filters that stack, where `None` means "don't care". Easy to get subtly wrong in a way that silently returns too much. I assert the completed/incomplete halves *partition* the full list, so neither can quietly drop a task. |
| **Recurrence** (6) | The newest logic, and its failure mode is invisible: if no next instance is created, nothing errors — the task simply never comes back. Covers daily, weekly keeping its weekday, `once` queueing nothing, double-completion not breeding duplicates, month-end arithmetic, and the queued instance staying out of today's plan. |
| **Conflict detection** (7) | Two opposite failures to guard: missing a real overlap, and flagging a false one. The back-to-back test (07:00–07:30 then 07:30–07:40 must *not* conflict) guards the second, which is the easier mistake to make. |
| **Empty / degenerate** (6) | A pet with no tasks, an owner with no pets, an owner with no free time, a task longer than any window, zero duration. Each must return an explained plan rather than an exception — a planning assistant that crashes on an empty day is useless on day one. |
| **Multi-pet budgeting** (1) | The design's whole premise. Two pets with 30 min of work each in a 45-min window must book 30 minutes and skip one task, not book 60. This test fails if anyone ever "optimises" the scheduler back to planning per pet. |

**Why these and not others.** I picked tests by asking where a bug would be *silent*.
Sorting, filtering and recurrence all fail quietly — wrong order, missing rows, a task
that just never reappears. Those got the most coverage. Things that fail loudly need less.

**b. Confidence**

**★★★★☆ (4 / 5).**

The four stars are earned rather than assumed: I mutation-tested the suite rather than
trusting a green run. Flipping `<` to `<=` in `detect_conflicts()` makes the back-to-back
test fail as it should, and the unpadded-time sorting test fails under string comparison.
So the assertions are load-bearing, not decorative.

**The missing star, specifically:**

- **Window-splitting is only tested by outcome.** `FreeTime.book()` splitting a window
  into two usable leftovers is exercised incidentally, never asserted directly. If it
  dropped the second leftover, most tests would still pass.
- **Overlapping `TimeSlot`s are untested.** `_windows()` trims them so the same minute is
  never offered twice. Nothing proves it, and an owner who enters 07:00–09:00 *and*
  08:00–10:00 would silently get 120 phantom minutes if that trimming broke.
- **No midnight handling at all.** Not an untested case — an unimplemented one. A task
  pinned at 23:50 for 30 minutes is silently clipped rather than rejected or wrapped.

**What I'd test next, in order:** the window-splitting leftovers, overlapping availability
slots, then a property-style check that `scheduled_minutes()` never exceeds
`total_available_minutes()` across randomly generated task sets — that last one is the
single test most likely to find something I haven't thought of, because it doesn't depend
on me imagining the failing case first.

---

## 5. Reflection

**a. What went well**

**The catch that `DailyPlan` had to be per-owner, not per-pet.** It was a design bug, not
a coding one: `build(owner, pet)` ran once per pet and each call independently spent the
*whole* time budget, so an owner with two pets got two plans that both claimed 08:00–08:30.
Nothing would have crashed. The tests would have passed. The app would have cheerfully
double-booked a real person every single day.

What makes me satisfied with it is that the *signature* was the evidence. `build()`
already needed the `Owner` for its constraints; a method taking the owner for its limits
and the pet for its data is really an owner-level operation wearing a disguise. Reading
that off the API rather than discovering it from a bug report is the part I'd want to
repeat.

Second place: the conflict detector reporting instead of resolving. It would have been
easy to auto-shuffle the losing task and feel clever. Warning the owner and leaving the
decision with them is the less impressive-looking choice and the right one.

**b. What you would improve**

- **Midnight is unmodelled.** A task pinned at 23:50 for 30 minutes gets silently clipped.
  Not a bug I introduced so much as a case the `TimeSlot` design cannot express. I'd
  redesign availability around real datetimes rather than `"HH:MM"` strings.
- **Placement is greedy first-fit.** It never backtracks, so a long low-priority task can
  take a window that two higher-priority tasks would have shared better. Honest and
  explainable, but not optimal. I'd try scoring a few arrangements before committing.
- **Recurrence only moves forward on completion.** If the owner never marks Monday's walk
  done, it just sits there overdue and no Tuesday instance appears. A real assistant would
  roll the day over whether or not you kept up with it.
- **`CareTask` is doing two jobs.** It is both the reusable template and the dated
  instance. `due_date` papers over that; a proper split into `TaskTemplate` and
  `TaskInstance` would be cleaner, and I'd do it before adding any more recurrence
  features.

**c. Key takeaway**

**The architectural decisions were the ones AI could not make for me, and they were also
the ones that mattered most.**

Every genuinely consequential moment in this project was a judgment call where the
assistant could produce a competent answer but not the *right* one, because "right"
depended on context it didn't have:

- Per-pet vs. per-owner planning — it would have implemented either, correctly.
- Warning about conflicts vs. auto-resolving them — both are defensible; only one respects
  that the owner knows things the program doesn't.
- Requested time beating priority — the program's ranking is a general rule; the owner's
  08:00 is specific knowledge.
- Keeping two duplicated passes rather than one clever abstraction — the "better" code by
  most style metrics was the worse code for the next human reading it.

AI made the implementation fast and the documentation good, and it was genuinely useful
for surfacing edge cases I hadn't imagined. What it could not do is decide what the system
*should* be, because every one of those choices came down to a value — who gets to decide,
who has to understand it later, what failure is acceptable — rather than a fact.

The practical version of that lesson: **a green test suite is evidence the tests ran, not
evidence the code is right.** Mutating the conflict boundary from `<` to `<=` and watching
a test fail told me more about my system's reliability than the 32 passing tests did.
Being the lead architect mostly meant refusing to accept output I hadn't tried to break.
