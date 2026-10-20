"""Streamlit front end for the FixIt booking agent.

Start the API first, then the page:
    uvicorn api:app --reload
    streamlit run app.py

Every answer in the chat comes from the FastAPI back end (POST /request), which runs
the agent. This page never works out prices, booking IDs or availability itself.
"""

import html
import io
import json
import os
import re
from datetime import date, datetime, timedelta
from pathlib import Path

import requests
import streamlit as st
from PIL import Image  # installed together with Streamlit

API_URL = os.getenv("FIXIT_API_URL", "http://127.0.0.1:8000")
REQUEST_TIMEOUT = 120
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
CSS_FILE = BASE_DIR / "assets" / "styles.css"
TECHNICIAN_IMAGE = BASE_DIR / "assets" / "technician.png"

# Booking week from policies.md (the tools use the same fixed dates)
WEEK_START = date(2026, 11, 2)
BOOKING_WEEK = [WEEK_START + timedelta(days=offset) for offset in range(7)]
SLOT_TIMES = {"Morning": "9 AM - 12 PM", "Afternoon": "12 PM - 3 PM", "Evening": "3 PM - 6 PM"}

# Pages in the left navigation: (page key, title, short description, icon)
NAV_ITEMS = [
    ("chat", "Chat with Assistant", "Get quotes, book, check slots", ":material/forum:"),
    ("book", "Book a Service", "Schedule a home visit", ":material/event_available:"),
    ("services", "Our Services", "Explore all repair services", ":material/home_repair_service:"),
    ("areas", "Service Areas", "Check if we serve your area", ":material/location_on:"),
    ("bookings", "All Bookings", "View all bookings", ":material/receipt_long:"),
    ("policies", "Policies & Safety", "Important rules and guidelines", ":material/health_and_safety:"),
]

CATEGORY_INFO = {
    "plumber": {"label": "Plumbing", "icon": ":material/plumbing:", "svg": "droplet"},
    "electrician": {"label": "Electrical", "icon": ":material/electrical_services:", "svg": "zap"},
    "ac_technician": {"label": "AC Services", "icon": ":material/ac_unit:", "svg": "snowflake"},
    "carpenter": {"label": "Carpentry", "icon": ":material/carpenter:", "svg": "hammer"},
}

# Starter text placed in the message box by the shortcuts. The customer finishes it.
STARTERS = {
    "quote": "How much would a tap repair cost on Tuesday? My PIN code is ",
    "book": "Please book a visit. Repair needed: , Day: , Slot (Morning, Afternoon or Evening): , "
            "Name: , Mobile: , PIN code: ",
    "slots": "Which time slots are free for a plumber on ",
    "cancel": "Please cancel my booking FX-",
    "services": "Which repair services do you offer?",
}
SHORTCUTS = [
    ("quote", ":material/currency_rupee: Get a price quote"),
    ("book", ":material/event_available: Book a visit"),
    ("slots", ":material/schedule: Check availability"),
    ("cancel", ":material/event_busy: Cancel a booking"),
    ("services", ":material/grid_view: Supported services"),
]

# Icons for the HTML parts of the page. They use Material Symbols Rounded, the same icon
# font Streamlit uses for button icons, so every icon on the page comes from one family.
ICON_NAMES = {
    "house": "home", "shield": "verified_user", "calendar": "calendar_month",
    "calendar-x": "event_busy", "pin": "location_on", "headset": "support_agent",
    "bot": "smart_toy", "user": "person", "check": "check_circle", "wrench": "build",
    "droplet": "plumbing", "zap": "electrical_services", "snowflake": "ac_unit",
    "hammer": "carpenter", "clock": "schedule", "phone": "call", "rupee": "currency_rupee",
    "alert": "warning", "info": "info", "x-circle": "cancel", "tag": "sell", "inbox": "inbox",
    "award": "workspace_premium", "engineering": "engineering",
}


def icon(name, size=18):
    """Return a Material Symbols icon as an HTML string."""
    return (
        f'<span class="fx-icon" style="font-size:{size}px" aria-hidden="true" translate="no">'
        f'{ICON_NAMES[name]}</span>'
    )


def html_block(markup):
    """Show a piece of the page's own HTML. Text from the agent is always escaped first."""
    st.markdown(markup, unsafe_allow_html=True)


def esc(value):
    """Escape text before putting it inside HTML (the agent's text is never trusted as HTML)."""
    return html.escape(str(value))


def rupees(amount):
    """Format a whole-rupee amount from the back end, for example 1001 -> Rs 1,001."""
    return f"&#8377;{int(amount):,}"


def nice_date(iso_text):
    """Turn 2026-11-03 into 'Tuesday, 03 Nov 2026'. Unknown text is shown as it is."""
    try:
        return datetime.strptime(iso_text, "%Y-%m-%d").strftime("%A, %d %b %Y")
    except (TypeError, ValueError):
        return str(iso_text)


def short_date(iso_text):
    try:
        return datetime.strptime(iso_text, "%Y-%m-%d").strftime("%a, %d %b %Y")
    except (TypeError, ValueError):
        return str(iso_text)


def slot_label(slot):
    if slot in SLOT_TIMES:
        return f"{slot} ({SLOT_TIMES[slot]})"
    return slot


def now_label():
    """Current time for chat timestamps, for example 10:21 AM."""
    return datetime.now().strftime("%I:%M %p").lstrip("0")


# ---------------------------------------------------------------------------
# Supplied data (read only)
# ---------------------------------------------------------------------------

@st.cache_data
def load_css():
    return CSS_FILE.read_text(encoding="utf-8")


@st.cache_data(show_spinner=False)
def technician_photo():
    """The technician portrait, cropped to head and shoulders and made smaller (done once).

    Returns JPEG bytes, or None if the image file is missing or cannot be read.
    """
    try:
        with Image.open(TECHNICIAN_IMAGE) as image:
            image = image.convert("RGB")
            width, height = image.size
            # Keep the top of the portrait in a 4:5 frame so the face stays in view
            crop_height = min(height, int(width * 1.25))
            image = image.crop((0, 0, width, crop_height))
            image.thumbnail((440, 550))
            buffer = io.BytesIO()
            image.save(buffer, format="JPEG", quality=85)
            return buffer.getvalue()
    except (OSError, ValueError):
        return None


@st.cache_data
def load_services():
    return json.loads((DATA_DIR / "services.json").read_text(encoding="utf-8"))


@st.cache_data
def load_service_areas():
    return json.loads((DATA_DIR / "service_areas.json").read_text(encoding="utf-8"))


@st.cache_data
def load_policies():
    return (DATA_DIR / "policies.md").read_text(encoding="utf-8")


def gas_safety_message():
    """The exact gas leak safety message from policies.md."""
    match = re.search(r'Gas leaks.*?Tell the customer: "(.*?)"', load_policies(), re.DOTALL)
    if match:
        return match.group(1)
    return ""


def unsupported_work():
    """Short names of the work FixIt does not do, read from policies.md."""
    items = []
    in_section = False
    for line in load_policies().splitlines():
        if line.startswith("## "):
            in_section = line.strip() == "## Work we do not do"
            continue
        if in_section and line.startswith("- "):
            text = line[2:].replace("**", "")
            # Keep the part before the first bracket or full stop
            text = re.split(r"\s\(|\.\s|\.$", text)[0]
            items.append(text)
    return items


def zone_for_pin(pin_code):
    """The zone (inner or outer) of a PIN code in service_areas.json, or "" if not listed."""
    for area in load_service_areas():
        if area["pin_code"] == pin_code:
            return area["zone"]
    return ""


def services_by_category():
    groups = {}
    for service in load_services():
        groups.setdefault(service["category"], []).append(service)
    return groups


# ---------------------------------------------------------------------------
# Back end calls (FastAPI)
# ---------------------------------------------------------------------------

BACKEND_DOWN = (
    "The FixIt booking service is temporarily unavailable. "
    "Please make sure the back end is running and try again in a moment."
)


# The health check and the bookings list are cached for a few seconds so that clicking
# around the page does not call the back end on every rerun. The bookings cache is
# cleared as soon as the agent answers, so a new booking or cancellation shows at once.
@st.cache_data(ttl=10, show_spinner=False)
def backend_online():
    try:
        return requests.get(f"{API_URL}/health", timeout=3).status_code == 200
    except requests.exceptions.RequestException:
        return False


@st.cache_data(ttl=10, show_spinner=False)
def fetch_bookings():
    """Return (bookings, error message). Bookings always come from GET /bookings."""
    try:
        response = requests.get(f"{API_URL}/bookings", timeout=10)
    except requests.exceptions.RequestException:
        return None, BACKEND_DOWN
    if response.status_code != 200:
        return None, "Bookings could not be loaded right now. Please try again shortly."
    try:
        bookings = response.json()
    except ValueError:
        return None, "Bookings could not be loaded right now. Please try again shortly."
    if not isinstance(bookings, list):
        return None, "Bookings could not be loaded right now. Please try again shortly."
    return bookings, ""


def ask_agent(message):
    """Send the customer's message to POST /request. Returns (result, error message)."""
    try:
        response = requests.post(f"{API_URL}/request", json={"message": message}, timeout=REQUEST_TIMEOUT)
    except requests.exceptions.Timeout:
        return None, "The assistant is taking longer than expected. Please try again."
    except requests.exceptions.RequestException:
        return None, BACKEND_DOWN

    if response.status_code == 400:
        return None, "Please type a message before sending."
    if response.status_code == 422:
        return None, "That request could not be read. Please rephrase it and try again."
    if response.status_code != 200:
        return None, "Something went wrong on our side. Please try again in a moment."
    try:
        result = response.json()
    except ValueError:
        return None, "Something went wrong on our side. Please try again in a moment."
    if not isinstance(result, dict) or "status" not in result:
        return None, "Something went wrong on our side. Please try again in a moment."
    return result, ""


def find_booking(booking_id):
    """Look up a saved booking by ID so the card can show the real customer details."""
    if not booking_id:
        return None
    bookings, error = fetch_bookings()
    if error:
        return None
    for booking in bookings:
        if booking.get("booking_id") == booking_id:
            return booking
    return None


# ---------------------------------------------------------------------------
# Session state and actions
# ---------------------------------------------------------------------------

def greeting_message():
    return {"role": "assistant", "kind": "greeting", "time": now_label()}


def init_session():
    defaults = {
        "page": "chat",
        "messages": [greeting_message()],
        "pending": None,
        "composer_text": "",
        "service_filter": "All",
    }
    for name, value in defaults.items():
        if name not in st.session_state:
            st.session_state[name] = value


def is_busy():
    """True while a request is waiting for the agent (all buttons are disabled then)."""
    return st.session_state.pending is not None


def go_to(page):
    st.session_state.page = page


def use_starter(starter_key):
    """Put a starter message in the message box and open the chat."""
    st.session_state.composer_text = STARTERS[starter_key]
    st.session_state.page = "chat"


def use_text(text):
    st.session_state.composer_text = text
    st.session_state.page = "chat"


def show_category(category):
    st.session_state.service_filter = CATEGORY_INFO[category]["label"]
    st.session_state.page = "services"


def submit_message(text):
    """Add the customer's message to the chat and queue it for the back end."""
    text = text.strip()
    if text == "" or is_busy():
        return
    st.session_state.messages.append({"role": "user", "text": text, "time": now_label()})
    st.session_state.pending = text
    st.session_state.page = "chat"


def retry_message(text):
    """Send the last message again after an error, without repeating it in the chat."""
    if not is_busy():
        st.session_state.pending = text


def clear_chat():
    """Clear the conversation on screen. Saved bookings are not touched."""
    st.session_state.messages = [greeting_message()]
    st.session_state.pending = None


def on_shortcut():
    choice = st.session_state.get("shortcut")
    if choice:
        use_starter(choice)
    st.session_state.shortcut = None


def process_pending_request():
    """Send the queued message to the agent, then store its answer in the chat."""
    text = st.session_state.pending
    # Clear the queue first so the same message is never sent twice
    st.session_state.pending = None

    result, error = ask_agent(text)
    # The agent may have booked or cancelled something, so read the bookings again
    fetch_bookings.clear()
    backend_online.clear()
    if error:
        st.session_state.messages.append(
            {"role": "assistant", "kind": "error", "text": error, "retry": text, "time": now_label()}
        )
    else:
        booking = None
        if result.get("status") in ("booked", "cancelled"):
            booking = find_booking(result.get("booking_id", ""))
        st.session_state.messages.append(
            {"role": "assistant", "kind": "agent", "result": result, "booking": booking, "time": now_label()}
        )


# ---------------------------------------------------------------------------
# HTML builders for the chat
# ---------------------------------------------------------------------------

def message_row(role, inner_html, time_text, wide=False):
    avatar_icon = "bot" if role == "assistant" else "user"
    avatar_class = "bot" if role == "assistant" else "user"
    row_class = "bot" if role == "assistant" else "user"
    body_class = "fx-body wide" if wide else "fx-body"
    return (
        f'<div class="fx-msg {row_class}">'
        f'<div class="fx-avatar {avatar_class}">{icon(avatar_icon, 17)}</div>'
        f'<div class="{body_class}">{inner_html}<div class="fx-time">{esc(time_text)}</div></div>'
        f'</div>'
    )


def greeting_html():
    abilities = [
        "Get a price quote for any repair service",
        "Book a home repair visit",
        "Check available time slots",
        "Cancel an existing booking",
        "Answer questions about our services and policies",
    ]
    items = "".join(f"<li>{icon('check', 16)}{esc(item)}</li>" for item in abilities)
    return (
        '<div class="fx-bubble bot"><p>Hi! I am your FixIt assistant. I can help you:</p>'
        f'<ul>{items}</ul><p>How can I help you today?</p></div>'
    )


def detail_row(icon_name, label, value):
    return (
        f'<div class="fx-detail-row">{icon(icon_name, 15)}'
        f'<span class="fx-detail-label">{esc(label)}</span>'
        f'<span class="fx-detail-value">{esc(value)}</span></div>'
    )


def price_box(result, total_label, zone=""):
    """Price lines exactly as the back end returned them."""
    visit_label = f"Visit charge ({zone.title()} zone)" if zone else "Visit charge"
    rows = [
        ("Service price", result.get("job_price", 0)),
        (visit_label, result.get("visit_charge", 0)),
        ("Weekend extra", result.get("weekend_extra", 0)),
        ("GST (18%)", result.get("gst", 0)),
    ]
    lines = "".join(
        f'<div class="fx-price-row"><span>{label}</span><b>{rupees(value)}</b></div>' for label, value in rows
    )
    return (
        f'<div class="fx-price"><div class="fx-price-title">Price breakdown</div>{lines}'
        f'<div class="fx-price-total"><span>{total_label}</span><b>{rupees(result.get("total_price", 0))}</b></div></div>'
    )


def booked_card(result, booking):
    details = [
        detail_row("wrench", "Service", result.get("service_name", "")),
        detail_row("calendar", "Date", nice_date(result.get("date", ""))),
        detail_row("clock", "Time slot", slot_label(result.get("slot", ""))),
    ]
    # Customer details come from the saved booking, never from guesses
    zone = ""
    if booking:
        details.append(detail_row("user", "Customer", booking.get("name", "")))
        details.append(detail_row("phone", "Phone", booking.get("phone", "")))
        area_text = f"{booking.get('area', '')}, {booking.get('pin_code', '')}"
        # The zone comes from service_areas.json, looked up by the booking's PIN code
        zone = zone_for_pin(booking.get("pin_code", ""))
        if zone:
            area_text += f" ({zone.title()} zone)"
        details.append(detail_row("pin", "Area", area_text))
    return (
        '<div class="fx-result success">'
        '<div class="fx-result-head">'
        f'<div class="fx-result-title">{icon("check", 26)}<div><strong>Booking Confirmed</strong>'
        '<span>Your visit has been scheduled.</span></div></div>'
        f'<div class="fx-result-id"><span>Booking ID</span><strong>{esc(result.get("booking_id", ""))}</strong></div>'
        '</div>'
        f'<div class="fx-result-grid"><div class="fx-details">{"".join(details)}</div>'
        f'{price_box(result, "Total amount", zone)}</div>'
        f'<div class="fx-result-foot">{icon("info", 15)}Keep your booking ID to change or cancel this visit.</div>'
        '</div>'
    )


def quote_card(result):
    details = (
        detail_row("wrench", "Service", result.get("service_name", ""))
        + detail_row("calendar", "Date", nice_date(result.get("date", "")))
    )
    return (
        '<div class="fx-result quote">'
        '<div class="fx-result-head">'
        f'<div class="fx-result-title">{icon("tag", 22)}<div><strong>Price Estimate</strong>'
        '<span>No booking has been made.</span></div></div></div>'
        f'<div class="fx-result-grid"><div class="fx-details">{details}</div>'
        f'{price_box(result, "Estimated total")}</div>'
        f'<div class="fx-result-foot">{icon("info", 15)}To book this visit, send your name, mobile number, '
        'PIN code and preferred slot.</div>'
        '</div>'
    )


def cancelled_card(result, booking):
    fee = result.get("cancellation_fee", 0)
    fee_note = "No fee, cancelled before the day of the visit." if fee == 0 else "Same-day cancellation fee."
    details = [
        detail_row("wrench", "Service", result.get("service_name", "")),
        detail_row("calendar", "Date", nice_date(result.get("date", ""))),
        detail_row("clock", "Time slot", slot_label(result.get("slot", ""))),
    ]
    if booking:
        details.append(detail_row("user", "Customer", booking.get("name", "")))
    return (
        '<div class="fx-result cancel">'
        '<div class="fx-result-head">'
        f'<div class="fx-result-title">{icon("calendar-x", 22)}<div><strong>Booking Cancelled</strong>'
        '<span>The time slot is free again.</span></div></div>'
        f'<div class="fx-result-id"><span>Booking ID</span><strong>{esc(result.get("booking_id", ""))}</strong></div>'
        '</div>'
        f'<div class="fx-result-grid"><div class="fx-details">{"".join(details)}</div>'
        f'<div class="fx-price"><div class="fx-price-title">Cancellation fee</div>'
        f'<div class="fx-fee">{rupees(fee)}</div><div class="fx-price-row"><span>{fee_note}</span></div></div>'
        '</div></div>'
    )


def agent_message_html(message):
    """Build the chat bubble (and card) for one answer from the back end."""
    result = message["result"]
    status = result.get("status", "")
    text = esc(result.get("message", ""))

    if status == "booked":
        inner = f'<div class="fx-bubble bot"><p>{text}</p></div>' + booked_card(result, message.get("booking"))
        return message_row("assistant", inner, message["time"], wide=True)
    if status == "quote_only":
        inner = f'<div class="fx-bubble bot"><p>{text}</p></div>' + quote_card(result)
        return message_row("assistant", inner, message["time"], wide=True)
    if status == "cancelled":
        inner = f'<div class="fx-bubble bot"><p>{text}</p></div>' + cancelled_card(result, message.get("booking"))
        return message_row("assistant", inner, message["time"], wide=True)

    # need_more_info, cannot_help and stopped get a labelled notice
    safety_text = gas_safety_message()
    if status == "cannot_help" and safety_text and safety_text in result.get("message", ""):
        label, tone, icon_name = "Safety notice", "amber", "alert"
    elif status == "need_more_info":
        label, tone, icon_name = "More details needed", "amber", "info"
    elif status == "cannot_help":
        label, tone, icon_name = "We cannot help with this request", "gray", "x-circle"
    else:
        label, tone, icon_name = "Request stopped", "red", "alert"
    inner = (
        f'<div class="fx-bubble bot notice-{tone}">'
        f'<div class="fx-status-label {tone}">{icon(icon_name, 15)}{label}</div><p>{text}</p></div>'
    )
    return message_row("assistant", inner, message["time"])


def error_message_html(message):
    inner = (
        '<div class="fx-bubble bot notice-red">'
        f'<div class="fx-status-label red">{icon("alert", 15)}Service unavailable</div>'
        f'<p>{esc(message["text"])}</p></div>'
    )
    return message_row("assistant", inner, message["time"])


def typing_html():
    inner = (
        '<div class="fx-bubble bot"><span class="fx-typing">FixIt Assistant is working on your request'
        '<span class="fx-dots"><span></span><span></span><span></span></span></span></div>'
    )
    return message_row("assistant", inner, now_label())


# ---------------------------------------------------------------------------
# Page parts
# ---------------------------------------------------------------------------

def render_styles():
    # Streamlit rebuilds the page on every rerun, so the stylesheet is re-sent each time.
    # The file itself is read from disk only once (cached).
    html_block(f"<style>{load_css()}</style>")


def render_header():
    features = [
        ("shield", "Verified Technicians", "Trained professionals"),
        ("calendar", "Flexible Time Slots", "Morning, Afternoon, Evening"),
        ("pin", "Pune Coverage", "Inner and outer zones"),
        ("headset", "Help & Support", "Ask the assistant anytime"),
    ]
    feature_html = "".join(
        f'<div class="fx-feature"><div class="fx-feature-icon">{icon(name, 17)}</div>'
        f'<div><div class="fx-feature-title">{esc(title)}</div><div class="fx-feature-sub">{esc(sub)}</div></div></div>'
        for name, title, sub in features
    )
    # The outer div lets the stylesheet adapt the header to its own width (container query)
    html_block(
        '<div class="fx-header-wrap"><div class="fx-header">'
        f'<div class="fx-brand"><div class="fx-brand-mark">{icon("house", 22)}</div>'
        '<div><div class="fx-brand-name">FixIt</div><div class="fx-brand-sub">Home Services</div></div></div>'
        '<div class="fx-header-divider"></div>'
        '<div><div class="fx-tagline-title">Your Home. Our Experts.</div>'
        '<div class="fx-tagline-sub">Reliable home repair services across Pune</div></div>'
        f'<div class="fx-header-features">{feature_html}</div>'
        '</div></div>'
    )


def render_sidebar(busy):
    with st.sidebar:
        html_block('<div class="fx-side-label">Menu</div>')
        with st.container(key="nav", gap=None):
            for page, title, description, nav_icon in NAV_ITEMS:
                active = st.session_state.page == page
                # Two-line label: the title, then a short description (styled in styles.css)
                st.button(
                    f"{title}  \n{description}", key=f"nav_{page}", icon=nav_icon,
                    type="primary" if active else "secondary", width="stretch",
                    on_click=go_to, args=(page,), disabled=busy,
                )

        with st.container(key="popular_head", horizontal=True, horizontal_alignment="distribute",
                          vertical_alignment="center"):
            html_block('<div class="fx-side-title">Popular Services</div>')
            st.button("View all", icon=":material/arrow_forward:", icon_position="right", key="popular_all",
                      type="tertiary", on_click=go_to, args=("services",), disabled=busy)
        with st.container(key="popular", gap=None):
            for category, services in services_by_category().items():
                info = CATEGORY_INFO.get(category, {"label": category.title(), "icon": ":material/build:"})
                st.button(
                    f"{info['label']}  \n{len(services)} services", key=f"popular_{category}", icon=info["icon"],
                    width="stretch", on_click=show_category, args=(category,), disabled=busy,
                )

        # Booking week and slots, as written in policies.md
        first_day = BOOKING_WEEK[0].strftime("%a %d %b")
        last_day = BOOKING_WEEK[-1].strftime("%a %d %b %Y")
        html_block(
            f'<div class="fx-side-note">{icon("calendar", 16)}<div><strong>Booking week</strong>'
            f'{first_day} to {last_day}<br>Morning, Afternoon and Evening slots</div></div>'
        )


def render_chat_panel(busy, online):
    with st.container(key="card_chat"):
        # Keyed so the stylesheet can keep the title and Clear chat on one row on phones
        with st.container(key="chat_head"):
            head_left, head_right = st.columns([5, 1.3], vertical_alignment="center")
        status_pill = (
            '<span class="fx-pill online"><span class="fx-pill-dot"></span>Online</span>' if online
            else '<span class="fx-pill offline"><span class="fx-pill-dot"></span>Offline</span>'
        )
        with head_left:
            html_block(
                '<div class="fx-chat-head">'
                f'<div class="fx-bot-mark">{icon("bot", 22)}</div>'
                f'<div><div class="fx-chat-title"><h2>FixIt Assistant</h2>{status_pill}'
                '<span class="fx-pill ai">Powered by AI</span></div>'
                '<div class="fx-chat-desc">Your AI assistant for home repair services</div></div>'
                '</div>'
            )
        with head_right:
            st.button("Clear Chat", icon=":material/delete:", key="clear_chat", type="secondary",
                      on_click=clear_chat, disabled=busy, help="Clears this conversation. Saved bookings are kept.")

        # The fixed height makes the conversation scroll inside the card. styles.css adjusts
        # it to the screen height (and to half the screen on phones).
        with st.container(key="chat_scroll", height=560, autoscroll=True):
            for message in st.session_state.messages:
                if message["role"] == "user":
                    inner = f'<div class="fx-bubble user"><p>{esc(message["text"])}</p></div>'
                    html_block(message_row("user", inner, message["time"]))
                elif message["kind"] == "greeting":
                    html_block(message_row("assistant", greeting_html(), message["time"]))
                elif message["kind"] == "error":
                    html_block(error_message_html(message))
                else:
                    html_block(agent_message_html(message))

            last = st.session_state.messages[-1]
            if not busy and last.get("kind") == "error":
                st.button("Try again", icon=":material/refresh:", key="retry",
                          on_click=retry_message, args=(last["retry"],))

            if busy:
                html_block(typing_html())

        render_composer(busy)


def render_composer(busy):
    with st.container(key="composer_box"):
        with st.form("composer", clear_on_submit=True, border=False):
            text_col, send_col = st.columns([6, 1], vertical_alignment="bottom")
            with text_col:
                typed_text = st.text_input(
                    "Message", key="composer_text", label_visibility="collapsed",
                    placeholder="Type your message here... (e.g., get a quote, book a service, check slots)",
                    disabled=busy,
                )
            with send_col:
                sent = st.form_submit_button("Send", icon=":material/send:", type="primary", disabled=busy)
        if sent:
            submit_message(typed_text)
            st.rerun()

        st.pills(
            "Shortcuts", [key for key, _ in SHORTCUTS], key="shortcut",
            format_func=lambda key: dict(SHORTCUTS)[key], label_visibility="collapsed",
            on_change=on_shortcut, disabled=busy,
        )


def render_service_info():
    """Promotional card with the technician portrait from assets/technician.png."""
    # Every benefit is stated in data/policies.md
    benefits = [
        ("engineering", "Trained professionals"),   # "sends trained plumbers, electricians..."
        ("rupee", "Transparent pricing"),           # "The price is the same for every customer"
        ("clock", "Flexible time slots"),           # Morning, Afternoon and Evening slots
        ("shield", "30-day warranty"),              # "All repairs have a 30-day warranty"
    ]
    items = "".join(f'<li>{icon(name, 16)}<span>{label}</span></li>' for name, label in benefits)
    photo = technician_photo()
    with st.container(key="card_service_info"):
        text_col, photo_col = st.columns([1.35, 1], gap="small", vertical_alignment="center")
        with text_col:
            html_block(
                '<div class="fx-promo-text"><h3>Professional Home Repair Services</h3>'
                '<p>Skilled technicians for repairs at your home in Pune.</p>'
                f'<ul class="fx-benefits">{items}</ul></div>'
            )
        with photo_col:
            if photo:
                st.image(photo, width="stretch", alt="FixIt technician in a blue FixIt uniform with a tool belt")
            else:
                # The photo file is missing or unreadable: show a plain placeholder, not another image
                html_block(f'<div class="fx-photo-missing">{icon("engineering", 34)}<span>Photo unavailable</span></div>')


def render_quick_actions(busy):
    with st.container(key="card_quick_actions"):
        html_block('<div class="fx-card-title">Quick Actions</div>')
        # styles.css lays these buttons out as an even two-column grid
        with st.container(key="qa_grid", gap=None):
            st.button("Get a Price Quote", icon=":material/currency_rupee:", key="qa_quote", width="stretch",
                      on_click=use_starter, args=("quote",), disabled=busy)
            st.button("Book a Service", icon=":material/event_available:", key="qa_book", width="stretch",
                      on_click=go_to, args=("book",), disabled=busy)
            st.button("Check Availability", icon=":material/schedule:", key="qa_slots", width="stretch",
                      on_click=use_starter, args=("slots",), disabled=busy)
            st.button("Cancel a Booking", icon=":material/event_busy:", key="qa_cancel", width="stretch",
                      on_click=use_starter, args=("cancel",), disabled=busy)
            st.button("View Supported Services", icon=":material/grid_view:", key="qa_services", width="stretch",
                      on_click=go_to, args=("services",), disabled=busy)


def booking_card_html(booking):
    info = CATEGORY_INFO.get(booking.get("category", ""), {"svg": "wrench"})
    if booking.get("status") == "cancelled":
        pill = '<span class="fx-pill cancelled">Cancelled</span>'
        amount = f'<span class="fx-booking-meta">Fee {rupees(booking.get("cancellation_fee") or 0)}</span>'
    else:
        pill = '<span class="fx-pill confirmed">Confirmed</span>'
        amount = f'<span class="fx-booking-total">{rupees(booking.get("total_price", 0))}</span>'
    return (
        '<div class="fx-booking">'
        f'<div class="fx-booking-icon">{icon(info["svg"], 18)}</div>'
        f'<div><div class="fx-booking-id">{esc(booking.get("booking_id", ""))}</div>'
        f'<div class="fx-booking-service">{esc(booking.get("service_name", ""))}</div>'
        f'<div class="fx-booking-meta">{icon("calendar", 12)}<span>{esc(short_date(booking.get("date", "")))}</span>'
        f'<span class="fx-dot-sep">&middot;</span><span>{esc(booking.get("slot", ""))}</span></div></div>'
        f'<div class="fx-booking-side">{pill}{amount}</div>'
        '</div>'
    )


def render_recent_bookings(busy):
    with st.container(key="card_recent"):
        with st.container(key="recent_head", horizontal=True, horizontal_alignment="distribute",
                          vertical_alignment="center"):
            html_block('<div class="fx-card-title">Recent Bookings</div>')
            st.button("View All", icon=":material/arrow_forward:", icon_position="right", key="recent_all",
                      type="tertiary", on_click=go_to, args=("bookings",), disabled=busy)
        bookings, error = fetch_bookings()
        if error:
            html_block(f'<div class="fx-empty">{icon("alert", 22)}<strong>Bookings unavailable</strong>{esc(error)}</div>')
        elif not bookings:
            html_block(
                f'<div class="fx-empty">{icon("inbox", 24)}<strong>No bookings yet</strong>'
                'Bookings you make with the assistant will appear here.</div>'
            )
        else:
            newest_first = list(reversed(bookings))[:3]
            html_block("".join(booking_card_html(booking) for booking in newest_first))


def render_safety_notice(busy):
    with st.container(key="card_safety"):
        items = ", ".join(item[0].lower() + item[1:] if index else item for index, item in enumerate(unsupported_work()))
        safety = gas_safety_message()
        html_block(
            f'<div class="fx-safety">{icon("alert", 20)}<div><strong>Important Safety Notice</strong>'
            f'<p>We do not do: {esc(items)}.</p>'
            f'<p><b>Gas leak?</b> {esc(safety)}</p></div></div>'
        )
        st.button("View all policies", icon=":material/arrow_forward:", icon_position="right", key="safety_more",
                  type="tertiary", on_click=go_to, args=("policies",), disabled=busy)


def render_page_title(title, subtitle):
    html_block(f'<div class="fx-section-title">{esc(title)}</div><div class="fx-section-sub">{esc(subtitle)}</div>')


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

def page_chat(busy, online):
    # The keys let the stylesheet move the side panel below the chat on tablets
    with st.container(key="chat_layout"):
        chat_col, side_col = st.columns([1.9, 1], gap="medium")
        with chat_col:
            render_chat_panel(busy, online)
        with side_col:
            with st.container(key="side_panel"):
                render_service_info()
                render_quick_actions(busy)
                render_recent_bookings(busy)
                render_safety_notice(busy)


def page_book(busy):
    render_page_title("Book a Service", "Fill in the details. The assistant checks the slot and confirms the booking in the chat.")
    services = load_services()
    areas = load_service_areas()
    with st.container(key="card_book"):
        with st.form("book_form", border=False):
            first, second = st.columns(2)
            with first:
                service = st.selectbox(
                    "Service", services, index=None, placeholder="Choose a service",
                    format_func=lambda item: f"{item['name']} ({CATEGORY_INFO.get(item['category'], {}).get('label', item['category'])})",
                )
                day = st.selectbox(
                    "Day", BOOKING_WEEK, index=None, placeholder="Choose a day in the booking week",
                    format_func=lambda item: item.strftime("%A, %d %b %Y"),
                )
                slot = st.selectbox("Time slot", list(SLOT_TIMES), index=None, placeholder="Choose a slot",
                                    format_func=slot_label)
            with second:
                name = st.text_input("Your name", max_chars=80)
                phone = st.text_input("Mobile number", max_chars=14, placeholder="10-digit mobile number")
                area = st.selectbox(
                    "PIN code", areas, index=None, placeholder="Choose your area",
                    format_func=lambda item: f"{item['pin_code']} - {item['area']}",
                )
            st.caption("Electricians do not work on Sundays. Prices and availability are confirmed by the assistant.")
            send = st.form_submit_button("Send booking request", type="primary", icon=":material/send:", disabled=busy)

    if send:
        missing = []
        for label, value in [("service", service), ("day", day), ("time slot", slot),
                             ("name", name.strip()), ("mobile number", phone.strip()), ("PIN code", area)]:
            if not value:
                missing.append(label)
        if missing:
            st.warning("Please fill in: " + ", ".join(missing) + ".")
        else:
            message = (
                f"Please book a {service['name']} on {day.strftime('%A')} {slot.lower()}. "
                f"Name: {name.strip()}. Mobile: {phone.strip()}. PIN code: {area['pin_code']}."
            )
            submit_message(message)
            st.rerun()


def page_services(busy):
    render_page_title("Our Services", "Service prices from our price list. The visit charge and GST are added to every visit.")
    labels = ["All"] + [CATEGORY_INFO.get(category, {"label": category})["label"] for category in services_by_category()]
    st.pills("Category", labels, key="service_filter", label_visibility="collapsed")
    chosen = st.session_state.service_filter or "All"

    for category, services in services_by_category().items():
        info = CATEGORY_INFO.get(category, {"label": category.title(), "svg": "wrench"})
        if chosen not in ("All", info["label"]):
            continue
        html_block(f'<div class="fx-card-title" style="margin-top:10px">{esc(info["label"])}</div>')
        columns = st.columns(3)
        for index, service in enumerate(services):
            with columns[index % 3]:
                with st.container(key=f"card_service_{service['service_id']}"):
                    html_block(
                        f'<div class="fx-service"><div class="fx-booking-icon">{icon(info["svg"], 18)}</div><div>'
                        f'<div class="fx-service-name">{esc(service["name"])}</div>'
                        f'<div class="fx-service-about">{esc(service["about"])}</div>'
                        f'<div class="fx-service-price">Service price <b>{rupees(service["price"])}</b></div>'
                        '</div></div>'
                    )
                    st.button("Ask for a price", key=f"price_{service['service_id']}", icon=":material/currency_rupee:",
                              on_click=use_text, args=(f"How much would a {service['name'].lower()} cost on ",),
                              disabled=busy, width="stretch")


def page_areas():
    render_page_title("Service Areas", "We visit these PIN codes in Pune. The visit charge depends on the zone.")
    areas = load_service_areas()
    zone_columns = st.columns(2, gap="medium")
    for column, zone in zip(zone_columns, ["inner", "outer"]):
        zone_areas = [area for area in areas if area["zone"] == zone]
        if not zone_areas:
            continue
        rows = "".join(
            f'<div class="fx-area-row"><span>{esc(area["area"])}</span>'
            f'<span class="fx-area-pin">{esc(area["pin_code"])}</span></div>'
            for area in zone_areas
        )
        with column:
            with st.container(key=f"card_zone_{zone}"):
                html_block(
                    f'<div class="fx-panel-head"><div><div class="fx-card-title">{zone.title()} zone</div>'
                    f'<div class="fx-card-sub">{len(zone_areas)} areas</div></div>'
                    f'<div style="text-align:right"><div class="fx-zone-charge">{rupees(zone_areas[0]["visit_charge"])}</div>'
                    '<div class="fx-card-sub">visit charge</div></div></div>'
                    f'<div style="margin-top:8px">{rows}</div>'
                )
    st.info("Your PIN code is not listed? We do not serve that area yet.", icon=":material/info:")


def page_bookings(busy):
    title_col, button_col = st.columns([4, 1], vertical_alignment="bottom")
    with title_col:
        render_page_title("All Bookings", "Loaded from the booking service (GET /bookings).")
    with button_col:
        st.button("Refresh", icon=":material/refresh:", key="refresh_bookings", disabled=busy,
                  on_click=fetch_bookings.clear)

    bookings, error = fetch_bookings()
    if error:
        st.error(error, icon=":material/cloud_off:")
        return
    if not bookings:
        with st.container(key="card_bookings_empty"):
            html_block(
                f'<div class="fx-empty" style="border:none">{icon("inbox", 28)}<strong>No bookings yet</strong>'
                'Book a visit with the assistant and it will appear here.</div>'
            )
        st.button("Open the assistant", icon=":material/forum:", on_click=go_to, args=("chat",), disabled=busy)
        return

    confirmed = [booking for booking in bookings if booking.get("status") == "booked"]
    cancelled = [booking for booking in bookings if booking.get("status") == "cancelled"]
    with st.container(key="card_booking_stats", horizontal=True, gap="large"):
        for label, value in [("Total bookings", len(bookings)), ("Confirmed", len(confirmed)), ("Cancelled", len(cancelled))]:
            html_block(f'<div class="fx-stat"><b>{value}</b>{label}</div>')

    view = st.segmented_control("Show", ["All", "Confirmed", "Cancelled"], default="All", key="booking_view")
    if view == "Confirmed":
        rows = confirmed
    elif view == "Cancelled":
        rows = cancelled
    else:
        rows = bookings

    table = []
    for booking in reversed(rows):
        table.append({
            "Booking ID": booking.get("booking_id", ""),
            "Status": "Cancelled" if booking.get("status") == "cancelled" else "Confirmed",
            "Customer": booking.get("name", ""),
            "Phone": booking.get("phone", ""),
            "Service": booking.get("service_name", ""),
            "Date": short_date(booking.get("date", "")),
            "Slot": booking.get("slot", ""),
            "Area": f"{booking.get('area', '')} ({booking.get('pin_code', '')})",
            "Total": booking.get("total_price", 0),
            "Cancellation fee": booking.get("cancellation_fee") or 0,
        })
    st.dataframe(
        table, hide_index=True, width="stretch",
        column_config={
            "Total": st.column_config.NumberColumn("Total", format="₹%d"),
            "Cancellation fee": st.column_config.NumberColumn("Cancellation fee", format="₹%d"),
        },
    )


def page_policies():
    render_page_title("Policies & Safety", "The company rules, from data/policies.md.")
    safety = gas_safety_message()
    if safety:
        st.warning(f"**Gas leak?** {safety}", icon=":material/warning:")
    with st.container(key="card_policies"):
        st.markdown(load_policies())


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    st.set_page_config(
        page_title="FixIt Home Services",
        page_icon=":material/home_repair_service:",
        layout="wide",
    )
    init_session()
    render_styles()
    busy = is_busy()
    online = backend_online()

    render_sidebar(busy)
    render_header()

    page = st.session_state.page
    if page == "chat":
        page_chat(busy, online)
    elif page == "book":
        page_book(busy)
    elif page == "services":
        page_services(busy)
    elif page == "areas":
        page_areas()
    elif page == "bookings":
        page_bookings(busy)
    else:
        page_policies()

    # The page above is drawn with everything disabled, then the request is sent.
    if busy:
        process_pending_request()
        st.rerun()


# Streamlit runs this file as "__main__". The check lets the tests import the helper
# functions (for example technician_photo) without drawing the page.
if __name__ == "__main__":
    main()
