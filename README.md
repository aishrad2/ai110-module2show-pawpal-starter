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

```
# e.g.:
# Daily plan for Biscuit (Golden Retriever):
#   08:00 — Morning walk (30 min) [priority: high]
#   09:00 — Feeding (10 min) [priority: high]
#   ...
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
# Paste your pytest output here
```

## 📐 Smarter Scheduling

> The method mapping below reflects the design in `diagrams/uml_draft.mmd`. The bodies in
> `pawpal_system.py` are still stubs, so the notes describe intended behavior.

| Feature | Method(s) | Notes |
|---------|-----------|-------|
| Task sorting | `CareTask.weight()` | `PRIORITY_RANK[priority] * 100 - duration_minutes`. Priority is the dominant term; duration breaks ties in favour of shorter tasks, so more of the day's care fits. |
| Filtering | `DailyPlan.build()` | A task that fits no remaining window is recorded in `DailyPlan.skipped` as a `PlanEntry` carrying a `reason`. |
| Conflict handling | `CareTask.is_pinned()`, `DailyPlan.build()` | Tasks with an owner-requested `start_time` are placed first. A requested time that overlaps another or falls outside every `TimeSlot` is skipped with a reason. |
| Multi-pet budgeting | `DailyPlan.build()`, `Owner.total_available_minutes()` | One plan covers the owner's whole day across every pet, so the shared time budget is spent once rather than once per pet. |
| Recurring tasks | — | Not modelled. `CareTask` represents a single day's task; recurrence would require a schedule field and a day-of-week filter in `build()`. |

## 📸 Demo Walkthrough

Describe your app in numbered steps so a reader can follow along without watching a video:

1. <!-- Describe this step -->
2. <!-- Describe this step -->
3. <!-- Describe this step -->
4. <!-- Describe this step -->
5. <!-- Add more steps as needed -->

**Screenshot or video** *(optional)*: <!-- Insert a screenshot or link to a demo video here -->
