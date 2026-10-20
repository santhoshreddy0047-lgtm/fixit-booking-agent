"""FastAPI server for the FixIt booking agent.

Start it with:
    uvicorn api:app --reload
Then open http://127.0.0.1:8000/docs to try the endpoints.
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

import tools
from agent import FixItResponse, run_agent

app = FastAPI(title="FixIt Booking Agent API")


class CustomerRequest(BaseModel):
    message: str


@app.post("/request", response_model=FixItResponse)
async def handle_request(request: CustomerRequest):
    """Send a customer message to the agent and return its final response."""
    if request.message.strip() == "":
        raise HTTPException(status_code=400, detail="Message must not be empty.")
    return await run_agent(request.message)


@app.get("/bookings")
def list_bookings():
    """Return every booking stored in bookings.json."""
    try:
        return tools.load_bookings()
    except (OSError, ValueError) as error:
        print(f"[API] Could not read bookings.json: {type(error).__name__}")
        raise HTTPException(status_code=500, detail="The bookings file could not be read. Please check bookings.json.")


@app.get("/health")
def health():
    return {"status": "ok"}
