import os
import json
import pandas as pd
from solver_engine import solve_exam_schedule

def assign_invigilators():
    os.makedirs("data", exist_ok=True)
    schedule_path = "data/exam_schedule.json"
    
    if os.path.exists(schedule_path):
        print("📂 Loading saved exam schedule for invigilation...")
        with open(schedule_path, "r") as f:
            schedule = json.load(f)
    else:
        print("🔄 Running Macro-Scheduler...")
        schedule = solve_exam_schedule()

    if not schedule:
        print("❌ Cannot assign invigilators: no valid schedule found.")
        return

    with open("data/faculty.json", "r") as f:
        faculty_list = json.load(f)
    with open("data/rooms.json", "r") as f:
        rooms = {r["room_id"]: r for r in json.load(f)}
    
    # Load faculty leaves if file exists
    leaves = []
    if os.path.exists("data/leaves.json"):
        with open("data/leaves.json", "r") as f:
            leaves = json.load(f)

    # Filter out faculty who are on leave
    active_faculty = [fac for fac in faculty_list if fac["faculty_id"] not in leaves]
    print(f"📋 Active faculty available for duty: {len(active_faculty)} (Filtered {len(leaves)} on leave)")

    faculty_duty_counts = {fac["faculty_id"]: 0 for fac in active_faculty}
    faculty_busy_slots = {fac["faculty_id"]: set() for fac in active_faculty}
    invigilation_assignments = []
    flat_rows = []

    active_slot_rooms = set()
    for c_id, details in schedule.items():
        slot = details["time_slot"]
        for r_id in details["assigned_rooms"]:
            active_slot_rooms.add((slot, r_id))

    sorted_slot_rooms = sorted(list(active_slot_rooms))
    faculty_index = 0

    for slot, r_id in sorted_slot_rooms:
        room_name = rooms[r_id]["name"]
        invigilators_needed = 2 if rooms[r_id]["capacity"] > 100 else 1
        
        assigned_to_room = []
        for _ in range(invigilators_needed):
            attempts = 0
            while attempts < len(active_faculty):
                fac = active_faculty[faculty_index % len(active_faculty)]
                faculty_index += 1
                attempts += 1
                
                f_id = fac["faculty_id"]
                if faculty_duty_counts[f_id] < fac["max_invigilations"] and slot not in faculty_busy_slots[f_id]:
                    faculty_duty_counts[f_id] += 1
                    faculty_busy_slots[f_id].add(slot)
                    assigned_to_room.append({
                        "faculty_id": f_id,
                        "name": fac["name"],
                        "department": fac["department"]
                    })
                    break

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
                "Department": inv["department"],
                "Time Slot": slot,
                "Room": room_name
            })

    with open("data/faculty_schedule.json", "w") as f:
        json.dump(invigilation_assignments, f, indent=4)

    df = pd.DataFrame(flat_rows)
    df.to_excel("data/faculty_invigilation_schedule.xlsx", index=False)
    df.to_csv("data/faculty_invigilation_schedule.csv", index=False)
    print("✅ Success! Saved faculty_schedule.json, .xlsx, and .csv in data/.")

if __name__ == "__main__":
    assign_invigilators()