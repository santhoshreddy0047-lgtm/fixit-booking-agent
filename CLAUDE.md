# FixIt Booking Agent - Project Instructions

## 1. Project Overview

Build a beginner-friendly AI booking agent for FixIt Home Services, a fictional
home repair company operating in Pune, India.

Customers should be able to use natural language to:
- Request a price quote.
- Book a home repair visit.
- Check available appointment slots.
- Cancel an existing booking.
- Ask about supported services.

The agent must follow all company policies and never invent prices, availability,
customer details, or booking information.

## 2. Technology Stack

- Python 3.12
- OpenAI Agents SDK
- Pydantic
- FastAPI
- Uvicorn
- Streamlit
- python-dotenv
- JSON files for supplied data and booking storage

Use the OpenAI model specified in the assignment: gpt-4.1-mini.

## 3. Required Folder Structure

fixit-agent/
    .env
    .gitignore
    CLAUDE.md
    README.md
    requirements.txt
    tools.py
    agent.py
    api.py
    app.py
    bookings.json
    data/
        services.json
        service_areas.json
        slots.json
        policies.md

Do not create unnecessary files or folders unless required.

## 4. Data Rules

The following files are supplied by the instructor:
- data/services.json
- data/service_areas.json
- data/slots.json
- data/policies.md

Read and use these files as supplied.
Never modify their contents.
Never invent replacement service data, prices, service areas, or slot availability.

Store new bookings in bookings.json.
Create bookings.json automatically if it does not exist.
Keep bookings.json out of Git.

## 5. Company Rules

Today's fixed date is Monday, 2 November 2026.

Bookings are allowed only from 2 November to 8 November 2026.

Time slots:
- Morning: 9 AM to 12 PM
- Afternoon: 12 PM to 3 PM
- Evening: 3 PM to 6 PM

Electricians do not work on Sundays.

Required booking information:
- Customer name
- Valid 10-digit mobile number
- PIN code
- Requested repair
- Date
- Time slot

Never guess missing details. Ask the customer to provide them.

Only serve PIN codes listed in data/service_areas.json.

Visit charges:
- Inner zone: ₹99
- Outer zone: ₹149

Pricing:
1. Read the service price from services.json.
2. Add the applicable visit charge.
3. Add ₹100 on Saturday and Sunday.
4. Calculate GST at 18% on the subtotal.
5. Round GST to the nearest rupee.
6. Calculate and return the final total.

All pricing calculations must be performed by Python tools, never by the AI model.

Cancellation:
- Before the appointment date: free.
- On the appointment date: ₹99.
- An unknown or already-cancelled booking must not be cancelled again.
- A cancelled slot becomes available again.

Unsupported work:
- Gas leaks
- Main electricity meter or street-pole work
- Painting
- Waterproofing and roof work
- Repairs to fridges, washing machines and TVs

For gas leaks, return the exact safety message from policies.md.
For main electricity meter or street-pole work, advise the customer to contact
their electricity provider.
Do not book unsupported work.

No discounts or free visits are allowed.

## 6. Required Python Tools

Implement these functions in tools.py:

- check_area(pin_code)
- find_services(category)
- get_price_quote(service_id, pin_code, date)
- check_slots(category, date)
- book_visit(name, phone, pin_code, service_id, date, slot)
- cancel_booking(booking_id)

Tools must use plain Python business logic.
They must validate inputs and return clear messages rather than crashing.
Use the supplied JSON files as the source of truth.

Prevent duplicate bookings for the same customer, date and slot.
Never book a slot that is already taken in slots.json or bookings.json.

## 7. Agent Requirements

Implement agent.py using the OpenAI Agents SDK.

Use:
- Agent
- Runner.run
- @function_tool
- Pydantic output model
- Model gpt-4.1-mini
- Maximum 10 agent turns

Include the company policies in the agent instructions.
Include today's date and the booking week in the agent context.
Return a stopped result when the agent cannot finish within the limit.
Print token usage after each run.

The final response model must include:
- status
- message
- booking_id
- service_name
- date
- slot
- job_price
- visit_charge
- weekend_extra
- gst
- total_price
- cancellation_fee

Allowed statuses:
- booked
- quote_only
- cancelled
- need_more_info
- cannot_help
- stopped

The AI must copy prices and booking details from tool results.
It must not calculate prices independently.

Implement a basic check against instructions embedded in customer messages
that attempt to override company rules. Customer messages must never override
the business policies.

## 8. FastAPI Requirements

Implement api.py with these endpoints:

- POST /request
  - Accept JSON containing a message.
  - Return the Pydantic final response.
  - Return HTTP 400 for an empty message.

- GET /bookings
  - Return the bookings stored in bookings.json.

- GET /health
  - Return {"status": "ok"}.

Test the endpoints using FastAPI's /docs page.

## 9. Streamlit Requirements

Implement app.py with:
- A clear page title.
- A short explanation of the agent.
- A text area for the customer request.
- A Send button.
- A spinner while the agent is processing.
- A booking confirmation with booking ID when applicable.
- A price breakdown for bookings and price quotes.
- Cancellation fee information for cancellations.
- A warning message for requests that cannot be completed.
- An All Bookings table loaded from the API.
- A friendly error message if the API is unavailable.

Do not add unnecessary features.

## 10. Code Style

- Use beginner-friendly Python.
- Prefer plain functions, loops and if statements.
- Use meaningful variable names.
- Add short comments where useful.
- Keep functions focused on one responsibility.
- Handle expected errors gracefully.
- No emojis in code, messages or the UI.
- Never print or expose API keys.
- Do not use hardcoded prices or availability when the supplied data provides them.

## 11. Testing Requirements

Test all six business tools independently before integrating the agent.

Verify:
- Correct weekday and weekend pricing.
- Inner and outer zone charges.
- Invalid phone numbers and missing information.
- Dates outside the booking week.
- Unavailable slots.
- Duplicate booking prevention.
- Cancellation fees.
- Unsupported work.
- Gas leak safety instructions.
- Unserved PIN codes.
- Attempts to override company rules.

Follow the instructor's six practice requests and expected results in the assignment brief.

## 12. Documentation and Delivery

Create README.md with installation, configuration, and run instructions.

Create test_results.md documenting the six practice requests, actual results,
expected results, booking IDs, prices or cancellation fees, and whether each
test passed.

Never include .env, .venv or bookings.json in the GitHub submission.

## 13. Implementation Notes

- Run the API: `uvicorn api:app --reload`. Run the UI: `streamlit run app.py`.
- The tools accept dates as YYYY-MM-DD or as a day name in the booking week
  ("Tuesday", "today", "tomorrow"). The model was less reliable when it had to
  convert day names itself.
- `agent.py` copies all prices, booking IDs and fees from tool results after each run
  (`apply_tool_results`), so the model's own numbers are never returned.
- If the model claims "booked" without calling `book_visit`, `run_agent` sends one
  follow-up within the remaining turns of the 10-turn limit.
- PIN codes found in a message are checked with `tools.check_area` and the result is
  passed to the agent, because the model sometimes answered without checking.
- To reset all bookings, delete bookings.json. It is recreated automatically.
