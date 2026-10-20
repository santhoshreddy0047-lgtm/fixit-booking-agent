"""Business tools for the FixIt booking agent.

Every function here is plain Python. The AI agent calls these functions,
but all checks and price calculations happen here, never inside the AI model.

The six tools at the bottom of the file return JSON strings. Each result has an
"ok" key, a plain-words "message" when something is wrong, and an "error_type"
that says what kind of problem it was. The tools never crash.
"""

import json
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

# File locations
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
SERVICES_FILE = DATA_DIR / "services.json"
AREAS_FILE = DATA_DIR / "service_areas.json"
SLOTS_FILE = DATA_DIR / "slots.json"
BOOKINGS_FILE = BASE_DIR / "bookings.json"

# Company rules from policies.md (these values are not in the JSON data files)
TODAY = date(2026, 11, 2)
WEEK_START = date(2026, 11, 2)
WEEK_END = date(2026, 11, 8)
VALID_SLOTS = ["Morning", "Afternoon", "Evening"]
WEEKEND_EXTRA = 100
GST_RATE = Decimal("0.18")
SAME_DAY_CANCELLATION_FEE = 99
FIRST_BOOKING_NUMBER = 1001

# Kinds of problems a tool can report (the agent uses these to choose a status)
MISSING_DETAILS = "missing_details"          # the customer left something out
INVALID_DETAILS = "invalid_details"          # bad phone, PIN format, date, slot name or category
NOT_SERVED = "not_served"                    # PIN code not in service_areas.json
UNKNOWN_SERVICE = "unknown_service"          # service ID not in services.json
SLOT_UNAVAILABLE = "slot_unavailable"        # slot or whole day already taken
ELECTRICIAN_SUNDAY = "electrician_sunday"    # electricians do not work on Sundays
UNKNOWN_BOOKING = "unknown_booking"          # no booking with that ID
ALREADY_CANCELLED = "already_cancelled"      # booking was cancelled before
SYSTEM_ERROR = "system_error"                # a data file could not be read


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def load_json(file_path):
    """Read a JSON file and return its contents."""
    with open(file_path, "r", encoding="utf-8") as file:
        return json.load(file)


def load_bookings():
    """Read bookings.json, creating an empty file if it does not exist.

    A broken file raises an error instead of being treated as empty,
    so existing bookings are never overwritten by mistake.
    """
    if not BOOKINGS_FILE.exists():
        save_bookings([])
        return []

    with open(BOOKINGS_FILE, "r", encoding="utf-8") as file:
        text = file.read()
    if text.strip() == "":
        return []

    bookings = json.loads(text)
    if not isinstance(bookings, list):
        raise ValueError("bookings.json must contain a list of bookings")
    return bookings


def save_bookings(bookings):
    """Write the full list of bookings to bookings.json."""
    with open(BOOKINGS_FILE, "w", encoding="utf-8") as file:
        json.dump(bookings, file, indent=2, ensure_ascii=False)


def problem(error_type, message):
    """Build a failed result with its kind of problem and a plain-words message."""
    return {"ok": False, "error_type": error_type, "message": message}


def clean_text(value):
    """Turn any input into a stripped string (None becomes an empty string)."""
    if value is None:
        return ""
    return str(value).strip()


def day_name_to_date(day_text):
    """Turn 'today', 'tomorrow' or a day name like 'Tuesday' into a date in the booking week."""
    day_text = day_text.lower()
    if day_text == "today":
        return TODAY
    if day_text == "tomorrow":
        return TODAY + timedelta(days=1)

    current_day = WEEK_START
    while current_day <= WEEK_END:
        if current_day.strftime("%A").lower() == day_text:
            return current_day
        current_day = current_day + timedelta(days=1)
    return None


def parse_booking_date(date_text):
    """Check a date (YYYY-MM-DD or a day name). Returns (date_object, error_message)."""
    date_text = clean_text(date_text)
    if date_text == "":
        return None, "Please provide the date for the visit."

    visit_date = day_name_to_date(date_text)
    if visit_date is None:
        try:
            visit_date = datetime.strptime(date_text, "%Y-%m-%d").date()
        except ValueError:
            return None, f"'{date_text}' is not a valid date. Use a day name like Tuesday or the format YYYY-MM-DD."

    if visit_date < WEEK_START or visit_date > WEEK_END:
        return None, "Bookings are open only from Monday 2 November to Sunday 8 November 2026. Please choose a date in this week."
    return visit_date, ""


def normalise_slot(slot_text):
    """Return the slot name with correct capitals, or an empty string if invalid."""
    slot_text = clean_text(slot_text).lower()
    for slot_name in VALID_SLOTS:
        if slot_text == slot_name.lower():
            return slot_name
    return ""


def describe_day(visit_date):
    """Format a date for messages, for example 'Saturday 2026-11-07'."""
    return f"{visit_date.strftime('%A')} {visit_date.isoformat()}"


def find_service_by_id(service_id):
    """Return the service dictionary for an ID, or None if not found."""
    service_id = clean_text(service_id).upper()
    for service in load_json(SERVICES_FILE):
        if service["service_id"] == service_id:
            return service
    return None


def find_area_by_pin(pin_code):
    """Return the service area dictionary for a PIN code, or None if not served."""
    for area in load_json(AREAS_FILE):
        if area["pin_code"] == pin_code:
            return area
    return None


def get_categories():
    """Return the list of work types found in services.json."""
    categories = []
    for service in load_json(SERVICES_FILE):
        if service["category"] not in categories:
            categories.append(service["category"])
    return categories


def is_weekend(visit_date):
    """Saturday is 5 and Sunday is 6 in Python's weekday()."""
    return visit_date.weekday() >= 5


def electrician_on_sunday(category, visit_date):
    return category == "electrician" and visit_date.weekday() == 6


def round_rupees(amount):
    """Round to the nearest rupee, with .50 always rounding up."""
    return int(Decimal(amount).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def is_slot_taken(category, date_text, slot):
    """A slot is taken if slots.json marks it booked or an active booking uses it."""
    for slot_row in load_json(SLOTS_FILE):
        if (slot_row["category"] == category and slot_row["date"] == date_text
                and slot_row["slot"] == slot and slot_row["booked"]):
            return True

    for booking in load_bookings():
        if (booking["status"] == "booked" and booking["category"] == category
                and booking["date"] == date_text and booking["slot"] == slot):
            return True
    return False


def slot_exists(category, date_text, slot):
    """Check that slots.json has a row for this category, date and slot."""
    for slot_row in load_json(SLOTS_FILE):
        if slot_row["category"] == category and slot_row["date"] == date_text and slot_row["slot"] == slot:
            return True
    return False


def free_slots_on(category, visit_date):
    """Return the free slot names for a work type on one day (empty list if none)."""
    if electrician_on_sunday(category, visit_date):
        return []

    date_text = visit_date.isoformat()
    free_slots = []
    for slot in VALID_SLOTS:
        if slot_exists(category, date_text, slot) and not is_slot_taken(category, date_text, slot):
            free_slots.append(slot)
    return free_slots


def find_other_free_day(category, visit_date):
    """Find another day in the booking week with at least one free slot.

    Looks at the days after visit_date first, then the days before it.
    Returns a dictionary with the date, day and free slots, or None if the
    whole week is full.
    """
    later_days = []
    earlier_days = []
    current_day = WEEK_START
    while current_day <= WEEK_END:
        if current_day > visit_date:
            later_days.append(current_day)
        elif current_day < visit_date:
            earlier_days.append(current_day)
        current_day = current_day + timedelta(days=1)

    # Nearest earlier day first
    earlier_days.reverse()

    for day in later_days + earlier_days:
        free_slots = free_slots_on(category, day)
        if free_slots:
            return {
                "date": day.isoformat(),
                "day": day.strftime("%A"),
                "available_slots": free_slots,
                "is_later": day > visit_date,
            }
    return None


def describe_other_free_day(category, visit_date):
    """A sentence that suggests another free day, or says the week is full."""
    other_day = find_other_free_day(category, visit_date)
    if other_day is None:
        return "There are no free slots for this type of work in the rest of the booking week."

    day_text = f"{other_day['day']} {other_day['date']}"
    slots_text = ", ".join(other_day["available_slots"])
    if other_day["is_later"]:
        return f"The next free day is {day_text} ({slots_text})."
    return f"There are no free days later in the booking week. The nearest free day is {day_text} ({slots_text})."


def next_booking_id(bookings):
    """Create the next booking ID, for example FX-1001, FX-1002."""
    highest_number = FIRST_BOOKING_NUMBER - 1
    for booking in bookings:
        number_part = booking["booking_id"].replace("FX-", "")
        if number_part.isdigit() and int(number_part) > highest_number:
            highest_number = int(number_part)
    return f"FX-{highest_number + 1}"


def to_json(result):
    """Turn a result dictionary into the JSON string returned by the tools."""
    return json.dumps(result, ensure_ascii=False)


def run_safely(tool_function, *arguments):
    """Run a business function and return its result as a JSON string.

    If a data file is missing or broken, return a clear message instead of crashing.
    """
    try:
        result = tool_function(*arguments)
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        print(f"[Tool error] {tool_function.__name__}: {type(error).__name__}: {error}")
        result = problem(SYSTEM_ERROR, "Sorry, the booking system could not read its data right now. Please try again later.")
    return to_json(result)


# ---------------------------------------------------------------------------
# Business logic
# Each function below returns a Python dictionary with an "ok" key.
# The six tools at the bottom of the file return these as JSON strings.
# ---------------------------------------------------------------------------

def get_area(pin_code):
    """Check whether FixIt serves a PIN code and return its zone and visit charge."""
    pin_code = clean_text(pin_code)
    if pin_code == "":
        return problem(MISSING_DETAILS, "Please provide your 6-digit PIN code.")
    if not (pin_code.isdigit() and len(pin_code) == 6):
        return problem(INVALID_DETAILS, f"'{pin_code}' is not a valid PIN code. A PIN code has 6 digits.")

    area = find_area_by_pin(pin_code)
    if area is None:
        return problem(NOT_SERVED, f"We do not serve pin code {pin_code} yet. Do not book a visit.")

    return {
        "ok": True,
        "pin_code": area["pin_code"],
        "area": area["area"],
        "zone": area["zone"],
        "visit_charge": area["visit_charge"],
        "message": f"We serve {area['area']} ({area['zone']} zone). Visit charge: Rs {area['visit_charge']}.",
    }


def list_services(category):
    """List services for a category. An empty category or 'all' lists every service."""
    category = clean_text(category).lower()
    services = load_json(SERVICES_FILE)
    valid_categories = get_categories()

    if category in ("", "all"):
        matching_services = services
    elif category in valid_categories:
        matching_services = []
        for service in services:
            if service["category"] == category:
                matching_services.append(service)
    else:
        return problem(INVALID_DETAILS, f"Unknown category '{category}'. Valid categories: {', '.join(valid_categories)}.")

    return {"ok": True, "services": matching_services}


def calculate_quote(service_id, pin_code, date):
    """Work out the full price for a service, area and date."""
    service = find_service_by_id(service_id)
    if service is None:
        return problem(UNKNOWN_SERVICE, f"Unknown service ID '{clean_text(service_id)}'.")

    area_result = get_area(pin_code)
    if not area_result["ok"]:
        return area_result

    visit_date, date_error = parse_booking_date(date)
    if date_error:
        return problem(INVALID_DETAILS, date_error)

    if electrician_on_sunday(service["category"], visit_date):
        message = "Electricians do not work on Sundays. " + describe_other_free_day("electrician", visit_date)
        return problem(ELECTRICIAN_SUNDAY, message)

    # Pricing steps from policies.md
    job_price = service["price"]
    visit_charge = area_result["visit_charge"]
    weekend_extra = WEEKEND_EXTRA if is_weekend(visit_date) else 0
    subtotal = job_price + visit_charge + weekend_extra
    gst = round_rupees(Decimal(subtotal) * GST_RATE)
    total_price = subtotal + gst

    return {
        "ok": True,
        "service_id": service["service_id"],
        "service_name": service["name"],
        "category": service["category"],
        "area": area_result["area"],
        "zone": area_result["zone"],
        "date": visit_date.isoformat(),
        "day": visit_date.strftime("%A"),
        "job_price": job_price,
        "visit_charge": visit_charge,
        "weekend_extra": weekend_extra,
        "subtotal": subtotal,
        "gst": gst,
        "total_price": total_price,
    }


def list_slots(category, date):
    """List the free and taken slots for a category on a date.

    When the day has no free slots, the result explains why and suggests
    another day in the booking week that has a free slot.
    """
    category = clean_text(category).lower()
    if category not in get_categories():
        return problem(INVALID_DETAILS, "Please give one category: plumber, electrician, ac_technician or carpenter.")

    visit_date, date_error = parse_booking_date(date)
    if date_error:
        return problem(INVALID_DETAILS, date_error)

    if electrician_on_sunday(category, visit_date):
        message = "Electricians do not work on Sundays. " + describe_other_free_day(category, visit_date)
        result = problem(ELECTRICIAN_SUNDAY, message)
        result["next_free_day"] = find_other_free_day(category, visit_date)
        return result

    available_slots = free_slots_on(category, visit_date)
    taken_slots = []
    for slot in VALID_SLOTS:
        if slot not in available_slots:
            taken_slots.append(slot)

    result = {
        "ok": True,
        "category": category,
        "date": visit_date.isoformat(),
        "day": visit_date.strftime("%A"),
        "available_slots": available_slots,
        "taken_slots": taken_slots,
    }

    if available_slots:
        result["message"] = f"Free slots on {describe_day(visit_date)}: {', '.join(available_slots)}."
    else:
        result["message"] = (
            f"All slots for {category} on {describe_day(visit_date)} are already booked. "
            + describe_other_free_day(category, visit_date)
        )
        result["next_free_day"] = find_other_free_day(category, visit_date)
    return result


def create_booking(name, phone, pin_code, service_id, date, slot):
    """Validate every detail, then save a new booking to bookings.json.

    If the same phone number already has a booking on that date and slot,
    nothing new is saved and the existing booking is returned.
    """
    name = clean_text(name)
    phone = clean_text(phone).replace(" ", "").replace("-", "")
    pin_code = clean_text(pin_code)
    service_id = clean_text(service_id).upper()
    date_text = clean_text(date)
    slot_name = normalise_slot(slot)
    if name.lower() in ("none", "null", "unknown"):
        name = ""

    # 1. Collect every missing detail so the customer can be asked once
    missing = []
    if name == "":
        missing.append("name")
    if phone == "":
        missing.append("10-digit mobile number")
    if pin_code == "":
        missing.append("PIN code")
    if service_id == "":
        missing.append("repair needed")
    if date_text == "":
        missing.append("date")
    if clean_text(slot) == "":
        missing.append("time slot (Morning, Afternoon or Evening)")
    if missing:
        return problem(MISSING_DETAILS, "Please provide: " + ", ".join(missing) + ".")

    # 2. Check each detail
    if not (phone.isdigit() and len(phone) == 10):
        return problem(INVALID_DETAILS, f"'{phone}' is not a valid mobile number. Please give a 10-digit number.")
    if slot_name == "":
        return problem(INVALID_DETAILS, "The time slot must be Morning, Afternoon or Evening.")

    # calculate_quote checks the service, PIN code, date and Sunday rule
    quote = calculate_quote(service_id, pin_code, date_text)
    if not quote["ok"]:
        return quote

    bookings = load_bookings()

    # 3. Same phone, date and slot already booked: return that booking, do not book again
    for booking in bookings:
        if (booking["status"] == "booked" and booking["phone"] == phone
                and booking["date"] == quote["date"] and booking["slot"] == slot_name):
            result = {"ok": True, "already_booked": True}
            result.update(booking)
            result["message"] = (
                f"This visit is already booked under booking ID {booking['booking_id']}. "
                "No new booking was made."
            )
            return result

    # 4. Make sure the technician is free
    if not slot_exists(quote["category"], quote["date"], slot_name) or \
            is_slot_taken(quote["category"], quote["date"], slot_name):
        visit_date = datetime.strptime(quote["date"], "%Y-%m-%d").date()
        free_slots = free_slots_on(quote["category"], visit_date)
        message = f"The {slot_name} slot on {describe_day(visit_date)} is already taken."
        if free_slots:
            message += " Free slots that day: " + ", ".join(free_slots) + "."
        else:
            message += " " + describe_other_free_day(quote["category"], visit_date)
        return problem(SLOT_UNAVAILABLE, message)

    # 5. Save the booking
    booking = {
        "booking_id": next_booking_id(bookings),
        "name": name,
        "phone": phone,
        "pin_code": pin_code,
        "area": quote["area"],
        "service_id": quote["service_id"],
        "service_name": quote["service_name"],
        "category": quote["category"],
        "date": quote["date"],
        "day": quote["day"],
        "slot": slot_name,
        "job_price": quote["job_price"],
        "visit_charge": quote["visit_charge"],
        "weekend_extra": quote["weekend_extra"],
        "gst": quote["gst"],
        "total_price": quote["total_price"],
        "status": "booked",
        "cancellation_fee": 0,
    }
    bookings.append(booking)
    save_bookings(bookings)

    result = {"ok": True, "already_booked": False}
    result.update(booking)
    return result


def cancel_existing_booking(booking_id):
    """Cancel a booking. Free before the visit day, Rs 99 on the visit day."""
    booking_id = clean_text(booking_id).upper()
    if booking_id == "":
        return problem(MISSING_DETAILS, "Please provide your booking ID, for example FX-1001.")

    bookings = load_bookings()
    for booking in bookings:
        if booking["booking_id"] != booking_id:
            continue

        if booking["status"] == "cancelled":
            return problem(ALREADY_CANCELLED, f"Booking {booking_id} is already cancelled.")

        visit_date = datetime.strptime(booking["date"], "%Y-%m-%d").date()
        if visit_date == TODAY:
            fee = SAME_DAY_CANCELLATION_FEE
        else:
            fee = 0

        # Marking it cancelled frees the slot, because is_slot_taken skips cancelled bookings
        booking["status"] = "cancelled"
        booking["cancellation_fee"] = fee
        save_bookings(bookings)

        result = {"ok": True}
        result.update(booking)
        return result

    return problem(UNKNOWN_BOOKING, f"No booking found with ID {booking_id}.")


# ---------------------------------------------------------------------------
# The six business tools (each returns a JSON string and never crashes)
# ---------------------------------------------------------------------------

def check_area(pin_code):
    """Check whether FixIt serves a PIN code. Returns a JSON string."""
    return run_safely(get_area, pin_code)


def find_services(category):
    """List the services for a category ('' or 'all' for every service). Returns a JSON string."""
    return run_safely(list_services, category)


def get_price_quote(service_id, pin_code, date):
    """Calculate the full price for a service, PIN code and date. Returns a JSON string."""
    return run_safely(calculate_quote, service_id, pin_code, date)


def check_slots(category, date):
    """List the free slots for a category on a date, or the next free day. Returns a JSON string."""
    return run_safely(list_slots, category, date)


def book_visit(name, phone, pin_code, service_id, date, slot):
    """Book a visit and save it to bookings.json. Returns a JSON string."""
    return run_safely(create_booking, name, phone, pin_code, service_id, date, slot)


def cancel_booking(booking_id):
    """Cancel a booking by its ID, for example FX-1001. Returns a JSON string."""
    return run_safely(cancel_existing_booking, booking_id)
