import json

import pandas as pd

from solver_engine import solve_exam_schedule



def generate_roll_number_seating():

    print("🔄 Running Macro-Scheduler...")

    schedule = solve_exam_schedule(num_slots=6)

    if not schedule:

        print("❌ Cannot generate seating because schedule is empty.")

        return



    with open("data/courses.json", "r") as f:

        courses = {c["course_id"]: c for c in json.load(f)}

    with open("data/students.json", "r") as f:

        students_list = json.load(f)

    with open("data/rooms.json", "r") as f:

        rooms = {r["room_id"]: r for r in json.load(f)}



    # Group students by (Time Slot, Room ID)

    slot_room_occupants = {}



    for c_id, details in schedule.items():

        slot = details["time_slot"]

        for r_id in details["assigned_rooms"]:

            if slot not in slot_room_occupants:

                slot_room_occupants[slot] = {}

            if r_id not in slot_room_occupants[slot]:

                slot_room_occupants[slot][r_id] = []

           

            for stu in students_list:

                if c_id in stu["enrolled_courses"]:

                    slot_room_occupants[slot][r_id].append({

                        "student_id": stu["student_id"],

                        "course_id": c_id

                    })



    master_seating_allocation = {}

    flat_rows = []



    print("\n🛡️ Applying True Checkerboard Anti-Collusion Seating Algorithm...")



    for slot, room_dict in slot_room_occupants.items():

        for r_id, occupants in room_dict.items():

            room = rooms[r_id]

           

            # BUILD CHECKERBOARD SEAT POOL (Staggered rows)

            room_seats = []

            for r_idx, seat_count in enumerate(room["row_capacities"]):

                # Odd rows start at seat index 0 (Seat 1), Even rows start at seat index 1 (Seat 2)

                start_offset = r_idx % 2

                for s_idx in range(start_offset, seat_count, 2):

                    room_seats.append({

                        "row": r_idx + 1,

                        "seat": s_idx + 1

                    })



            # Interleave students from different courses round-robin style

            course_buckets = {}

            for occ in occupants:

                c = occ["course_id"]

                if c not in course_buckets:

                    course_buckets[c] = []

                course_buckets[c].append(occ["student_id"])



            interleaved_students = []

            buckets = list(course_buckets.values())

            max_len = max(len(b) for b in buckets) if buckets else 0

           

            for i in range(max_len):

                for bucket in buckets:

                    if i < len(bucket):

                        interleaved_students.append({

                            "student_id": bucket[i],

                            "course_id": list(course_buckets.keys())[buckets.index(bucket)]

                        })



            # Assign to checkerboard seats sequentially without vertical collisions

            for seat_idx, occupant in enumerate(interleaved_students):

                if seat_idx >= len(room_seats):

                    break # Room capacity reached

               

                seat_info = room_seats[seat_idx]

                stu_id = occupant["student_id"]

                c_id = occupant["course_id"]



                if stu_id not in master_seating_allocation:

                    master_seating_allocation[stu_id] = {}



                master_seating_allocation[stu_id][c_id] = {

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



    # Save outputs

    with open("data/master_seating_chart.json", "w") as f:

        json.dump(master_seating_allocation, f, indent=4)



    df = pd.DataFrame(flat_rows)

    df.to_excel("data/master_seating_chart.xlsx", index=False)

    df.to_csv("data/master_seating_chart.csv", index=False)



    print("✅ Success! Checkerboard seating charts regenerated.")



if __name__ == "__main__":

    generate_roll_number_seating()