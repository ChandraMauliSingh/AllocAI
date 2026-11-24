import os
import re
import json
import pandas as pd
import streamlit as st

import agents
from invigilation_engine import (
    add_faculty_leave,
    remove_faculty_leave,
    clear_faculty_leaves,
    assign_invigilators,
)
from solver_engine import solve_exam_schedule
from seating_engine import generate_roll_number_seating

st.set_page_config(
    page_title="AllocAI — Exam & Invigilation Command Center",
    page_icon="🎓",
    layout="wide",
)


def load_json(path: str):
    if os.path.exists(path) and os.path.getsize(path) > 0:
        try:
            with open(path, "r") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return None
    return None


def sync_leaves_from_prompt(prompt: str) -> list[str] | None:
    """Automatically adds or removes faculty in data/leaves.json when mentioned in natural language."""
    q = prompt.lower()
    fac_nums = re.findall(r'(?:fac(?:ulty)?\.?\s*#?)\s*(\d+)', q)

    if ("all facult" in q or "everyone" in q) and any(
        w in q for w in ["clear", "reset", "available", "back", "present", "no leave"]
    ):
        return clear_faculty_leaves()

    if not fac_nums:
        return None

    updated = None
    is_removing = any(w in q for w in ["back", "available", "present", "return", "remove", "cancel leave"])
    is_adding = any(w in q for w in ["leave", "absent", "unavailable", "off"])

    for num in fac_nums:
        if is_removing and not is_adding:
            updated = remove_faculty_leave(num)
        elif is_adding:
            updated = add_faculty_leave(num)

    return updated


# --- Header & Top KPIs ---
st.title("🎓 AllocAI — Autonomous Exam, Seating & Invigilation System")
st.caption("Hybrid OR-Tools (CP-SAT) Optimization • True Checkerboard Seating • Rank-Aware Invigilation • Local Llama 3.2")

schedule_data = load_json("data/exam_schedule.json") or {}
seating_data = load_json("data/master_seating_chart.json") or {}
faculty_sched_data = load_json("data/faculty_schedule.json") or []
leaves_data = load_json("data/leaves.json") or []
faculty_master = load_json("data/faculty.json") or []

total_fac_count = len(faculty_master) if faculty_master else 50
active_fac_count = max(0, total_fac_count - len(leaves_data))

k1, k2, k3, k4 = st.columns(4)
k1.metric("Scheduled Courses", len(schedule_data))
k2.metric("Students Seated", len(seating_data))
k3.metric("Active Faculty", active_fac_count)
k4.metric("Faculty on Leave", len(leaves_data))

st.divider()

# --- Navigation ---
page = st.sidebar.radio(
    "Workspace",
    [
        "💬 Admin Assistant Chat",
        "📅 Master Exam Schedule",
        "🪑 Room-Wise & Student Seating",
        "👨‍🏫 Faculty Hierarchy & Leaves",
        "📜 Institutional Rules",
    ],
)

# ==============================================================================
# 1. ADMIN ASSISTANT CHAT
# ==============================================================================
if page == "💬 Admin Assistant Chat":
    st.subheader("💬 Natural Language Command & Query Assistant")
    st.markdown(
        "Try: *'Faculty 5 is on leave, update invigilation'* • *'Faculty 5 is back from leave'* • *'Make a fresh timetable'* • *'Where is STU001 sitting?'*"
    )

    if "messages" not in st.session_state:
        st.session_state.messages = []

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if user_prompt := st.chat_input("Type a command or question..."):
        st.session_state.messages.append({"role": "user", "content": user_prompt})
        with st.chat_message("user"):
            st.markdown(user_prompt)

        with st.chat_message("assistant"):
            with st.spinner("Running AllocAI engines..."):
                leave_result = sync_leaves_from_prompt(user_prompt)

                # If user only asked about leave/return without rebuilding full timetable, refresh invigilation immediately
                q_low = user_prompt.lower()
                only_leave_change = (leave_result is not None) and not any(
                    w in q_low for w in ["timetable", "time table", "schedule", "fresh", "rebuild", "remake", "generate"]
                )

                if only_leave_change:
                    if not os.path.exists("data/exam_schedule.json"):
                        solve_exam_schedule(num_slots=6)
                        generate_roll_number_seating()
                    assign_invigilators()
                    response = (
                        f"✅ Updated `data/leaves.json` and refreshed invigilation duties.\n\n"
                        f"**Current Faculty on Leave:** `{', '.join(leave_result) if leave_result else 'None'}`"
                    )
                else:
                    try:
                        res = agents.agent_executor.invoke({"input": user_prompt})
                        response = res.get("output", "Completed.")
                        if leave_result is not None:
                            # Ensure invigilation reflects the updated leaves.json
                            assign_invigilators()
                            response += f"\n\n**Current Faculty on Leave:** `{', '.join(leave_result) if leave_result else 'None'}`"
                    except Exception as e:
                        if leave_result is not None:
                            assign_invigilators()
                            response = (
                                f"✅ Updated `data/leaves.json` (`{', '.join(leave_result) if leave_result else 'None'}`) "
                                f"and refreshed invigilation schedule."
                            )
                        else:
                            response = f"⚠️ Agent hit an iteration/parsing limit. Please try a shorter query (e.g., *'Where is STU001?'*)."

            st.markdown(response)
            st.session_state.messages.append({"role": "assistant", "content": response})

# ==============================================================================
# 2. MASTER EXAM SCHEDULE
# ==============================================================================
elif page == "📅 Master Exam Schedule":
    st.subheader("📅 Master Exam Timetable")
    if schedule_data:
        rows = [
            {
                "Course ID": cid,
                "Time Slot": info.get("time_slot", ""),
                "Assigned Rooms": ", ".join(info.get("assigned_rooms", [])),
                "Total Students": info.get("total_students", 0),
            }
            for cid, info in schedule_data.items()
        ]
        df_sched = pd.DataFrame(rows)
        st.dataframe(df_sched, width="stretch", hide_index=True)

        if os.path.exists("data/exam_schedule.xlsx"):
            with open("data/exam_schedule.xlsx", "rb") as f:
                st.download_button("📥 Download Schedule (Excel)", f, file_name="exam_schedule.xlsx")
    else:
        st.info("No exam schedule generated yet. Run a generation command in Admin Assistant Chat.")

# ==============================================================================
# 3. ROOM-WISE & STUDENT SEATING (TABLES + VISUAL MATRIX)
# ==============================================================================
elif page == "🪑 Room-Wise & Student Seating":
    st.subheader("🪑 Seating Allocation — Student-Wise & Room-Wise Views")

    if not seating_data:
        st.info("Seating chart not generated yet.")
    else:
        # Flatten student seating into tabular rows
        student_rows = []
        for stu_id, courses in seating_data.items():
            for course_id, seat_info in courses.items():
                student_rows.append(
                    {
                        "Student ID": stu_id,
                        "Course": course_id,
                        "Time Slot": seat_info.get("time_slot", ""),
                        "Room ID": seat_info.get("room_id", ""),
                        "Room Name": seat_info.get("room_name", ""),
                        "Row": seat_info.get("row", ""),
                        "Seat #": seat_info.get("seat_number", ""),
                    }
                )

        df_all_seats = pd.DataFrame(student_rows)

        tab1, tab2 = st.tabs(["👤 Student-Wise Seating Table", "🏫 Room-Wise Seating Plan (Table & Grid)"])

        # --- TAB 1: STUDENT-WISE TABLE ---
        with tab1:
            search_stu = st.text_input("Search Student ID (e.g., STU001) or leave blank to view all").strip().upper()
            if search_stu:
                filtered_df = df_all_seats[df_all_seats["Student ID"].str.contains(search_stu, na=False)]
            else:
                selected_stu = st.selectbox("Quick Select Student", options=sorted(seating_data.keys()))
                filtered_df = df_all_seats[df_all_seats["Student ID"] == selected_stu]

            st.dataframe(filtered_df, width="stretch", hide_index=True)

            with st.expander("View All Students Seating Table"):
                st.dataframe(df_all_seats, width="stretch", hide_index=True)

        # --- TAB 2: ROOM-WISE TABLE + VISUAL SEAT MATRIX ---
        with tab2:
            slots_available = sorted(df_all_seats["Time Slot"].dropna().unique().tolist())
            selected_slot = st.selectbox("Select Time Slot", options=slots_available)

            slot_df = df_all_seats[df_all_seats["Time Slot"] == selected_slot]
            rooms_in_slot = sorted(slot_df["Room Name"].dropna().unique().tolist())

            if rooms_in_slot:
                selected_room = st.selectbox("Select Room", options=rooms_in_slot)
                room_df = slot_df[slot_df["Room Name"] == selected_room].sort_values(["Row", "Seat #"])

                st.markdown(f"**Room Table — {selected_room} ({selected_slot})**")
                st.dataframe(
                    room_df[["Row", "Seat #", "Student ID", "Course", "Room ID"]],
                    width="stretch",
                    hide_index=True,
                )

                st.markdown("**Visual Checkerboard Seat Grid** *(Empty cells = checkerboard spacing)*")
                room_df = room_df.copy()
                room_df["Cell"] = room_df["Student ID"] + " (" + room_df["Course"] + ")"
                grid_df = room_df.pivot_table(
                    index="Row",
                    columns="Seat #",
                    values="Cell",
                    aggfunc="first",
                    fill_value="—",
                )
                st.dataframe(grid_df, width="stretch")

        if os.path.exists("data/master_seating_chart.xlsx"):
            with open("data/master_seating_chart.xlsx", "rb") as f:
                st.download_button("📥 Download Complete Seating Chart (Excel)", f, file_name="master_seating_chart.xlsx")

# ==============================================================================
# 4. FACULTY HIERARCHY & LEAVES
# ==============================================================================
elif page == "👨‍🏫 Faculty Hierarchy & Leaves":
    st.subheader("👨‍🏫 Faculty Invigilation Roster, Rank Hierarchy & Leave Manager")
    st.markdown(
        "**Duty Hierarchy:** `Assistant Professor` (highest duty load) → `Associate Professor` (moderate load) → `Professor` (lowest duty load)."
    )

    # Interactive Leave Controls
    c1, c2, c3 = st.columns([2, 2, 1])
    fac_options = [f["faculty_id"] for f in faculty_master] if faculty_master else [f"FAC{i:03d}" for i in range(1, 51)]

    with c1:
        fac_to_add = st.selectbox("Mark Faculty on Leave", options=fac_options, key="add_leave_select")
        if st.button("➕ Add to Leave (`leaves.json`)"):
            add_faculty_leave(fac_to_add)
            assign_invigilators()
            st.rerun()

    with c2:
        current_leaves = load_json("data/leaves.json") or []
        fac_to_remove = st.selectbox(
            "Mark Faculty Available / Remove Leave",
            options=current_leaves if current_leaves else ["None"],
            key="rem_leave_select",
        )
        if st.button("✅ Remove from Leave (`leaves.json`)") and fac_to_remove != "None":
            remove_faculty_leave(fac_to_remove)
            assign_invigilators()
            st.rerun()

    with c3:
        st.write("")
        st.write("")
        if st.button("🗑️ Clear All Leaves"):
            clear_faculty_leaves()
            assign_invigilators()
            st.rerun()

    st.info(f"**Active Leave List (`data/leaves.json`):** `{', '.join(current_leaves) if current_leaves else 'None'}`")

    if faculty_sched_data:
        inv_rows = []
        for block in faculty_sched_data:
            for inv in block.get("invigilators", []):
                inv_rows.append(
                    {
                        "Time Slot": block.get("time_slot", ""),
                        "Room": block.get("room_name", ""),
                        "Faculty ID": inv.get("faculty_id", ""),
                        "Faculty Name": inv.get("name", ""),
                        "Designation": inv.get("designation", ""),
                        "Department": inv.get("department", ""),
                        "Duties Assigned": inv.get("duties_assigned", ""),
                    }
                )
        df_inv = pd.DataFrame(inv_rows)
        st.dataframe(df_inv, width="stretch", hide_index=True)

        if "Designation" in df_inv.columns and not df_inv.empty:
            st.markdown("**Duty Count Summary by Designation**")
            rank_summary = (
                df_inv.groupby("Designation", as_index=False)
                .agg(Assignments=("Faculty ID", "count"), Unique_Faculty=("Faculty ID", "nunique"))
            )
            st.dataframe(rank_summary, width="stretch", hide_index=True)

        if os.path.exists("data/faculty_invigilation_schedule.xlsx"):
            with open("data/faculty_invigilation_schedule.xlsx", "rb") as f:
                st.download_button(
                    "📥 Download Faculty Invigilation Schedule (Excel)",
                    f,
                    file_name="faculty_invigilation_schedule.xlsx",
                )
    else:
        st.info("No invigilation schedule generated yet.")

# ==============================================================================
# 5. INSTITUTIONAL RULES
# ==============================================================================
elif page == "📜 Institutional Rules":
    st.subheader("📜 Institutional Rules & Policies")
    rules_path = "data/rules.txt"
    if os.path.exists(rules_path):
        with open(rules_path, "r") as f:
            st.markdown(f.read())
    else:
        st.info("`data/rules.txt` not found.")