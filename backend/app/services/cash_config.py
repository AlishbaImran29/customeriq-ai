"""Settings of the Cash Tracker, in one place."""

# A courier is flagged when a delivered parcel's COD money has been unpaid for MORE than this many days.
# The page lets the seller pick another value; this is the default.
ALERT_DAYS = 14

# How old unpaid parcels are grouped (days since delivery): 0-7, 8-14, 15 or more.
BUCKET_EDGES = (7, 14)
