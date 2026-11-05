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

- What constraints does your scheduler consider (for example: time, priority, preferences)?
- How did you decide which constraints mattered most?

**b. Tradeoffs**

- Describe one tradeoff your scheduler makes.
- Why is that tradeoff reasonable for this scenario?

---

## 3. AI Collaboration

**a. How you used AI**

- How did you use AI tools during this project (for example: design brainstorming, debugging, refactoring)?
- What kinds of prompts or questions were most helpful?

**b. Judgment and verification**

- Describe one moment where you did not accept an AI suggestion as-is.
- How did you evaluate or verify what the AI suggested?

---

## 4. Testing and Verification

**a. What you tested**

- What behaviors did you test?
- Why were these tests important?

**b. Confidence**

- How confident are you that your scheduler works correctly?
- What edge cases would you test next if you had more time?

---

## 5. Reflection

**a. What went well**

- What part of this project are you most satisfied with?

**b. What you would improve**

- If you had another iteration, what would you improve or redesign?

**c. Key takeaway**

- What is one important thing you learned about designing systems or working with AI on this project?
