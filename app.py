import streamlit as st
import os
import json
import agents
import pandas as pd

st.set_page_config(
    page_title="AllocAI - University Exam & Invigilation Management",
    page_icon="🎓",
    layout="wide"
)

st.title("🎓 AllocAI: Autonomous University Exam & Invigilation Management System")
st.markdown("Hybrid Multi-Agent Architecture powered by **OR-Tools (CP-SAT)**, **True Checkerboard Seating**, and **Local Llama 3.2 (Ollama)**.")

# Sidebar Navigation
page = st.sidebar.selectbox("Navigation", ["💬 Admin Assistant Chat", "📅 Master Exam Schedule", "🪑 Seating Allocation Viewer", "📋 Faculty Invigilation Duty Roster", "📜 Institutional Rules RAG"])

# Helper loader
def load_json(path):
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return None

if page == "💬 Admin Assistant Chat":
    st.header("🤖 Intelligent Admin Assistant")
    st.markdown("Ask questions or issue natural language commands (e.g., *'Faculty 5 is on leave, make a fresh timetable'* or *'Where is STU003 sitting?'*).")

    if "messages" not in st.session_state:
        st.session_state.messages = []

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if user_prompt := st.chat_input("Enter your command or query..."):
        st.session_state.messages.append({"role": "user", "content": user_prompt})
        with st.chat_message("user"):
            st.markdown(user_prompt)

        with st.chat_message("assistant"):
            with st.spinner("AllocAI multi-agent pipeline executing..."):
                # Invoke your ReAct agent directly using agents.agent_executor
                res = agents.agent_executor.invoke({"input": user_prompt})
                response = res.get("output", str(res))
            st.markdown(response)
            st.session_state.messages.append({"role": "assistant", "content": response})

elif page == "📅 Master Exam Schedule":
    st.header("📅 Master Exam Timetable")
    path = "data/exam_schedule.json"
    data = load_json(path)
    
    if data:
        rows = []
        for c_id, details in data.items():
            rows.append({
                "Course ID": c_id,
                "Time Slot": details["time_slot"],
                "Assigned Rooms": ", ".join(details["assigned_rooms"]),
                "Total Students": details["total_students"]
            })
        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True)
        
        if os.path.exists("data/exam_schedule.xlsx"):
            with open("data/exam_schedule.xlsx", "rb") as f:
                st.download_button("📥 Download Master Schedule (Excel)", f, file_name="exam_schedule.xlsx")
    else:
        st.warning("No schedule generated yet. Use the Admin Chat to generate one!")

elif page == "🪑 Seating Allocation Viewer":
    st.header("🪑 Tiered Anti-Collusion Seating Chart")
    path = "data/master_seating_chart.json"
    data = load_json(path)
    
    if data:
        student_query = st.selectbox("Select or Search Student ID", options=list(data.keys()))
        if student_query:
            st.subheader(f"Seating Details for {student_query}")
            st.json(data[student_query])
            
        if os.path.exists("data/master_seating_chart.xlsx"):
            with open("data/master_seating_chart.xlsx", "rb") as f:
                st.download_button("📥 Download Complete Seating Chart (Excel)", f, file_name="master_seating_chart.xlsx")
    else:
        st.warning("Seating chart not generated yet.")

elif page == "📋 Faculty Invigilation Duty Roster":
    st.header("📋 Faculty Invigilation Roster & Leave Status")
    
    leave_path = "data/leaves.json"
    leaves = load_json(leave_path) or []
    st.info(f"🛑 Current Faculty on Leave: {leaves if leaves else 'None'}")

    path = "data/faculty_schedule.json"
    data = load_json(path)
    
    if data:
        rows = []
        for slot_info in data:
            for inv in slot_info["invigilators"]:
                rows.append({
                    "Time Slot": slot_info["time_slot"],
                    "Room": slot_info["room_name"],
                    "Faculty ID": inv["faculty_id"],
                    "Faculty Name": inv["name"],
                    "Department": inv["department"]
                })
        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True)
        
        if os.path.exists("data/faculty_invigilation_schedule.xlsx"):
            with open("data/faculty_invigilation_schedule.xlsx", "rb") as f:
                st.download_button("📥 Download Faculty Schedule (Excel)", f, file_name="faculty_invigilation_schedule.xlsx")
    else:
        st.warning("Faculty schedule not generated yet.")

elif page == "📜 Institutional Rules RAG":
    st.header("📜 Institutional Rules & Guidelines")
    rules_path = "data/rules.txt"
    if os.path.exists(rules_path):
        with open(rules_path, "r") as f:
            st.markdown(f.read())
    else:
        st.warning("rules.txt not found in data/ folder.")