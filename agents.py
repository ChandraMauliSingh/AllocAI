import os
import re
import json
from langchain_ollama import OllamaLLM
from langchain_classic.agents import AgentExecutor, create_react_agent
from langchain_core.tools import Tool
from langchain_core.prompts import PromptTemplate

from solver_engine import solve_exam_schedule
from seating_engine import generate_roll_number_seating
from invigilation_engine import assign_invigilators

# 1. Initialize Local Ollama LLM
llm = OllamaLLM(model="llama3.2", temperature=0)

# 2. Define Institutional RAG Tool
def query_rules_rag(query: str) -> str:
    """Searches AllocAI institutional exam rules and policies."""
    if not os.path.exists("data/rules.txt"):
        return "Rules file not found."
    with open("data/rules.txt", "r") as f:
        rules_content = f.read()
    return f"Official AllocAI institutional rules:\n{rules_content}"

# 3. Define Solver Tool (Handles dynamic slots & faculty leaves)
# Store the latest user query globally so the tool can always read it directly
CURRENT_USER_QUERY = ""

def trigger_full_pipeline(query: str) -> str:
    """Runs the complete macro-scheduler, seating allocation, and invigilation engine."""
    try:
        os.makedirs("data", exist_ok=True)
        
        # Use the global user query text directly so it never gets lost or corrupted by the LLM
        global CURRENT_USER_QUERY
        q_lower = CURRENT_USER_QUERY.lower()

        leave_path = "data/leaves.json"
        leaves = []
        if os.path.exists(leave_path) and os.path.getsize(leave_path) > 0:
            try:
                with open(leave_path, "r") as f:
                    leaves = json.load(f)
            except json.JSONDecodeError:
                leaves = []

        if "all facult" in q_lower and ("available" in q_lower or "back" in q_lower or "clear" in q_lower):
            leaves = []
        else:
            fac_matches = re.findall(r'(?:fac(?:ulty)?\.?\s*#?)\s*(\d+)', q_lower)
            for num in fac_matches:
                fac_id = f"FAC{int(num):03d}"
                if any(w in q_lower for w in ["leave", "absent", "unavailable", "off"]):
                    if fac_id not in leaves:
                        leaves.append(fac_id)
                    print(f"🛑 Recorded leave for {fac_id}")
                elif any(w in q_lower for w in ["available", "back", "present", "return"]):
                    if fac_id in leaves:
                        leaves.remove(fac_id)
                    print(f"✅ Marked {fac_id} as available")

        leaves = list(set(leaves))
        with open(leave_path, "w") as f:
            json.dump(leaves, f, indent=4)

        # Parse slot count if specified (default 6)
        slots = 6
        slot_match = re.search(r'(?:slots?\s*=?\s*(\d+)|(\d+)\s*slots?)', q_lower)
        if slot_match:
            slots = int(slot_match.group(1) or slot_match.group(2))

        print(f"🤖 Agent triggering Macro-Scheduler (slots={slots}, leaves={leaves})...")
        schedule = solve_exam_schedule(num_slots=slots)
        if not schedule:
            return f"Failed to generate schedule with {slots} slots due to exam clash constraints. Increase slots."

        print("🤖 Agent triggering Micro-Seating Engine...")
        generate_roll_number_seating()

        print("🤖 Agent triggering Invigilation Engine...")
        assign_invigilators()

        return (
            f"Success! Generated schedule with {slots} slots. "
            f"Active Faculty Leaves: {leaves}. "
            f"Timetable Summary: {list(schedule.keys())}"
        )
    except Exception as e:
        return f"Error running pipeline: {str(e)}"    
# 4. Define Student Schedule Lookup Tool
def lookup_student_schedule(student_id: str) -> str:
    """Looks up a specific student's exam room, row, seat number, and time slot."""
    path = "data/master_seating_chart.json"
    if not os.path.exists(path):
        return "Seating chart has not been generated yet. Run Generate_Exam_Schedule first."

    with open(path, "r") as f:
        data = json.load(f)

    # Extract clean ID even if LLM passes extra words
    match = re.search(r'stu\s*0*(\d+)', str(student_id), re.IGNORECASE)
    clean_id = f"STU{int(match.group(1)):03d}" if match else str(student_id).upper().strip()

    if clean_id in data:
        return json.dumps(data[clean_id], indent=2)
    return f"Student ID {clean_id} does not exist in the seating chart."

# 5. Register Tools
tools = [
    Tool(
        name="Generate_Exam_Schedule",
        func=trigger_full_pipeline,
        description="Always use this to generate, remake, or update the exam timetable, seating charts, or faculty leaves. Pass the full user request as Action Input."
    ),
    Tool(
        name="Institutional_Rules_RAG",
        func=query_rules_rag,
        description="Use this when asked about institutional policies, anti-collusion rules, seating constraints, or invigilation limits."
    ),
    Tool(
        name="Lookup_Student_Seating",
        func=lookup_student_schedule,
        description="Use this when asked where a specific student (e.g. STU003) is sitting. Pass the student ID as Action Input."
    )
]

# 6. ReAct Prompt Template
template = """Answer the following questions as best you can. All exam, room, student, and faculty data already exists in the system—never ask the user for subjects or hours.
You have access to the following tools:

{tools}

Use the following format:

Question: the input question you must answer
Thought: you should always think about what to do. If it is just a greeting, skip Action and write Final Answer directly.
Action: the action to take, should be one of [{tool_names}]
Action Input: the input to the action
Observation: the result of the action
... (this Thought/Action/Action Input/Observation can repeat N times)
Thought: I now know the final answer
Final Answer: the final answer to the original input question (report ONLY exact data from Observation, never invent times or subjects)

Begin!

Question: {input}
Thought:{agent_scratchpad}"""

prompt = PromptTemplate.from_template(template)
agent = create_react_agent(llm, tools, prompt)
agent_executor = AgentExecutor(
    agent=agent,
    tools=tools,
    verbose=True,
    handle_parsing_errors=True,
    max_iterations=None
)

if __name__ == "__main__":
    print("🤖 AllocAI Multi-Agent System Initialized with Local Ollama (Llama 3.2).")
    print("Type 'exit' to quit.\n")

    while True:
        user_input = input("Admin Query > ")
        if user_input.lower() in ["exit", "quit"]:
            break
        
        # Save user query globally so the tool has direct access to it
        CURRENT_USER_QUERY = user_input

        response = agent_executor.invoke({"input": user_input})
        print(f"\nAI Agent Response:\n{response['output']}\n" + "-" * 50)