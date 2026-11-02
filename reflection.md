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

| Class | Attributes | Key methods |
|-------|-----------|-------------|
| `Owner` | `name`, `start_time`, `available_minutes`, `pets` | `add_pet()` |
| `Pet` | `name`, `species`, `age_years`, `tasks` | `add_task()` |
| `CareTask` | `title`, `duration_minutes`, `priority`, `start_time` | `weight()` |
| `DailyPlan` | `pet`, `entries`, `skipped` | `build()`, `explain()`, `to_table()` |

`DailyPlan.build()` does the scheduling: sort by `CareTask.weight()`, drop tasks that
don't fit in `available_minutes`, assign start times in order. `explain()` says why each
task was chosen or skipped.

Considered and left out to keep it simple: a separate `Scheduler`, a `ScheduledTask`
split from `CareTask`, `TimeWindow`, and `OwnerPreferences`. If any becomes necessary
during implementation, that's a design change for 1b.

**b. Design changes**

- Did your design change during implementation?
- If yes, describe at least one change and why you made it.

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
