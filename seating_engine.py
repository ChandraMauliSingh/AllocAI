import os
import json
import pandas as pd
from solver_engine import solve_exam_schedule

SCHEDULE_PATH = "data/exam_schedule.json"


def _build_checkerboard_seats(room: dict) -> list[dict]:
    seats = []
    row_caps = room.get("row_capacities")
    if row_caps and isinstance(row_caps, list):
        for r_idx, seat_count in enumerate(row_caps):
            start_offset = r_idx % 2
            for s_idx in range(start_offset, int(seat_count), 2):
                seats.append({"row": r_idx + 1, "seat": s_idx + 1})
    else:
        cap = int(room.get("capacity", 40))
        cols = 10
        rows = max(1, (cap + cols - 1) // cols)
        for r_idx in range(rows):
            seats_in_row = min(cols, cap - r_idx * cols)
            start_offset = r_idx % 2
            for s_idx in range(start_offset, seats_in_row, 2):
                seats.append({"row": r_idx + 1, "seat": s_idx + 1})
    return seats


def _total_checkerboard_capacity(schedule: dict, rooms: dict) -> int:
    total = 0
    for _, details in schedule.items():
        for r_id in details.get("assigned_rooms", []):
            if r_id in rooms:
                total += len(_build_checkerboard_seats(rooms[r_id]))
    return total


def generate_roll_number_seating(initial_slots: int = 6, max_slots: int = 24):
    os.makedirs("data", exist_ok=True)

    with open("data/students.json", "r") as f:
        students_list = json.load(f)
    with open("data/rooms.json", "r") as f:
        rooms = {r["room_id"]: r for r in json.load(f)}

    # Count total enrolled student-course seatings needed
    total_needed_seats = 0
    for stu in students_list:
        total_needed_seats += len(stu.get("enrolled_courses", []))

    num_slots = initial_slots
    schedule = None

    if os.path.exists(SCHEDULE_PATH) and os.path.getsize(SCHEDULE_PATH) > 0:
        with open(SCHEDULE_PATH, "r") as f:
            schedule = json.load(f)

    # Automatically increase slots if checkerboard capacity is insufficient
    while num_slots <= max_slots:
        if not schedule or _total_checkerboard_capacity(schedule, rooms) < total_needed_seats:
            print(f"🔄 Optimizing macro-schedule with {num_slots} slots for checkerboard capacity...")
            candidate = solve_exam_schedule(num_slots=num_slots)
            if candidate:
                schedule = candidate
                with open(SCHEDULE_PATH, "w") as f:
                    json.dump(schedule, f, indent=4)
        if schedule and _total_checkerboard_capacity(schedule, rooms) >= total_needed_seats:
            break
        num_slots += 1

    if not schedule:
        print("❌ Cannot generate seating because schedule is empty.")
        return

    # Group students by (Time Slot, Room ID)
    slot_room_occupants = {}
    used_seats_per_slot_room = {}

    for c_id, details in schedule.items():
        slot = details["time_slot"]
        assigned_rooms = details.get("assigned_rooms", [])
        course_students = [
            stu["student_id"]
            for stu in students_list
            if c_id in stu.get("enrolled_courses", [])
        ]

        slot_room_occupants.setdefault(slot, {})
        used_seats_per_slot_room.setdefault(slot, {})

        # Distribute course students across assigned rooms first
        r_idx = 0
        for stu_id in course_students:
            placed_in_assigned = False
            for attempt in range(len(assigned_rooms)):
                r_id = assigned_rooms[(r_idx + attempt) % len(assigned_rooms)]
                room_cb_seats = _build_checkerboard_seats(rooms[r_id])
                used_count = used_seats_per_slot_room[slot].get(r_id, 0)
                if used_count < len(room_cb_seats):
                    slot_room_occupants[slot].setdefault(r_id, []).append({
                        "student_id": stu_id,
                        "course_id": c_id
                    })
                    used_seats_per_slot_room[slot][r_id] = used_count + 1
                    r_idx = (r_idx + attempt + 1) % max(1, len(assigned_rooms))
                    placed_in_assigned = True
                    break

            # Spillover into any remaining room in the same slot if assigned rooms fill up
            if not placed_in_assigned:
                for fallback_r_id, fallback_room in rooms.items():
                    room_cb_seats = _build_checkerboard_seats(fallback_room)
                    used_count = used_seats_per_slot_room[slot].get(fallback_r_id, 0)
                    if used_count < len(room_cb_seats):
                        slot_room_occupants[slot].setdefault(fallback_r_id, []).append({
                            "student_id": stu_id,
                            "course_id": c_id
                        })
                        used_seats_per_slot_room[slot][fallback_r_id] = used_count + 1
                        break

    master_seating_allocation = {}
    flat_rows = []

    print("\n🛡️ Applying True Checkerboard Anti-Collusion Seating Algorithm...")

    for slot, room_dict in slot_room_occupants.items():
        for r_id, occupants in room_dict.items():
            room = rooms[r_id]
            room_seats = _build_checkerboard_seats(room)

            # Interleave students from different courses round-robin style
            course_buckets = {}
            for occ in occupants:
                c = occ["course_id"]
                course_buckets.setdefault(c, []).append(occ["student_id"])

            bucket_keys = list(course_buckets.keys())
            buckets = [course_buckets[k] for k in bucket_keys]
            max_len = max((len(b) for b in buckets), default=0)

            interleaved_students = []
            for i in range(max_len):
                for b_idx, bucket in enumerate(buckets):
                    if i < len(bucket):
                        interleaved_students.append({
                            "student_id": bucket[i],
                            "course_id": bucket_keys[b_idx]
                        })

            for seat_idx, occupant in enumerate(interleaved_students):
                if seat_idx >= len(room_seats):
                    break

                seat_info = room_seats[seat_idx]
                stu_id = occupant["student_id"]
                c_id = occupant["course_id"]

                master_seating_allocation.setdefault(stu_id, {})[c_id] = {
                    "time_slot": slot,
                    "room_id": r_id,
                    "room_name": room["name"],
                    "row": seat_info["row"],
                    "seat_number": seat_info["seat"]
                }

                flat_rows.append({
                    "Student ID": stu_id,
                    "Course ID": c_id,
                    "Time Slot": slot,
                    "Room": room["name"],
                    "Row": seat_info["row"],
                    "Seat Number": seat_info["seat"]
                })

    with open("data/master_seating_chart.json", "w") as f:
        json.dump(master_seating_allocation, f, indent=4)

    df = pd.DataFrame(flat_rows)
    df.to_excel("data/master_seating_chart.xlsx", index=False)
    df.to_csv("data/master_seating_chart.csv", index=False)

    print(f"✅ Checkerboard seating complete ({len(master_seating_allocation)} unique students, {len(flat_rows)} total exam seats).")


if __name__ == "__main__":
    generate_roll_number_seating()