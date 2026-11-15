import json
import os
import pandas as pd
from ortools.sat.python import cp_model

os.makedirs("data", exist_ok=True)

def load_data():
    with open("data/courses.json", "r") as f:
        courses = json.load(f)
    with open("data/students.json", "r") as f:
        students = json.load(f)
    with open("data/rooms.json", "r") as f:
        rooms = json.load(f)
    with open("data/faculty.json", "r") as f:
        faculty = json.load(f)
    return courses, students, rooms, faculty

def solve_exam_schedule(num_slots=6):
    courses, students, rooms, faculty = load_data()
    model = cp_model.CpModel()
    
    course_ids = [c["course_id"] for c in courses]
    room_ids = [r["room_id"] for r in rooms]
    
    # 1. Variables: slot[c] = time slot assigned to course c (0 to num_slots-1)
    slot = {c["course_id"]: model.NewIntVar(0, num_slots - 1, f"slot_{c['course_id']}") for c in courses}
    
    # 2. Variables: use_room[c, r] = boolean, true if course c uses room r
    use_room = {}
    for c in courses:
        for r in rooms:
            use_room[(c["course_id"], r["room_id"])] = model.NewBoolVar(f"use_{c['course_id']}_{r['room_id']}")
            
    # Constraint 1: Total capacity of all rooms assigned to course c must >= course student count
    for c in courses:
        c_id = c["course_id"]
        c_count = c["students_count"]
        model.Add(
            sum(use_room[(c_id, r["room_id"])] * r["capacity"] for r in rooms) >= c_count
        )

    # Constraint 2: A room can be used by AT MOST ONE course per time slot
    for r in rooms:
        r_id = r["room_id"]
        for t in range(num_slots):
            course_at_slot_t = []
            for c in courses:
                c_id = c["course_id"]
                is_at_t = model.NewBoolVar(f"c_{c_id}_at_slot_{t}_in_{r_id}")
                model.Add(slot[c_id] == t).OnlyEnforceIf(is_at_t)
                model.Add(slot[c_id] != t).OnlyEnforceIf(is_at_t.Not())
                
                c_uses_r_and_t = model.NewBoolVar(f"use_{c_id}_{r_id}_at_{t}")
                model.AddBoolAnd([use_room[(c_id, r_id)], is_at_t]).OnlyEnforceIf(c_uses_r_and_t)
                model.AddBoolOr([use_room[(c_id, r_id)].Not(), is_at_t.Not()]).OnlyEnforceIf(c_uses_r_and_t.Not())
                
                course_at_slot_t.append(c_uses_r_and_t)
            
            model.Add(sum(course_at_slot_t) <= 1)

    # Constraint 3: Students cannot have two exams in the same time slot
    for s in students:
        enrolled = s["enrolled_courses"]
        for i in range(len(enrolled)):
            for j in range(i + 1, len(enrolled)):
                c1, c2 = enrolled[i], enrolled[j]
                model.Add(slot[c1] != slot[c2])

    # Solve the model
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 10.0 # Time limit for solver
    status = solver.Solve(model)
    
    schedule = {}
    if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
        for c in courses:
            c_id = c["course_id"]
            s_val = solver.Value(slot[c_id])
            assigned_rooms = [r["room_id"] for r in rooms if solver.Value(use_room[(c_id, r["room_id"])]) == 1]
            schedule[c_id] = {
                "time_slot": f"Slot {s_val + 1}",
                "assigned_rooms": assigned_rooms,
                "total_students": c["students_count"]
            }
        print("✅ OR-Tools Solver successfully generated a multi-room clash-free timetable!")
        
        # --- EXPORT TO JSON, CSV, AND EXCEL ---
        with open("data/exam_schedule.json", "w") as f:
            json.dump(schedule, f, indent=4)
            
        flat_rows = []
        for c_id, details in schedule.items():
            flat_rows.append({
                "Course ID": c_id,
                "Time Slot": details["time_slot"],
                "Assigned Rooms": ", ".join(details["assigned_rooms"]),
                "Total Students": details["total_students"]
            })
            
        df = pd.DataFrame(flat_rows)
        df.to_csv("data/exam_schedule.csv", index=False)
        df.to_excel("data/exam_schedule.xlsx", index=False)
        
        print("📁 Master timetable files saved successfully:")
        print("   - data/exam_schedule.json")
        print("   - data/exam_schedule.csv")
        print("   - data/exam_schedule.xlsx")
        
        return schedule
    else:
        print("❌ No feasible schedule found with given constraints.")
        return None

if __name__ == "__main__":
    solve_exam_schedule()