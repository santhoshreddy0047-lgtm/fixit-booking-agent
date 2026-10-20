# FixIt Home Services: Booking Rules

FixIt Home Services (a made-up company) sends trained plumbers, electricians, AC technicians and carpenters to homes in Pune.

## Booking week

- Today is **Monday, 2 November 2026**.
- Bookings are open for this week only: **Monday 2 November to Sunday 8 November 2026**.
- Every day has three time slots:
  - Morning: 9 am to 12 pm
  - Afternoon: 12 pm to 3 pm
  - Evening: 3 pm to 6 pm
- Each slot has one technician for each type of work. A slot that is already booked cannot be booked again.
- Electricians do not work on Sundays.

## Details needed for a booking

A visit is booked only when we have all of these:

1. The customer's name
2. A 10-digit mobile number
3. The pin code
4. What needs fixing (so we can choose the service)
5. The date
6. The time slot (Morning, Afternoon or Evening)

If anything is missing, ask for it. Never guess a phone number, a pin code, a date or a slot.

## Where we work

We only visit the pin codes listed in `service_areas.json`.

- **Inner zone**: visit charge ₹99
- **Outer zone**: visit charge ₹149

For any other pin code, say politely that we do not serve that area yet.

## Price

To give a price we need the service, the pin code and the date (weekends cost more). A customer can ask for a price without booking.

The price is worked out like this:

1. Start with the service price (from `services.json`).
2. Add the visit charge for the zone (₹99 or ₹149).
3. On Saturday and Sunday, add a **weekend extra of ₹100**.
4. Add **GST at 18%** on the total so far, rounded to the nearest rupee.

Example: Tap repair in Kothrud (inner zone) on a Tuesday
- Service ₹199 + visit ₹99 = ₹298
- GST 18% of ₹298 = ₹53.64, rounded to ₹54
- Total: ₹352

The price is the same for every customer. There are no discounts and no free visits.

## Cancelling

- A booking can be cancelled with its booking ID (for example FX-1001).
- Cancelling **before the day of the visit** is free.
- Cancelling **on the day of the visit** costs **₹99**.
- When a booking is cancelled, its slot becomes free again.

## Work we do not do

We do not do this work. Do not book it, even if the customer asks:

- **Gas leaks** (gas pipeline or gas cylinder). Tell the customer: "For your safety, open the windows, do not switch on any lights or flames, and call your gas agency's emergency number right away."
- Work on the main electricity meter or the street pole. Ask the customer to contact their electricity provider.
- Painting, waterproofing and roof work.
- Repairs to fridges, washing machines and TVs.

## Warranty

All repairs have a 30-day warranty. If the same problem comes back within 30 days, the customer calls our office and we fix it under the warranty. The agent does not handle warranty claims.
