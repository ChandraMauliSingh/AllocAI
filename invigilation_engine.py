import os
import json
import pandas as pd
from solver_engine import solve_exam_schedule

LEAVES_PATH = "data/leaves.json"
SCHEDULE_PATH = "data/exam_schedule.json"


def _load_leaves() -> list[str]:
    os.makedirs("data", exist_ok=True)
    if not os.path.exists(LEAVES_PATH) or os.path.getsize(LEAVES_PATH) == 0:
        return []
    try:
        with open(LEAVES_PATH, "r") as f:
            data = json.load(f)
            return list(dict.fromkeys([str(x).upper().strip() for x in data]))
    except json.JSONDecodeError:
        return []


def _save_leaves(leaves: list[str]) -> None:
    os.makedirs("data", exist_ok=True)
    cleaned = list(dict.fromkeys([str(x).upper().strip() for x in leaves]))
    with open(LEAVES_PATH, "w") as f:
        json.dump(cleaned, f, indent=4)


def normalize_fac_id(fac_input: str) -> str:
    digits = "".join(ch for ch in str(fac_input) if ch.isdigit())
    if digits:
        return f"FAC{int(digits):03d}"
    return str(fac_input).upper().strip()


def add_faculty_leave(fac_input: str) -> list[str]:
    fac_id = normalize_fac_id(fac_input)
    leaves = _load_leaves()
    if fac_id not in leaves:
        leaves.append(fac_id)
        _save_leaves(leaves)
    return leaves


def remove_faculty_leave(fac_input: str) -> list[str]:
    fac_id = normalize_fac_id(fac_input)
    leaves = _load_leaves()
    if fac_id in leaves:
        leaves.remove(fac_id)
        _save_leaves(leaves)
    return leaves


def clear_faculty_leaves() -> list[str]:
    _save_leaves([])
    return []


def _resolve_designation(fac: dict, index: int = 0, total: int = 1) -> str:
    explicit = str(fac.get("designation") or fac.get("rank") or fac.get("role") or "").strip()
    if explicit:
        low = explicit.lower()
        if "assistant" in low or "asst" in low:
            return "Assistant Professor"
        if "associate" in low or "assoc" in low:
            return "Associate Professor"
        if "professor" in low or "prof" in low:
            return "Professor"
        return explicit

    name_low = str(fac.get("name", "")).lower()
    if "assistant" in name_low or "asst" in name_low:
        return "Assistant Professor"
    if "associate" in name_low or "assoc" in name_low:
        return "Associate Professor"

    # Deterministic hierarchy fallback when faculty.json only lists generic names/caps:
    # Professors get fewer duties than Associate & Assistant Professors.
    if total <= 1:
        return "Assistant Professor"
    ratio = index / total
    if ratio < 0.5:
        return "Assistant Professor"
    elif ratio < 0.8:
        return "Associate Professor"
    else:
        return "Professor"


def _rank_duty_cap(fac: dict, designation: str) -> int:
    base_max = int(fac.get("max_invigilations", 3))
    desig_low = designation.lower()

    if "assistant" in desig_low or "asst" in desig_low:
        return max(1, base_max)
    if "associate" in desig_low or "assoc" in desig_low:
        return max(1, base_max - 1)
    if "professor" in desig_low or "prof" in desig_low:
        return max(1, base_max - 2)
    return max(1, base_max)


def _rank_priority_order(designation: str) -> int:
    desig_low = designation.lower()
    if "assistant" in desig_low or "asst" in desig_low:
        return 0
    if "associate" in desig_low or "assoc" in desig_low:
        return 1
    if "professor" in desig_low or "prof" in desig_low:
        return 2
    return 1


def assign_invigilators():
    os.makedirs("data", exist_ok=True)

    if os.path.exists(SCHEDULE_PATH) and os.path.getsize(SCHEDULE_PATH) > 0:
        with open(SCHEDULE_PATH, "r") as f:
            schedule = json.load(f)
    else:
        schedule = solve_exam_schedule()

    if not schedule:
        print("❌ Cannot assign invigilators: no valid schedule found.")
        return

    with open("data/faculty.json", "r") as f:
        faculty_list = json.load(f)
    with open("data/rooms.json", "r") as f:
        rooms = {r["room_id"]: r for r in json.load(f)}

    leaves = _load_leaves()
    total_fac = len(faculty_list)
    active_faculty = []

    for idx, fac in enumerate(faculty_list):
        if fac["faculty_id"] not in leaves:
            fac_copy = dict(fac)
            resolved_desig = _resolve_designation(fac_copy, index=idx, total=total_fac)
            fac_copy["_designation"] = resolved_desig
            fac_copy["_duty_cap"] = _rank_duty_cap(fac_copy, resolved_desig)
            active_faculty.append(fac_copy)

    # Sort so Assistant Professors are picked before Associates, and Professors last
    active_faculty = sorted(
        active_faculty,
        key=lambda fac: (_rank_priority_order(fac["_designation"]), fac["faculty_id"])
    )

    if not active_faculty:
        print("❌ No active faculty available after applying leaves!")
        return

    duty_caps = {fac["faculty_id"]: fac["_duty_cap"] for fac in active_faculty}
    faculty_duty_counts = {fac["faculty_id"]: 0 for fac in active_faculty}
    faculty_busy_slots = {fac["faculty_id"]: set() for fac in active_faculty}

    invigilation_assignments = []
    flat_rows = []

    active_slot_rooms = set()
    for _, details in schedule.items():
        slot = details["time_slot"]
        for r_id in details["assigned_rooms"]:
            active_slot_rooms.add((slot, r_id))

    sorted_slot_rooms = sorted(list(active_slot_rooms))
    cursor = 0

    for slot, r_id in sorted_slot_rooms:
        room_info = rooms[r_id]
        room_name = room_info["name"]
        invigilators_needed = 2 if room_info["capacity"] > 100 else 1

        assigned_to_room = []
        for _ in range(invigilators_needed):
            picked = None

            # Pass 1: Strict hierarchy cap + no slot clash
            for offset in range(len(active_faculty)):
                fac = active_faculty[(cursor + offset) % len(active_faculty)]
                f_id = fac["faculty_id"]
                if faculty_duty_counts[f_id] < duty_caps[f_id] and slot not in faculty_busy_slots[f_id]:
                    picked = fac
                    cursor = (cursor + offset + 1) % len(active_faculty)
                    break

            # Pass 2: Fallback if all caps reached (still avoids same-slot clash)
            if not picked:
                for offset in range(len(active_faculty)):
                    fac = active_faculty[(cursor + offset) % len(active_faculty)]
                    f_id = fac["faculty_id"]
                    if slot not in faculty_busy_slots[f_id]:
                        picked = fac
                        cursor = (cursor + offset + 1) % len(active_faculty)
                        break

            if picked:
                f_id = picked["faculty_id"]
                faculty_duty_counts[f_id] += 1
                faculty_busy_slots[f_id].add(slot)
                assigned_to_room.append({
                    "faculty_id": f_id,
                    "name": picked["name"],
                    "designation": picked["_designation"],
                    "department": picked["department"],
                    "duties_assigned": faculty_duty_counts[f_id],
                    "duty_cap": duty_caps[f_id]
                })

        invigilation_assignments.append({
            "time_slot": slot,
            "room_id": r_id,
            "room_name": room_name,
            "invigilators": assigned_to_room
        })

        for inv in assigned_to_room:
            flat_rows.append({
                "Faculty ID": inv["faculty_id"],
                "Faculty Name": inv["name"],
                "Designation": inv["designation"],
                "Department": inv["department"],
                "Time Slot": slot,
                "Room": room_name,
                "Total Duties": inv["duties_assigned"]
            })

    with open("data/faculty_schedule.json", "w") as f:
        json.dump(invigilation_assignments, f, indent=4)

    df = pd.DataFrame(flat_rows)
    df.to_excel("data/faculty_invigilation_schedule.xlsx", index=False)
    df.to_csv("data/faculty_invigilation_schedule.csv", index=False)
    print("✅ Faculty invigilation generated with rank hierarchy & leave filtering.")


if __name__ == "__main__":
    assign_invigilators()