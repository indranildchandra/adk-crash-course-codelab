from config import MODEL, SEARCH_TOOLS
from google.adk.agents import Agent, SequentialAgent
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())

# --- Agent Definitions for our Specialist Team (Refactored for Sequential Workflow) ---
day_trip_agent = Agent(
    name="day_trip_agent",
    model=MODEL,
    description="Agent specialized in generating spontaneous full-day itineraries based on mood, interests, and budget.",
    instruction="""
    You are the "Spontaneous Day Trip" Generator  - a specialized AI assistant that creates engaging full-day itineraries.

    Your Mission:
    Transform a simple mood or interest into a complete day-trip adventure with real-time details, while respecting a budget.

    Guidelines:
    1. **Budget-Aware**: Pay close attention to budget hints like 'cheap', 'affordable', or 'splurge'. Use Google Search to find activities (free museums, parks, paid attractions) that match the user's budget.
    2. **Full-Day Structure**: Create morning, afternoon, and evening activities.
    3. **Real-Time Focus**: Search for current operating hours and special events.
    4. **Mood Matching**: Align suggestions with the requested mood (adventurous, relaxing, artsy, etc.).

    RETURN itinerary in MARKDOWN FORMAT with clear time blocks and specific venue names.
    """,
    tools=SEARCH_TOOLS
)

#  CHANGE 1: We tell foodie_agent to save its output to the shared state.
# Note the new `output_key` and the more specific instruction.
foodie_agent = Agent(
    name="foodie_agent",
    model=MODEL,
    tools=SEARCH_TOOLS,
    instruction="""You are an expert food critic. Your goal is to find the best restaurant based on a user's request.

    When you recommend a place, you must output *only* the name of the establishment and nothing else.
    For example, if the best sushi is at 'Jin Sho', you should output only: Jin Sho
    """,
    output_key="destination"  # ADK will save the agent's final response to state['destination']
)

#  CHANGE 2: We tell transportation_agent to read from the shared state.
# The `{destination}` placeholder is automatically filled by the ADK from the state.
transportation_agent = Agent(
    name="transportation_agent",
    model=MODEL,
    tools=SEARCH_TOOLS,
    instruction="""You are a navigation assistant. Given a destination, provide clear directions.
    The user wants to go to: {destination}.

    Analyze the user's full original query to find their starting point.
    Then, provide clear directions from that starting point to {destination}.
    """,
)

#  CHANGE 3: Define the SequentialAgent to manage the workflow.
# This agent will run foodie_agent, then transportation_agent, in that exact order.
find_and_navigate_agent = SequentialAgent(
    name="find_and_navigate_agent",
    sub_agents=[foodie_agent, transportation_agent],
    description="A workflow that first finds a location and then provides directions to it."
)

weekend_guide_agent = Agent(
    name="weekend_guide_agent",
    model=MODEL,
    tools=SEARCH_TOOLS,
    instruction="You are a local events guide. Your task is to find interesting events, concerts, festivals, and activities happening on a specific weekend."
)


day_trip_workflow = SequentialAgent(
    name="day_trip_workflow",
    sub_agents=[day_trip_agent],
    description="A workflow that plans a full day itinerary."
)

weekend_guide_workflow = SequentialAgent(
    name="weekend_guide_workflow",
    sub_agents=[weekend_guide_agent],
    description="A workflow that finds weekend events."
)


# --- The Brain of the Operation: The Router Agent ---
router_agent = Agent(
    name="router_agent",
    model=MODEL,
    instruction="""
You are a master coordinator for a team of specialist AI travel agents.
Your primary job is to analyze the user's request and delegate it to the single most appropriate agent or workflow from your team.
You must invoke the chosen agent and return its complete, final response to the user.

--- Agent Capabilities ---
- `find_and_navigate_agent`: Finds a specific place and provides directions to it.
- `day_trip_workflow`: Plans a full-day itinerary for any general request.
- `weekend_guide_workflow`: Finds time-based events (concerts, festivals) happening on a specific weekend.

--- Examples ---
- User: "Find the best ramen in Sunnyvale and get me directions." -> `find_and_navigate_agent`
- User: "What are some fun things I can do today?" -> `day_trip_workflow`
- User: "What concerts are happening this weekend in SF?" -> `weekend_guide_workflow`

Now, analyze the user's request and delegate to the correct agent.
""",
    sub_agents=[find_and_navigate_agent, day_trip_workflow, weekend_guide_workflow],
)


print(" Agent team assembled with a SequentialAgent workflow!")
root_agent = router_agent