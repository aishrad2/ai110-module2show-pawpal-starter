"""Terminal demo for PawPal+.

Builds one owner with two pets and a handful of care tasks, asks the Scheduler
for today's plan, and prints it. Run it with:

    python main.py
"""

import sys

from pawpal_system import CareTask, Owner, Pet, Scheduler, TimeSlot

#: The day we are planning. Weekly tasks are filtered against this.
TODAY = "Tuesday"


def build_owner() -> Owner:
    """One owner, two pets, and the tasks they need done today."""
    jordan = Owner(
        name="Jordan",
        available_timeslots=[
            TimeSlot("Morning", "07:00", "08:30"),
            TimeSlot("Evening", "18:00", "19:30"),
        ],
    )

    mochi = Pet("Mochi", "dog", age_years=3)
    biscuit = Pet("Biscuit", "cat", age_years=7)

    scheduler = Scheduler(jordan)
    scheduler.add_task(mochi, CareTask("Morning walk", 30, "high", start_time="07:00"))
    scheduler.add_task(mochi, CareTask("Meds", 10, "high", start_time="07:45"))
    scheduler.add_task(mochi, CareTask("Training", 25, "medium", start_time="18:15"))
    scheduler.add_task(biscuit, CareTask("Feeding", 10, "high"))
    scheduler.add_task(biscuit, CareTask("Litter box", 15, "medium"))
    scheduler.add_task(
        biscuit,
        CareTask("Nail trim", 20, "low", frequency="weekly", day_of_week="Sunday"),
    )

    return jordan


def print_schedule(plan) -> None:
    """Print the plan as a 'Today's Schedule' table."""
    print("=" * 68)
    print(f"Today's Schedule — {plan.owner.name} ({TODAY})")
    print("=" * 68)

    rows = plan.to_table()
    if not rows:
        print("Nothing could be scheduled today.")
    else:
        print(f"{'TIME':<13}{'PET':<10}{'TASK':<16}{'MIN':>4}  {'PRIORITY':<9}WINDOW")
        print("-" * 68)
        for row in rows:
            print(
                f"{row['Time']:<13}{row['Pet']:<10}{row['Task']:<16}"
                f"{row['Minutes']:>4}  {row['Priority']:<9}{row['Window']}"
            )

    if plan.skipped:
        print()
        print("Not scheduled today:")
        for row in plan.skipped_table():
            print(
                f"  {row['Pet']} · {row['Task']} "
                f"({row['Minutes']} min) — {row['Reason']}"
            )

    print()
    print(
        f"{plan.scheduled_minutes()} of {plan.owner.total_available_minutes()} "
        f"free minutes used; {plan.unused_minutes()} left over."
    )


def main() -> None:
    owner = build_owner()
    plan = Scheduler(owner).build_plan(TODAY)
    print_schedule(plan)


if __name__ == "__main__":
    # The output uses · and —, which a default Windows console codepage
    # mangles. Ask stdout for UTF-8 where the interpreter supports it.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    main()
