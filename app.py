from datetime import date

import streamlit as st

from pawpal_system import (
    FREQUENCIES,
    PRIORITY_RANK,
    CareTask,
    DailyPlan,
    Owner,
    Pet,
    PlanEntry,
    Scheduler,
    TimeSlot,
)

st.set_page_config(page_title="PawPal+", page_icon="🐾", layout="centered")

st.title("🐾 PawPal+")

st.markdown(
    """
Welcome to the PawPal+ starter app.

This file is intentionally thin. It gives you a working Streamlit app so you can start quickly,
but **it does not implement the project logic**. Your job is to design the system and build it.

Use this app as your interactive demo once your backend classes/functions exist.
"""
)

with st.expander("Scenario", expanded=True):
    st.markdown(
        """
**PawPal+** is a pet care planning assistant. It helps a pet owner plan care tasks
for their pet(s) based on constraints like time, priority, and preferences.

You will design and implement the scheduling logic and connect it to this Streamlit UI.
"""
    )

with st.expander("What you need to build", expanded=True):
    st.markdown(
        """
At minimum, your system should:
- Represent pet care tasks (what needs to happen, how long it takes, priority)
- Represent the pet and the owner (basic info and preferences)
- Build a plan/schedule for a day that chooses and orders tasks based on constraints
- Explain the plan (why each task was chosen and when it happens)
"""
    )

st.divider()

st.subheader("Quick Demo Inputs")

# The owner lives in session state so the pets and tasks built up here survive
# the rerun that every widget interaction triggers.
if "owner" not in st.session_state:
    st.session_state.owner = Owner(
        name="Jordan",
        available_timeslots=[
            TimeSlot("Morning", "07:00", "08:30"),
            TimeSlot("Evening", "18:00", "19:30"),
        ],
    )

if "plan" not in st.session_state:
    st.session_state.plan = None

owner: Owner = st.session_state.owner
scheduler = Scheduler(owner)

owner_name = st.text_input("Owner name", value=owner.name)
pet_name = st.text_input("Pet name", value="Mochi")
species = st.selectbox("Species", ["dog", "cat", "other"])

# The text box is the source of truth for the name; the object keeps its pets.
if owner_name.strip() and owner_name.strip() != owner.name:
    owner.name = owner_name.strip()

st.caption(
    f"Free today: "
    + " · ".join(
        f"{slot.label} {slot.start_time}–{slot.end_time}"
        for slot in owner.available_timeslots
    )
    + f" ({owner.total_available_minutes()} min)"
)

st.markdown("### Tasks")
st.caption("Tasks are attached to the pet named above and fed straight to the scheduler.")

col1, col2, col3 = st.columns(3)
with col1:
    task_title = st.text_input("Task title", value="Morning walk")
with col2:
    duration = st.number_input("Duration (minutes)", min_value=1, max_value=240, value=20)
with col3:
    priority = st.selectbox(
        "Priority", sorted(PRIORITY_RANK, key=PRIORITY_RANK.get), index=2
    )

col4, col5 = st.columns(2)
with col4:
    frequency = st.selectbox("Frequency", FREQUENCIES)
with col5:
    start_time = st.text_input(
        "Requested start (HH:MM, optional)",
        value="",
        placeholder="07:00",
        help="Leave blank to let the scheduler place it wherever it fits.",
    )


def pet_for(name: str, species: str) -> Pet:
    """The owner's pet by that name, registering it the first time it is used.

    add_pet is idempotent by identity, so a freshly built Pet would always look
    new to it — the duplicate check has to be on the name.
    """
    for existing in owner.pets:
        if existing.name.lower() == name.strip().lower():
            return existing
    pet = Pet(name.strip(), species, age_years=0)
    owner.add_pet(pet)
    return pet


if st.button("Add task"):
    if not pet_name.strip():
        st.warning("Name the pet before adding tasks to it.")
    elif not task_title.strip():
        st.warning("Give the task a title.")
    else:
        scheduler.add_task(
            pet_for(pet_name, species),
            CareTask(
                title=task_title.strip(),
                duration_minutes=int(duration),
                priority=priority,
                start_time=start_time.strip(),
                frequency=frequency,
            ),
        )
        st.session_state.plan = None

today = date.today()
weekday = today.strftime("%A")

all_tasks = owner.get_all_tasks()
if not all_tasks:
    st.info("No tasks yet. Add one above.")
else:
    # --- Filter controls, wired straight to Scheduler.filter_tasks ---------
    st.markdown("#### Current tasks")

    fcol1, fcol2 = st.columns(2)
    with fcol1:
        pet_choice = st.selectbox(
            "Show pet",
            ["All pets"] + [pet.name for pet in owner.pets],
            help="Filters with Scheduler.filter_tasks(pet_name=...).",
        )
    with fcol2:
        status_choice = st.radio(
            "Show status",
            ["All", "Still to do", "Done"],
            horizontal=True,
            help="Filters with Scheduler.filter_tasks(completed=...).",
        )

    # None means "don't care" on both filters, so the widgets map directly onto
    # the scheduler's own API rather than being re-implemented here.
    completed_filter = {"All": None, "Still to do": False, "Done": True}[status_choice]
    visible = scheduler.filter_tasks(
        pet_name=None if pet_choice == "All pets" else pet_choice,
        completed=completed_filter,
    )
    # Sorted chronologically — the sorter composes with the filtered slice.
    visible = scheduler.sort_by_time(visible)

    if not visible:
        st.info("No tasks match that filter.")
    else:
        st.caption(
            f"Showing {len(visible)} of {len(all_tasks)} task(s), "
            "sorted by requested time (untimed tasks last)."
        )
        st.table(
            [
                {
                    "Requested": task.start_time or "—",
                    "Pet": task.pet_name(),
                    "Task": task.title,
                    "Minutes": task.duration_minutes,
                    "Priority": task.priority,
                    "Frequency": task.frequency,
                    "Due": f"{task.due_date:%a %d %b}" if task.due_date else "today",
                    "Done": "✓" if task.completed else "",
                }
                for task in visible
            ]
        )

st.divider()

st.subheader("Build Schedule")

st.caption(
    f"Planning for {weekday}, {today:%d %b}. Weekly tasks are filtered against "
    "the weekday; tasks queued for a future date sit out until their day."
)

# --- Conflict warnings -----------------------------------------------------
# Shown before the plan is generated, not only after: the owner can still fix a
# time, and the fix is the task list directly above. Each warning names both
# tasks and the consequence, because "two intervals overlap" is not actionable
# but "Brushing will not be scheduled" is. Never an exception — an overlap is
# something the owner may well have meant.
conflicts = scheduler.detect_conflicts(weekday, today)
if all_tasks:
    if conflicts:
        st.markdown("##### ⚠️ Scheduling conflicts")
        for conflict in conflicts:
            scope = (
                f"Both tasks are for {conflict.first.pet_name()}"
                if conflict.same_pet()
                else f"{conflict.first.pet_name()} and {conflict.second.pet_name()} "
                "need you at the same time"
            )
            st.warning(
                f"**{conflict.first.title}** and **{conflict.second.title}** "
                f"overlap by {conflict.overlap_minutes} minutes.\n\n"
                f"{scope}. **{conflict.second.title}** will be left out of "
                f"today's plan unless you move one of them.",
                icon="⚠️",
            )
    else:
        st.success("No scheduling conflicts — every requested time is clear.", icon="✅")

col6, col7 = st.columns(2)
with col6:
    if st.button("Generate schedule", type="primary", use_container_width=True):
        st.session_state.plan = scheduler.build_plan(weekday, today)
with col7:
    if st.button("Reset day (reopen tasks)", use_container_width=True):
        scheduler.reset_day()
        st.session_state.plan = None

plan: DailyPlan | None = st.session_state.plan

if plan is None:
    st.info("Add tasks above, then generate the schedule.")
else:
    col8, col9, col10 = st.columns(3)
    col8.metric("Booked", f"{plan.scheduled_minutes()} min")
    col9.metric("Free time left", f"{plan.unused_minutes()} min")
    col10.metric("Not scheduled", len(plan.skipped))

    rows = plan.to_table()
    if rows:
        if not plan.skipped:
            st.success(
                f"Everything fits — {len(rows)} task(s) scheduled across "
                f"{len(owner.pets)} pet(s).",
                icon="✅",
            )
        st.markdown("#### Today's schedule")
        st.caption("In clock order. 'Why' is the scheduler's own reason for the slot.")
        st.table(rows)
    else:
        st.warning(
            "Nothing fit in the owner's free windows. Check the reasons below.",
            icon="⚠️",
        )

    if plan.skipped:
        st.markdown("#### Not scheduled")
        st.caption("Every task left out, with the reason it was left out.")
        st.table(plan.skipped_table())

    with st.expander("Why does the plan look like this?"):
        st.text(plan.explain())

    done_col, _ = st.columns(2)
    with done_col:
        entry: PlanEntry
        for entry in plan.entries:
            if st.button(
                f"Mark done · {entry.task.title} ({entry.start_time})",
                key=f"done_{id(entry.task)}",
                use_container_width=True,
            ):
                # Completing a daily or weekly task queues its next instance on
                # the same pet, dated forward; complete_task hands it back so we
                # can say so.
                follow_up = scheduler.complete_task(entry.task, on_date=today)
                if follow_up is not None:
                    st.session_state.rollover = (
                        f"{follow_up.title} repeats {follow_up.frequency} — "
                        f"next one queued for {follow_up.due_date:%A %d %b}."
                    )
                else:
                    st.session_state.rollover = None
                st.session_state.plan = scheduler.build_plan(weekday, today)
                st.rerun()

    if st.session_state.get("rollover"):
        st.success(st.session_state.rollover)
