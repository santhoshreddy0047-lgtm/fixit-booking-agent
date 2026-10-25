"""Tests for the Streamlit page (app.py) that do not call OpenAI or change bookings.json.

Run from the project folder with:
    python tests/test_app.py

The FastAPI back end is replaced by a small fake that returns answers shaped exactly
like the real API, so the tests check how the page sends requests and shows answers.
"""

import html
import io
import sys
from pathlib import Path
from unittest.mock import patch

# The application modules are in the project folder, one level above tests/
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
APP_FILE = str(ROOT / "app.py")

import requests
import streamlit as st
from PIL import Image
from streamlit.testing.v1 import AppTest

import tools

# The assignment's scenario: "today" is Monday 2 November 2026 in Pune.
# tools.today() normally reads the real date; the tests pin it so their results never change.
from datetime import date as _date
ASSIGNMENT_TODAY = _date(2026, 11, 2)
tools.today = lambda: ASSIGNMENT_TODAY
# In test environments where pyarrow C-extension DLL is restricted by Windows Application Control,
# provide test-runner compatibility for AppTest's headless element tree inspection.
try:
    import pyarrow
except ImportError:
    import pickle
    import types
    import pandas as _pd
    import streamlit.dataframe_util as _dfu
    _pa = types.ModuleType("pyarrow")
    _pa.__version__ = "18.0.0"
    _pa.Table = type("Table", (), {})
    _pa.Array = type("Array", (), {})
    _pa.RecordBatch = type("RecordBatch", (), {})
    sys.modules["pyarrow"] = _pa
    _dfu.convert_pandas_df_to_arrow_bytes = lambda df, **k: pickle.dumps(df)
    _dfu.convert_arrow_bytes_to_pandas_df = lambda b: pickle.loads(b)

import app as fixit_app   # the page's helper functions (importing does not draw the page)

passed = 0
failed = 0

GAS_MESSAGE = ("For your safety, open the windows, do not switch on any lights or flames, "
               "and call your gas agency's emergency number right away.")

SAVED_BOOKINGS = [
    {"booking_id": "FX-1001", "name": "Meera Joshi", "phone": "9876543210", "pin_code": "411038",
     "area": "Kothrud", "service_id": "P01", "service_name": "Tap repair", "category": "plumber",
     "date": "2026-11-03", "day": "Tuesday", "slot": "Morning", "job_price": 199, "visit_charge": 99,
     "weekend_extra": 0, "gst": 54, "total_price": 352, "status": "booked", "cancellation_fee": 0},
    {"booking_id": "FX-1002", "name": "Arjun Mehta", "phone": "9823012345", "pin_code": "411021",
     "area": "Bavdhan", "service_id": "E01", "service_name": "Fan installation", "category": "electrician",
     "date": "2026-11-07", "day": "Saturday", "slot": "Afternoon", "job_price": 249, "visit_charge": 149,
     "weekend_extra": 100, "gst": 90, "total_price": 588, "status": "cancelled", "cancellation_fee": 0},
]


def answer(status, message, **fields):
    """An answer in the same shape as the real POST /request response."""
    result = {"status": status, "message": message, "booking_id": "", "service_name": "", "date": "",
              "slot": "", "job_price": 0, "visit_charge": 0, "weekend_extra": 0, "gst": 0,
              "total_price": 0, "cancellation_fee": 0}
    result.update(fields)
    return result


BOOKED = answer("booked", "Your plumber visit is booked for Tuesday morning.", booking_id="FX-1001",
                service_name="Tap repair", date="2026-11-03", slot="Morning", job_price=199,
                visit_charge=99, weekend_extra=0, gst=54, total_price=352)
QUOTE = answer("quote_only", "A pipe leak repair on Wednesday costs Rs 529.", service_name="Pipe leak repair",
               date="2026-11-04", job_price=349, visit_charge=99, weekend_extra=0, gst=81, total_price=529)
CANCELLED = answer("cancelled", "Booking FX-1001 is cancelled.", booking_id="FX-1001",
                   service_name="Tap repair", date="2026-11-03", slot="Morning", cancellation_fee=99)
MORE_INFO = answer("need_more_info", "Please tell us your name, mobile number and PIN code.")
GAS = answer("cannot_help", GAS_MESSAGE)
NOT_SERVED = answer("cannot_help", "We do not serve pin code 400001 yet.")
STOPPED = answer("stopped", "Sorry, the booking assistant is not available right now.")
GREETING_INFO = answer("info", "Hello! I am your FixIt assistant. I can help you get price quotes, book visits, check time slots and more. How can I help you today?")
SERVICES_INFO = answer("info", "We offer 11 repair services across four categories: Plumbing (Tap repair, Pipe leak repair, Toilet flush repair), Electrical (Fan installation, Switchboard repair, Light fitting), AC Services (AC service, AC gas refill, AC installation), and Carpentry (Door lock repair, Furniture assembly).")


class FakeResponse:
    def __init__(self, status_code, data):
        self.status_code = status_code
        self.data = data

    def json(self):
        return self.data


class FakeBackend:
    """Stands in for the FastAPI back end and records every request the page sends."""

    def __init__(self, bookings=None):
        self.bookings = list(SAVED_BOOKINGS) if bookings is None else bookings
        self.next_answer = BOOKED
        self.down = False
        self.posted_messages = []
        self.other_calls = []

    def get(self, url, timeout=None, **kwargs):
        if self.down:
            raise requests.exceptions.ConnectionError("refused")
        if url.endswith("/health"):
            return FakeResponse(200, {"status": "ok"})
        if url.endswith("/bookings"):
            return FakeResponse(200, self.bookings)
        self.other_calls.append(("GET", url))
        return FakeResponse(404, {})

    def post(self, url, json=None, timeout=None, **kwargs):
        if self.down:
            raise requests.exceptions.ConnectionError("refused")
        if not url.endswith("/request"):
            self.other_calls.append(("POST", url))
            return FakeResponse(404, {})
        self.posted_messages.append(json["message"])
        return FakeResponse(200, self.next_answer)


def check(label, condition, details=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"PASS  {label}")
    else:
        failed += 1
        print(f"FAIL  {label}  ->  {str(details)[:300]}")


def page_html(app):
    """All the HTML and text the page drew (without the stylesheet)."""
    return "\n".join(element.value for element in app.markdown if not element.value.startswith("<style>"))


def start(backend):
    # The page caches the health check and the bookings list for a few seconds.
    # Each test starts with empty caches so it only sees its own fake back end.
    st.cache_data.clear()
    with patch("requests.get", backend.get), patch("requests.post", backend.post):
        app = AppTest.from_file(APP_FILE, default_timeout=30)
        app.run()
    return app


def run(app, backend, action):
    """Run one user action (a click or a form submit) with the fake back end in place."""
    with patch("requests.get", backend.get), patch("requests.post", backend.post):
        action().run()
    return app


def button(app, label=None, key=None):
    """Find a button by key, or by its label (the first line, for two-line sidebar labels)."""
    for item in app.button:
        if key is not None and item.key == key:
            return item
        if label is not None and item.label.split("\n")[0].strip() == label:
            return item
    raise LookupError(f"button {label or key} not found")


def send(app, backend, text):
    """Type a message in the composer and press Send."""
    app.text_input(key="composer_text").input(text)
    return run(app, backend, lambda: button(app, label="Send").click())


# ---------------------------------------------------------------------------
print("\n== First load")
backend = FakeBackend()
app = start(backend)
text = page_html(app)
check("page loads without errors", len(app.exception) == 0, [e.value for e in app.exception])
check("header shows FixIt branding and tagline", "FixIt" in text and "Reliable home repair services across Pune" in text)
check("header shows the four header items",
      all(item in text for item in ["Verified Technicians", "Flexible Time Slots", "Pune Coverage", "Help &amp; Support"]))
check("greeting lists what the assistant can do",
      all(item in text for item in ["Get a price quote", "Book a home repair visit", "Check available time slots",
                                     "Cancel an existing booking", "Answer questions about our services and policies"]))
check("assistant shows Online when GET /health works", "fx-pill online" in text)
check("all six navigation items exist",
      all(button(app, label=title) for title in ["Chat with Assistant", "Book a Service", "Our Services",
                                                 "Service Areas", "All Bookings", "Policies & Safety"]))
check("popular services come from services.json",
      all(button(app, key=f"popular_{c}") for c in ["plumber", "electrician", "ac_technician", "carpenter"]))
check("recent bookings come from GET /bookings", "FX-1001" in text and "FX-1002" in text)
check("cancelled booking shows its fee, not its old total", "Cancelled" in text and "Fee &#8377;0" in text)
check("safety notice uses the exact gas message from policies.md", html.escape(GAS_MESSAGE) in text)
check("nothing was sent to the agent on page load", backend.posted_messages == [])

# ---------------------------------------------------------------------------
print("\n== Sending a message and a real booking answer")
backend = FakeBackend()
app = start(backend)
send(app, backend, "My kitchen tap is leaking. Please send a plumber on Tuesday morning. Meera Joshi, 9876543210, pin 411038.")
text = page_html(app)
check("message sent to POST /request exactly once",
      backend.posted_messages == ["My kitchen tap is leaking. Please send a plumber on Tuesday morning. "
                                  "Meera Joshi, 9876543210, pin 411038."], backend.posted_messages)
check("no errors after sending", len(app.exception) == 0, [e.value for e in app.exception])
check("customer message shown in the chat", "Meera Joshi, 9876543210, pin 411038." in text)
check("agent's own message shown", "Your plumber visit is booked for Tuesday morning." in text)
check("green Booking Confirmed card shown", "fx-result success" in text and "Booking Confirmed" in text)
check("booking ID from the back end", "FX-1001" in text)
check("price lines copied from the response",
      all(value in text for value in ["&#8377;199", "&#8377;99", "&#8377;0", "&#8377;54", "&#8377;352"]))
check("customer, phone and area come from the saved booking",
      "Meera Joshi" in text and "9876543210" in text and "Kothrud, 411038" in text)
check("zone looked up in service_areas.json by the booking's PIN code",
      "Kothrud, 411038 (Inner zone)" in text and "Visit charge (Inner zone)" in text)
check("time slot shown with its hours", "Morning (9 AM - 12 PM)" in text)
check("waiting state cleared after the answer", app.session_state["pending"] is None)
check("chat history kept (greeting, customer, agent)", len(app.session_state["messages"]) == 3)

# ---------------------------------------------------------------------------
print("\n== A booked answer whose ID is not in GET /bookings")
backend = FakeBackend(bookings=[])
app = start(backend)
send(app, backend, "Book it")
text = page_html(app)
check("card still shows backend fields", "Booking Confirmed" in text and "FX-1001" in text)
check("no customer details are invented", "Customer" not in text and "Meera" not in text)

# ---------------------------------------------------------------------------
print("\n== Quote only")
backend = FakeBackend()
backend.next_answer = QUOTE
app = start(backend)
send(app, backend, "How much for fixing a leaking pipe under my kitchen sink on Wednesday? I live in 411004.")
text = page_html(app)
check("Price Estimate card shown", "Price Estimate" in text and "fx-result quote" in text)
check("quote is not shown as a confirmed booking", "Booking Confirmed" not in text and "fx-result success" not in text)
check("says no booking was made", "No booking has been made." in text)
check("estimated total from the response", "Estimated total" in text and "&#8377;529" in text and "&#8377;81" in text)
check("quote shows no zone (the quote response has no PIN code to look up)", "Visit charge (" not in text)

# ---------------------------------------------------------------------------
print("\n== Cancellation")
backend = FakeBackend()
backend.next_answer = CANCELLED
app = start(backend)
send(app, backend, "Cancel booking FX-1001")
text = page_html(app)
check("Booking Cancelled card shown", "Booking Cancelled" in text and "FX-1001" in text)
check("cancellation fee from the response (Rs 99)", "Cancellation fee" in text and "&#8377;99" in text)
check("same-day fee explained", "Same-day cancellation fee." in text)
check("cancellation is not shown as a new booking", "Booking Confirmed" not in text)

# ---------------------------------------------------------------------------
print("\n== Need more info, cannot help, safety and stopped")
for result, label, tone in [
    (MORE_INFO, "More details needed", "notice-amber"),
    (NOT_SERVED, "We cannot help with this request", "notice-gray"),
    (GAS, "Safety notice", "notice-amber"),
    (STOPPED, "Request stopped", "notice-red"),
]:
    backend = FakeBackend()
    backend.next_answer = result
    app = start(backend)
    send(app, backend, "test message")
    text = page_html(app)
    check(f"{result['status']}: shows '{label}'", label in text and tone in text)
    check(f"{result['status']}: shows the agent's message", html.escape(result["message"]) in text)
    check(f"{result['status']}: no confirmation or price card", "fx-result" not in text)

# ---------------------------------------------------------------------------
print("\n== Info status: greetings and general enquiries")
for result, description in [
    (GREETING_INFO, "greeting"),
    (SERVICES_INFO, "service listing"),
]:
    backend = FakeBackend()
    backend.next_answer = result
    app = start(backend)
    send(app, backend, "Hi" if description == "greeting" else "What services do you provide?")
    text = page_html(app)
    check(f"info ({description}): shows the agent's message", html.escape(result["message"]) in text)
    check(f"info ({description}): NOT shown as 'More details needed'", "More details needed" not in text)
    check(f"info ({description}): NOT shown as 'Request stopped'", "Request stopped" not in text)
    check(f"info ({description}): NOT shown as 'cannot help'", "We cannot help" not in text)
    check(f"info ({description}): no confirmation or price card", "fx-result" not in text)
    check(f"info ({description}): shown as a plain chat bubble", "fx-bubble bot" in text)

# ---------------------------------------------------------------------------
print("\n== Agent text is escaped, never run as HTML")
backend = FakeBackend()
backend.next_answer = answer("need_more_info", "<script>alert(1)</script> <b>bold</b>")
app = start(backend)
send(app, backend, "<img src=x onerror=alert(1)>")
text = page_html(app)
check("agent HTML is escaped", "<script>" not in text and "&lt;script&gt;" in text)
check("customer HTML is escaped", "<img src=x" not in text and "&lt;img src=x" in text)

# ---------------------------------------------------------------------------
print("\n== Back end unavailable")
backend = FakeBackend()
backend.down = True
app = start(backend)
text = page_html(app)
check("page still loads", len(app.exception) == 0, [e.value for e in app.exception])
check("assistant shows Offline", "fx-pill offline" in text)
check("recent bookings explain the problem", "Bookings unavailable" in text)
send(app, backend, "How much is a tap repair?")
text = page_html(app)
check("friendly service unavailable message", "Service unavailable" in text and "temporarily unavailable" in text)
check("no stack trace or internal details shown", "Traceback" not in text and "refused" not in text)
check("Try again button offered", any(item.key == "retry" for item in app.button))
backend.down = False
backend.next_answer = QUOTE
run(app, backend, lambda: button(app, key="retry").click())
text = page_html(app)
check("Try again resends the same message once", backend.posted_messages == ["How much is a tap repair?"], backend.posted_messages)
check("answer shown after retry", "Price Estimate" in text)

# ---------------------------------------------------------------------------
print("\n== Empty booking history")
backend = FakeBackend(bookings=[])
app = start(backend)
check("recent bookings empty state", "No bookings yet" in page_html(app))
run(app, backend, lambda: button(app, label="All Bookings").click())
check("All Bookings page empty state", "No bookings yet" in page_html(app) and len(app.exception) == 0)

# ---------------------------------------------------------------------------
print("\n== Clear chat")
backend = FakeBackend()
app = start(backend)
send(app, backend, "Book it")
run(app, backend, lambda: button(app, key="clear_chat").click())
check("chat back to the greeting only", len(app.session_state["messages"]) == 1
      and app.session_state["messages"][0]["kind"] == "greeting")
check("clearing the chat sends nothing to the back end", backend.other_calls == [] and backend.posted_messages == ["Book it"])

# ---------------------------------------------------------------------------
print("\n== Shortcuts and quick actions")
backend = FakeBackend()
app = start(backend)
backend.next_answer = MORE_INFO
run(app, backend, lambda: button(app, key="qa_quote").click())
check("Get a Price Quote sends a plain request with no invented details",
      backend.posted_messages == ["I would like a price quote."], backend.posted_messages)
check("a quick action leaves the message box empty", app.text_input(key="composer_text").value == "")
check("the quote request stays open while details are needed",
      app.session_state["open_request"] == "I would like a price quote.")
send(app, backend, "Tap repair, PIN 411038, Wednesday")
check("the follow-up is sent with the open request",
      backend.posted_messages[-1] == "I would like a price quote.\nFollow-up from the customer: Tap repair, PIN 411038, Wednesday",
      backend.posted_messages[-1])
check("the chat shows only what the customer typed",
      app.session_state["messages"][-2]["text"] == "Tap repair, PIN 411038, Wednesday")
backend.next_answer = QUOTE
send(app, backend, "Morning")
check("a finished answer closes the open request", app.session_state["open_request"] is None)
send(app, backend, "Hello")
check("a new message after a finished answer is sent on its own", backend.posted_messages[-1] == "Hello")
backend.next_answer = MORE_INFO
send(app, backend, "Book a plumber")
run(app, backend, lambda: button(app, key="qa_cancel").click())
check("a quick action starts a new request, not a follow-up",
      backend.posted_messages[-1] == "I want to cancel a booking.", backend.posted_messages[-1])
send(app, backend, "Book a plumber")
run(app, backend, lambda: button(app, key="clear_chat").click())
check("clearing the chat closes the open request", app.session_state["open_request"] is None)
run(app, backend, lambda: button(app, key="qa_services").click())
check("View Supported Services opens Our Services", app.session_state["page"] == "services" and len(app.exception) == 0)
run(app, backend, lambda: button(app, key="nav_chat").click())
run(app, backend, lambda: button(app, key="qa_book").click())
check("Book a Service opens the booking form", app.session_state["page"] == "book")

# ---------------------------------------------------------------------------
print("\n== Every page loads")
for title, page in [("Book a Service", "book"), ("Our Services", "services"), ("Service Areas", "areas"),
                    ("All Bookings", "bookings"), ("Policies & Safety", "policies"), ("Chat with Assistant", "chat")]:
    backend = FakeBackend()
    app = start(backend)
    run(app, backend, lambda: button(app, label=title).click())
    check(f"{title} page loads", app.session_state["page"] == page and len(app.exception) == 0,
          [e.value for e in app.exception])
backend = FakeBackend()
app = start(backend)
run(app, backend, lambda: button(app, key="popular_electrician").click())
check("popular service opens Our Services filtered to it", app.session_state["service_filter"] == "Electrical")
check("electrical services from services.json listed", "Fan installation" in page_html(app) and "Tap repair" not in page_html(app))

# ---------------------------------------------------------------------------
print("\n== Book a Service form")
backend = FakeBackend()
app = start(backend)
run(app, backend, lambda: button(app, label="Book a Service").click())
run(app, backend, lambda: button(app, label="Send booking request").click())
check("empty form asks for the missing details", any("Please fill in" in w.value for w in app.warning))
check("empty form sends nothing", backend.posted_messages == [])
app.selectbox[0].select_index(0)      # Service: Tap repair
app.selectbox[1].select_index(1)      # Day: Tuesday
app.selectbox[2].select_index(0)      # Slot: Morning
app.selectbox[3].select_index(4)      # PIN code: 411038 - Kothrud
app.text_input[0].input("Meera Joshi")
app.text_input[1].input("9876543210")
run(app, backend, lambda: button(app, label="Send booking request").click())
check("form sends one message to the agent",
      backend.posted_messages == ["Please book a Tap repair on Tuesday morning. Name: Meera Joshi. "
                                  "Mobile: 9876543210. PIN code: 411038."], backend.posted_messages)
check("form opens the chat with the answer", app.session_state["page"] == "chat" and "Booking Confirmed" in page_html(app))

# ---------------------------------------------------------------------------
print("\n== Technician photo")
backend = FakeBackend()
app = start(backend)
check("chat page shows one image (the technician photo)", len(app.get("image")) == 1, len(app.get("image")))
photo = fixit_app.technician_photo()
with Image.open(fixit_app.TECHNICIAN_IMAGE) as original:
    original_width, original_height = original.size
with Image.open(io.BytesIO(photo)) as shown:
    shown_format, (shown_width, shown_height) = shown.format, shown.size
check("photo comes from assets/technician.png (the folder that is published with the app)",
      fixit_app.TECHNICIAN_IMAGE == Path(fixit_app.__file__).parent / "assets" / "technician.png")
check("photo is a small JPEG, not the 2.4 MB original", shown_format == "JPEG" and len(photo) < 150_000, len(photo))
check("photo keeps the 4:5 head-and-shoulders crop", abs(shown_height / shown_width - 1.25) < 0.01,
      (shown_width, shown_height))
check("photo is scaled evenly, not stretched (same scale for width and height)",
      abs(shown_width / original_width - shown_height / (original_width * 1.25)) < 0.01,
      (original_width, original_height, shown_width, shown_height))
check("technician photo file exists in assets/", fixit_app.TECHNICIAN_IMAGE.exists())
check("the app does not depend on the reference/ folder (it is not published)",
      "reference" not in fixit_app.TECHNICIAN_IMAGE.parts
      and "reference/" not in Path(fixit_app.__file__).read_text(encoding="utf-8").replace("\\", "/"))
real_path = fixit_app.TECHNICIAN_IMAGE
fixit_app.TECHNICIAN_IMAGE = Path("missing-photo.png")
fixit_app.technician_photo.clear()
check("a missing photo file gives None instead of an error", fixit_app.technician_photo() is None)
fixit_app.TECHNICIAN_IMAGE = real_path
fixit_app.technician_photo.clear()

backend = FakeBackend()
with patch("PIL.Image.open", side_effect=OSError("missing")):
    app = start(backend)
text = page_html(app)
check("missing photo: page still loads", len(app.exception) == 0, [e.value for e in app.exception])
check("missing photo: placeholder shown, no other image substituted",
      "Photo unavailable" in text and len(app.get("image")) == 0)
fixit_app.technician_photo.clear()

print("\n== Promotional claims come from policies.md")
backend = FakeBackend()
app = start(backend)
text = page_html(app)
policies = fixit_app.load_policies()
check("promo card heading shown", "Professional Home Repair Services" in text)
check("'trained' is stated in policies.md", "trained" in policies)
check("'30-day warranty' is stated in policies.md", "30-day warranty" in policies and "30-day warranty" in text)
check("same price for every customer is stated in policies.md", "same for every customer" in policies)
check("no invented ratings, customer counts or phone numbers",
      not any(claim in text for claim in ["rating", "5 star", "customers served", "+91", "1800"]))

print("\n== Sidebar")
nav_labels = {item.key: item.label for item in app.button if item.key and item.key.startswith("nav_")}
check("navigation shows a description under each title (no hover needed)",
      len(nav_labels) == 6 and all("\n" in label for label in nav_labels.values()), nav_labels)
check("active page is the primary button", button(app, key="nav_chat").proto.type == "primary")
check("booking dates note comes from the tools' bookable dates", "02 Nov – 08 Nov 2026" in text)
check("popular-service counts match services.json",
      all(button(app, key=f"popular_{category}").label.endswith(f"{len(items)} services")
          for category, items in fixit_app.services_by_category().items()))
print("\n== Bookings are never stale after an answer")
backend = FakeBackend()
app = start(backend)
check("recent bookings start with FX-1001 and FX-1002", "FX-1002" in page_html(app) and "FX-1003" not in page_html(app))
new_booking = dict(SAVED_BOOKINGS[0], booking_id="FX-1003", name="Asha", service_name="Pipe leak repair")
backend.bookings = backend.bookings + [new_booking]
backend.next_answer = dict(BOOKED, booking_id="FX-1003", service_name="Pipe leak repair")
send(app, backend, "Book a pipe leak repair")
check("new booking appears in Recent Bookings straight after the answer", "FX-1003" in page_html(app))
check("booking card uses the new booking's saved customer", "Asha" in page_html(app))
run(app, backend, lambda: button(app, label="All Bookings").click())
backend.bookings = backend.bookings + [dict(SAVED_BOOKINGS[0], booking_id="FX-1004")]
run(app, backend, lambda: button(app, key="refresh_bookings").click())
check("Refresh on All Bookings reloads from GET /bookings",
      "FX-1004" in str(app.dataframe[0].value["Booking ID"].tolist()), app.dataframe[0].value["Booking ID"].tolist())

# ---------------------------------------------------------------------------
print("\n== Audit: cancellation refreshes Recent Bookings (no stale status)")
backend = FakeBackend(bookings=[dict(SAVED_BOOKINGS[0])])
app = start(backend)
check("FX-1001 starts as Confirmed", "Confirmed" in page_html(app) and "Cancelled" not in page_html(app))
backend.bookings = [dict(SAVED_BOOKINGS[0], status="cancelled", cancellation_fee=99)]
backend.next_answer = dict(CANCELLED, cancellation_fee=99)
send(app, backend, "Cancel booking FX-1001")
text = page_html(app)
check("after the cancel answer, Recent Bookings shows FX-1001 as Cancelled with Fee Rs 99",
      "fx-pill cancelled" in text and "Fee &#8377;99" in text and "fx-pill confirmed" not in text)
check("cancellation card fee equals the backend's 99", "Cancellation fee" in text and "&#8377;99" in text)

print("\n== Audit: reruns never re-send a request")
backend = FakeBackend()
app = start(backend)
send(app, backend, "Book it")
for key in ["nav_services", "nav_areas", "nav_bookings", "nav_policies", "nav_chat", "brand_logo"]:
    run(app, backend, lambda key=key: button(app, key=key).click())
check("one message sent once, even after six more reruns", backend.posted_messages == ["Book it"], backend.posted_messages)
check("chat history not duplicated by reruns", len(app.session_state["messages"]) == 3, len(app.session_state["messages"]))

print("\n== Audit: weekend outer-zone booking card shows the backend values exactly")
weekend = answer("booked", "Booked.", booking_id="FX-1002", service_name="Fan installation", date="2026-11-07",
                 slot="Afternoon", job_price=249, visit_charge=149, weekend_extra=100, gst=90, total_price=588)
backend = FakeBackend(bookings=[dict(SAVED_BOOKINGS[1], status="booked")])
backend.next_answer = weekend
app = start(backend)
send(app, backend, "Book the fan")
text = page_html(app)
for label, value in [("service price", 249), ("visit charge", 149), ("weekend extra", 100), ("GST", 90), ("total", 588)]:
    check(f"card shows {label} Rs {value} from the response", f"&#8377;{value}" in text)
check("card shows date, slot, customer, phone, area and outer zone",
      all(item in text for item in ["Saturday, 07 Nov 2026", "Afternoon (12 PM - 3 PM)", "Arjun Mehta", "9823012345",
                                    "Bavdhan, 411021 (Outer zone)", "Visit charge (Outer zone)"]))

print("\n== Audit: All Bookings filters")
backend = FakeBackend()
app = start(backend)
run(app, backend, lambda: button(app, key="nav_bookings").click())
table = app.dataframe[0].value
check("All shows both bookings with their real statuses",
      table["Booking ID"].tolist() == ["FX-1002", "FX-1001"] and table["Status"].tolist() == ["Cancelled", "Confirmed"],
      table.to_dict())
app.segmented_control(key="booking_view").set_value("Cancelled")
run(app, backend, lambda: app)
check("Cancelled filter shows only FX-1002", app.dataframe[0].value["Booking ID"].tolist() == ["FX-1002"])
app.segmented_control(key="booking_view").set_value("Confirmed")
run(app, backend, lambda: app)
check("Confirmed filter shows only FX-1001", app.dataframe[0].value["Booking ID"].tolist() == ["FX-1001"])

print("\n== Audit: catalogue, areas and policies pages show the data files")
run(app, backend, lambda: button(app, key="nav_services").click())
text = page_html(app)
missing = [s["service_id"] for s in fixit_app.load_services()
           if s["name"] not in text or f"&#8377;{s['price']:,}" not in text]
check("Our Services lists all 11 services with their prices", missing == [], missing)
run(app, backend, lambda: button(app, key="nav_areas").click())
text = page_html(app)
missing = [a["pin_code"] for a in fixit_app.load_service_areas() if a["pin_code"] not in text or a["area"] not in text]
check("Service Areas lists every PIN code and area", missing == [], missing)
check("Service Areas shows both zone charges", "&#8377;99" in text and "&#8377;149" in text)
run(app, backend, lambda: button(app, key="nav_policies").click())
markdown_text = "\n".join(element.value for element in app.markdown)
check("Policies page shows the whole policies.md", fixit_app.load_policies() in markdown_text)

print("\n== Audit: bad back-end responses are shown as friendly messages")


class OddResponse:
    def __init__(self, status_code, data=None, bad_json=False):
        self.status_code = status_code
        self.data = data
        self.bad_json = bad_json

    def json(self):
        if self.bad_json:
            raise ValueError("not json")
        return self.data


def odd_post(response=None, error=None):
    def post(url, json=None, timeout=None, **kwargs):
        if error:
            raise error
        return response
    return post


for label, post, expected in [
    ("timeout", odd_post(error=requests.exceptions.Timeout("slow")), "taking longer than expected"),
    ("HTTP 500", odd_post(OddResponse(500, {"detail": "Internal Server Error"})), "Something went wrong on our side"),
    ("HTTP 422", odd_post(OddResponse(422, {"detail": []})), "could not be read"),
    ("not JSON", odd_post(OddResponse(200, bad_json=True)), "Something went wrong on our side"),
    ("JSON without a status", odd_post(OddResponse(200, {"message": "hi"})), "Something went wrong on our side"),
    ("JSON list instead of an object", odd_post(OddResponse(200, ["x"])), "Something went wrong on our side"),
]:
    backend = FakeBackend()
    app = start(backend)
    app.text_input(key="composer_text").input("hello")
    with patch("requests.get", backend.get), patch("requests.post", post):
        button(app, label="Send").click().run()
    text = page_html(app)
    check(f"{label}: friendly message, retry offered, no crash",
          expected in text and len(app.exception) == 0 and any(item.key == "retry" for item in app.button),
          [e.value for e in app.exception] or text[-300:])
    check(f"{label}: no internal details shown", "Traceback" not in text and "Internal Server Error" not in text)


def bookings_fail(url, timeout=None, **kwargs):
    if url.endswith("/health"):
        return FakeResponse(200, {"status": "ok"})
    return OddResponse(500, {"detail": "The bookings file could not be read."})

st.cache_data.clear()
with patch("requests.get", bookings_fail), patch("requests.post", FakeBackend().post):
    app = AppTest.from_file(APP_FILE, default_timeout=30).run()
check("GET /bookings error: Recent Bookings shows a message, the page still works",
      "Bookings could not be loaded" in page_html(app) and len(app.exception) == 0)

# ---------------------------------------------------------------------------
print("\n== Clickable FixIt logo and Back Navigation")
backend = FakeBackend()
app = start(backend)
send(app, backend, "Hello assistant")
check("chat has conversation history", len(app.session_state.messages) >= 2)

# Navigate to Our Services page
run(app, backend, lambda: button(app, label="Our Services").click())
check("navigated to services page", app.session_state.page == "services")

# Click FixIt logo in the header
run(app, backend, lambda: button(app, key="brand_logo").click())
check("logo click returns user to assistant screen", app.session_state.page == "chat")
check("logo click preserves chat history", len(app.session_state.messages) >= 2)
check("logo click preserves bookings", len(backend.bookings) >= 2)

# Test back button on each secondary page
for page_key, nav_label, back_key in [
    ("services", "Our Services", "back_btn_services"),
    ("book", "Book a Service", "back_btn_book"),
    ("areas", "Service Areas", "back_btn_areas"),
    ("bookings", "All Bookings", "back_btn_bookings"),
    ("policies", "Policies & Safety", "back_btn_policies"),
]:
    # Start at chat, navigate to page, then click back
    app.session_state.page = "chat"
    run(app, backend, lambda: button(app, label=nav_label).click())
    check(f"navigated to {nav_label}", app.session_state.page == page_key)
    run(app, backend, lambda: button(app, key=back_key).click())
    check(f"back button from {nav_label} returns to chat", app.session_state.page == "chat")

# Test Quick Actions navigation
run(app, backend, lambda: button(app, key="qa_book").click())
check("Quick Action 'Book a Service' opens book page", app.session_state.page == "book")

# Return to chat screen via back button
run(app, backend, lambda: button(app, key="back_btn_book").click())
check("returned to chat from book page", app.session_state.page == "chat")

run(app, backend, lambda: button(app, key="qa_services").click())
check("Quick Action 'View Supported Services' opens services page", app.session_state.page == "services")

# Return to chat screen via logo button
run(app, backend, lambda: button(app, key="brand_logo").click())
check("returned to chat from services page", app.session_state.page == "chat")

for key, request in [("qa_quote", "I would like a price quote."),
                     ("qa_slots", "Which appointment slots are available?"),
                     ("qa_cancel", "I want to cancel a booking.")]:
    run(app, backend, lambda: button(app, key=key).click())
    check(f"Quick Action {key} sends '{request}' and opens the chat",
          backend.posted_messages[-1] == request and app.session_state.page == "chat"
          and app.session_state.composer_text == "", backend.posted_messages[-1:])

# ---------------------------------------------------------------------------
print(f"\n{passed} passed, {failed} failed")
if failed:
    raise SystemExit(1)
