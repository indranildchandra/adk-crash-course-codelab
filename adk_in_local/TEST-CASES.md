# Manual Test Cases — ADK Multi-Agent Travel Planner

Use these test cases to manually verify each agent via the ADK web UI at [http://localhost:8080](http://localhost:8080).

**How to run:**

1. Start the stack: `./run.sh`
2. Open [http://localhost:8080](http://localhost:8080)
3. Select the agent from the dropdown
4. Paste the prompt and observe the response
5. Use the pass/fail criteria to evaluate correctness

---

## Master Orchestrator (`master_orchestrator`)

The master orchestrator routes each request to the most appropriate specialist. These tests verify both routing accuracy and end-to-end response quality.

### TC-M-01 — Route to day trip planner
**Prompt:**
```text
Plan a fun and artsy day out near San Francisco. Keep it affordable.
```
**Expected behaviour:** Routes to `planner_agent`. Response should include multiple activities, venue names with coordinates, and stay within a moderate budget tone.

---

### TC-M-02 — Route to foodie agent
**Prompt:**
```
I'm in Palo Alto and I'm craving the best ramen in town. Where should I go?
```
**Expected behaviour:** Routes to `foodie_agent`. Response should name a specific restaurant with a clear recommendation.

---

### TC-M-03 — Route to navigation agent
**Prompt:**
```
How do I get from Union Square in San Francisco to the Golden Gate Bridge?
```
**Expected behaviour:** Routes to `transportation_agent` or `find_and_navigate_agent`. Response should provide step-by-step directions.

---

### TC-M-04 — Route to budget planner
**Prompt:**
```
I have a $80 budget. Plan me a day out in Sunnyvale with activities and a meal.
```
**Expected behaviour:** Routes to `BudgetAwarePlannerAgent`. Response should extract the $80 budget, find activities and a restaurant, and stay within the limit.

---

### TC-M-05 — Route to trip architect (multi-stop)
**Prompt:**
```
Build me a detailed trip itinerary around Sunnyvale — I want a museum, lunch, and confirm everything is reachable within 30 minutes of each other.
```
**Expected behaviour:** Routes to `TripArchitectAgent`. Response should call specialist sub-agents for location scouting and logistics validation before assembling the final itinerary.

---

### TC-M-06 — Route to memory agent (multi-turn)
**Prompt (turn 1):**
```
I love contemporary art and hate crowded places. Remember that about me.
```
**Prompt (turn 2, same session):**
```
Now plan me a weekend activity based on my preferences.
```
**Expected behaviour:** Routes to `MemoryCoordinatorAgent`. Turn 2 should reference the preferences stated in turn 1 without being told again.

---

### TC-M-07 — Route to MCP trip planner (requires toolbox running)
**Prompt:**
```
Find me top-rated things to do in Paris.
```
**Expected behaviour:** Routes to `trip_planner_agent`. Response should query the database and return destination results from the SQLite backend.

---

## Single Agent (`planner_agent`)

### TC-A-01 — Day trip with mood
**Prompt:**
```
Plan a relaxing and nature-focused day trip near Sunnyvale, CA. Keep it affordable!
```
**Expected behaviour:** 2–3 plan options, each with activity names, coordinates (lat/lng), and brief descriptions. Budget should feel moderate, not luxury.

---

### TC-A-02 — Romantic outing
**Prompt:**
```
Suggest a romantic evening plan for a couple in San Jose, CA.
```
**Expected behaviour:** Plans tailored to a couple — dinner + activity combination, moderate budget, venue names with location details.

---

## Sequential Agent (`find_and_navigate_agent`)

### TC-B1-01 — Find and navigate to a restaurant
**Prompt:**
```
Find me the best sushi place in Sunnyvale and tell me how to get there from downtown Mountain View.
```
**Expected behaviour:** First sub-agent names a specific sushi restaurant. Second sub-agent provides directions from Mountain View to that restaurant. Both steps visible in the response.

---

### TC-B1-02 — Find and navigate to an activity
**Prompt:**
```
Find a good museum near San Jose and give me directions from Palo Alto.
```
**Expected behaviour:** Museum name returned first, followed by clear step-by-step directions from Palo Alto.

---

## Parallel Agent (`parallel_planner_agent`)

### TC-B2-01 — Full parallel search
**Prompt:**
```
I'm in San Francisco this weekend. Find me a museum, a concert, and a great restaurant — all in one go.
```
**Expected behaviour:** All three results (museum, concert, restaurant) returned together in a bulleted summary. Response should feel like a combined plan, not three separate answers.

---

### TC-B2-02 — City-specific parallel search
**Prompt:**
```
Plan my Saturday in Los Angeles — best museum, any live music, and top-rated dinner spot.
```
**Expected behaviour:** Three results synthesised into a single cohesive response for LA. Each item should be named specifically.

---

## Loop / Iterative Agent (`iterative_planner_agent`)

### TC-B3-01 — Plan with travel constraint
**Prompt:**
```
Plan an activity and restaurant for a day in Sunnyvale. Everything must be within 10 minutes of each other.
```
**Expected behaviour:** Agent should propose a plan, critique it against the travel time constraint, and refine if needed. Final response should satisfy the constraint or explicitly state it does.

---

### TC-B3-02 — Tight constraint forces refinement
**Prompt:**
```
Suggest a museum and lunch spot in San Jose. The two places must be within 5 minutes walking distance.
```
**Expected behaviour:** Multiple refinement rounds visible (or implied). Final answer should include two places that are genuinely close together.

---

## Budget-Aware Planner (`BudgetAwarePlannerAgent`)

### TC-C-01 — Valid budget
**Prompt:**
```
I have $120 to spend. Plan me a day in Sunnyvale with an activity and lunch.
```
**Expected behaviour:** Agent extracts $120 budget, finds an activity and restaurant, estimates costs, and checks they fit within the budget. Final plan includes cost breakdown.

---

### TC-C-02 — Invalid / missing budget
**Prompt:**
```
Plan me a day out in Sunnyvale.
```
**Expected behaviour:** Agent should politely ask for or inform the user that a valid budget is required to proceed (FailureAgent path).

---

## Routing Agent (`find_and_navigate_agent` via `d_routing_agent`)

### TC-D-01 — Food query routes to foodie
**Prompt:**
```
What's the best brunch place in Menlo Park?
```
**Expected behaviour:** Router identifies this as a food query and delegates to `foodie_agent`. A specific restaurant recommendation is returned.

---

### TC-D-02 — Navigation query routes correctly
**Prompt:**
```
How do I get from San Jose Airport to Stanford University?
```
**Expected behaviour:** Router identifies this as a navigation query and delegates to `transportation_agent`. Clear directions are returned.

---

## Trip Architect — Agents as Tools (`TripArchitectAgent`)

### TC-E-01 — Multi-stop itinerary
**Prompt:**
```
I want to visit a museum and have lunch near Sunnyvale. Make sure both places are open today and not too far apart.
```
**Expected behaviour:** `LocationScoutAgent` is called as a tool to find locations. `LogisticsValidatorAgent` is called to validate travel time / opening hours. Final response assembles a validated itinerary.

---

### TC-E-02 — Logistics validation focus
**Prompt:**
```
Is the Computer History Museum in Mountain View open on Sundays? And how far is it from downtown Sunnyvale?
```
**Expected behaviour:** `LogisticsValidatorAgent` is invoked. Response should include opening hours and travel time/distance.

---

## Memory Agent (`MemoryCoordinatorAgent`)

### TC-F-01 — Preference storage and recall
**Prompt (turn 1):**
```
I love hiking and dislike touristy spots. I'm vegetarian. Remember this.
```
**Prompt (turn 2, same session):**
```
Suggest a Saturday plan for me.
```
**Expected behaviour:** Turn 2 response should recommend hiking or nature activities (not tourist traps) and vegetarian-friendly dining — without being told the preferences again.

---

### TC-F-02 — Preference override
**Prompt (turn 1):**
```
My favourite cuisine is Italian.
```
**Prompt (turn 2):**
```
Actually, I've changed my mind — I now prefer Japanese food. Update that.
```
**Prompt (turn 3):**
```
Recommend a restaurant for me based on my preference.
```
**Expected behaviour:** Turn 3 should recommend a Japanese restaurant, not Italian — showing the memory was correctly updated.

---

## Ollama / Local Model Tests (`tc_ol_planner`)

> **Run automatically** when `MODEL_PROVIDER=ollama` is set in `model.config`.
> Use `--filter TC-OL` to run manually regardless of provider.

These tests use `tc_ol_planner` — a lightweight agent created inline by the test runner with no search tools and a concise instruction. This avoids DDG search loops that make tests non-deterministic on small local models. Each test requires a single LLM call (~50–80 s on gemma4:e2b).

### TC-OL-01 — Simple activity suggestion
**Prompt:**
```
Name one fun activity or attraction in San Francisco.
```
**Expected behaviour:** Response mentions at least one activity, place, or neighbourhood in or near San Francisco. Any coherent suggestion with a location name passes. The number of suggestions does not matter.

---

### TC-OL-02 — Food recommendation
**Prompt:**
```
What type of cuisine or food is popular in the San Francisco Bay Area?
```
**Expected behaviour:** Response mentions any food, cuisine type, or dish. No specific restaurant or location required — any coherent food suggestion passes.

---

### TC-OL-03 — Local area knowledge
**Prompt:**
```
Name one popular neighbourhood or area to visit in the San Francisco Bay Area.
```
**Expected behaviour:** Response mentions at least one neighbourhood, city, or area in the Bay Area. Any named location passes. The number of suggestions does not matter.

---

### TC-OL-04 — Budget-aware suggestion
**Prompt:**
```
Suggest one free or low-cost outdoor activity near Sunnyvale, California.
```
**Expected behaviour:** Response mentions at least one activity, park, or thing to do in or near Sunnyvale. Any named suggestion passes. The number of suggestions does not matter.

---

### TC-OL-05 — Outdoor activity suggestion
**Prompt:**
```
Name one outdoor park or trail near San Jose, California.
```
**Expected behaviour:** Response mentions at least one outdoor activity, park, trail, or nature area near San Jose. Any coherent outdoor suggestion with a name passes. The number of suggestions does not matter.

---

## MCP Trip Planner (`trip_planner_agent`)
> Requires MCP Toolbox server running on port 7001 and `setup_trip_database.py` to have been run.

### TC-G-01 — Find by destination type
**Prompt:**
```
Find me all museums in Paris.
```
**Expected behaviour:** Agent calls `find_destinations_by_type` tool with `city=Paris` and `type=Museum`. Returns a list of matching destinations from the database with names, types, and ratings.

---

### TC-G-02 — Find top-rated in city
**Prompt:**
```
What are the top-rated things to do in Rome?
```
**Expected behaviour:** Agent calls `find_top_rated_in_city` tool with `city=Rome`. Returns up to 5 highest-rated destinations ordered by rating.

---

### TC-G-03 — Find affordable options
**Prompt:**
```
What are some cheap things to do in Barcelona? My budget is $20 per activity.
```
**Expected behaviour:** Agent calls `find_affordable_options` with `city=Barcelona` and `max_cost=20`. Returns destinations where `average_cost <= 20`.
