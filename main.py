"""Terminal demo for PawPal+.

Builds one owner with two pets and a handful of care tasks, asks the Scheduler
for today's plan, and prints it — then shows the same tasks through
``Scheduler.sort_by_time`` and ``Scheduler.filter_tasks``, the conflict
detector, and the recurring-task rollover.

The tasks below are added deliberately out of chronological order (evening
first, the 07:00 walk fifth) so the sorted view has something to prove, and two
of them deliberately clash (see ``build_scheduler``) so the conflict detector
has something to find. Run it with:

    python main.py
"""

import sys
from datetime import date

from pawpal_system import CareTask, Pet, Scheduler, TimeSlot, Owner

#: The day we are planning. Recurrence dates are counted from here, and weekly
#: tasks are filtered against its weekday name.
TODAY_DATE = date.today()
TODAY = TODAY_DATE.strftime("%A")


def build_scheduler() -> Scheduler:
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

    # Added out of order on purpose — nothing here is in clock order, and two
    # tasks have no requested time at all.
    scheduler.add_task(mochi, CareTask("Training", 25, "medium", start_time="18:15"))
    scheduler.add_task(biscuit, CareTask("Feeding", 10, "high", start_time="07:30"))
    scheduler.add_task(mochi, CareTask("Meds", 10, "high", start_time="07:45"))
    scheduler.add_task(biscuit, CareTask("Litter box", 15, "medium"))
    scheduler.add_task(mochi, CareTask("Morning walk", 30, "high", start_time="07:00"))
    scheduler.add_task(
        biscuit,
        CareTask("Nail trim", 20, "low", frequency="weekly", day_of_week="Sunday"),
    )

    # --- Deliberate conflicts, for Step 4 --------------------------------
    # Two pets, one owner, one pair of hands. Biscuit's brushing is booked for
    # 07:45-08:00, straight over Mochi's 07:45-07:55 meds: different pets, same
    # ten minutes. Mochi's puzzle toy (18:20-18:30) lands inside his own
    # training session (18:15-18:40): same pet, same problem. The scheduler
    # reports both and still builds a plan.
    scheduler.add_task(biscuit, CareTask("Brushing", 15, "medium", start_time="07:45"))
    scheduler.add_task(mochi, CareTask("Puzzle toy", 10, "low", start_time="18:20"))

    # One task is already finished. It shows up in the completion filter and the
    # scheduler leaves it out of the plan. It is a one-off on purpose: a "once"
    # task does not come round again, so completing it here leaves the task list
    # untouched and the recurrence demo further down starts from a clean slate.
    evening_play = CareTask(
        "Evening play", 15, "medium", start_time="18:40", frequency="once"
    )
    scheduler.add_task(biscuit, evening_play)
    scheduler.complete_task(evening_play, on_date=TODAY_DATE)

    return scheduler


def heading(text: str) -> None:
    """Print a section banner."""
    print("=" * 68)
    print(text)
    print("=" * 68)


def titles(tasks) -> str:
    """Comma-separated task titles, or 'none' for an empty list."""
    return ", ".join(task.title for task in tasks) or "none"


def print_schedule(plan) -> None:
    """Print the plan as a 'Today's Schedule' table."""
    heading(f"Today's Schedule — {plan.owner.name} ({TODAY})")

    # Warnings first: the plan below is still valid, but the owner should know
    # which requested times could not all be honoured.
    if plan.warnings:
        for warning in plan.warnings:
            print(warning)
        print()

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


def print_sorted_tasks(scheduler: Scheduler) -> None:
    """Every task in clock order, whatever order it was added in."""
    heading("Every task, sorted by requested time")

    print(f"{'TIME':<9}{'PET':<10}{'TASK':<16}{'MIN':>4}  {'PRIORITY':<9}STATUS")
    print("-" * 68)
    for task in scheduler.sort_by_time():
        when = task.start_time or "—"
        status = "done" if task.completed else "to do"
        print(
            f"{when:<9}{task.pet_name():<10}{task.title:<16}"
            f"{task.duration_minutes:>4}  {task.priority:<9}{status}"
        )
    print()
    print("Tasks with no requested time sort to the bottom, then by title.")


def print_filters(scheduler: Scheduler) -> None:
    """The same tasks, narrowed by pet name and by completion status."""
    heading("Filtered views")

    # Filter by pet name, then hand the result to the sorter.
    for pet in scheduler.owner.pets:
        tasks = scheduler.sort_by_time(scheduler.filter_tasks(pet_name=pet.name))
        print(f"{pet.name}'s tasks ({len(tasks)}):")
        for task in tasks:
            when = task.start_time or "—"
            print(f"  {when:<7}{task.title}")
        print()

    # Filter by completion status.
    remaining = scheduler.filter_tasks(completed=False)
    finished = scheduler.filter_tasks(completed=True)
    print(f"Still to do ({len(remaining)}): {titles(remaining)}")
    print(f"Already done ({len(finished)}): {titles(finished)}")
    print()

    # Both filters at once.
    mochi_todo = scheduler.filter_tasks(pet_name="mochi", completed=False)
    print(f"Mochi, still to do ({len(mochi_todo)}): {titles(mochi_todo)}")
    print("(pet name matched case-insensitively — 'mochi' found 'Mochi')")


def print_conflicts(scheduler: Scheduler) -> None:
    """Every pair of outstanding tasks whose requested times overlap."""
    heading("Conflict check")

    conflicts = scheduler.detect_conflicts(TODAY, TODAY_DATE)
    if not conflicts:
        print("No overlapping requested times. ✓")
        return

    print(f"Found {len(conflicts)} overlapping pair(s):")
    for conflict in conflicts:
        scope = "same pet" if conflict.same_pet() else "different pets"
        print(f"  {conflict.message()}  [{scope}]")

    print()
    print(
        "Nothing was raised and nothing crashed — the plan above was still\n"
        "built. The task that lost each overlap is listed under 'Not scheduled'."
    )


def print_recurrence(scheduler: Scheduler) -> None:
    """Complete a daily and a weekly task; show the next instances appear."""
    heading("Recurring tasks roll forward on completion")

    # Pick one daily and one weekly task that are still outstanding.
    outstanding = scheduler.filter_tasks(completed=False)
    samples = [
        next((task for task in outstanding if task.frequency == "daily"), None),
        next((task for task in outstanding if task.frequency == "weekly"), None),
    ]

    for task in samples:
        if task is None:
            continue
        before = len(scheduler.get_all_tasks())
        follow_up = scheduler.complete_task(task, on_date=TODAY_DATE)
        after = len(scheduler.get_all_tasks())

        print(f"Completed: {task.pet_name()} · {task.title} ({task.frequency})")
        if follow_up is None:
            print("  -> one-off task, nothing queued.")
        else:
            gap = (follow_up.due_date - TODAY_DATE).days
            print(
                f"  -> next instance queued for {follow_up.due_date:%A %d %b} "
                f"(today + {gap} day{'s' if gap != 1 else ''}), "
                f"still at {follow_up.start_time or 'no fixed time'}, "
                f"completed={follow_up.completed}"
            )
            print(f"  -> tasks across all pets: {before} -> {after}")
        print()

    print(
        "Dates come from timedelta(days=1) for daily and timedelta(days=7) for\n"
        "weekly, so month ends and leap days take care of themselves, and a\n"
        "weekly task keeps landing on the same weekday."
    )

    # The queued instances are dated for the future, so replanning today leaves
    # them out rather than double-booking the owner.
    print()
    tomorrow_tasks = [
        task
        for task in scheduler.get_all_tasks()
        if task.due_date is not None and task.due_date > TODAY_DATE
    ]
    print(f"Queued for later ({len(tomorrow_tasks)}): {titles(tomorrow_tasks)}")
    print("These are skipped when today's plan is rebuilt — see the reasons below.")
    print()

    replan = scheduler.build_plan(TODAY, TODAY_DATE)
    for row in replan.skipped_table():
        if "occurrence" in row["Reason"]:
            print(f"  {row['Pet']} · {row['Task']} — {row['Reason']}")


def main() -> None:
    scheduler = build_scheduler()

    print_schedule(scheduler.build_plan(TODAY, TODAY_DATE))
    print()
    print_conflicts(scheduler)
    print()
    print_sorted_tasks(scheduler)
    print()
    print_filters(scheduler)
    print()
    # Runs last: it completes tasks, which changes the lists the sections above
    # print.
    print_recurrence(scheduler)


if __name__ == "__main__":
    # The output uses · and —, which a default Windows console codepage
    # mangles. Ask stdout for UTF-8 where the interpreter supports it.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    main()
