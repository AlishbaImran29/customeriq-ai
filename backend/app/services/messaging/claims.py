"""Rules that keep AI-written messages honest: nothing may be invented, and claims nobody provided are removed."""

import re

NO_INVENTION = (
    "Rules: use ONLY the facts you are given. Do NOT invent numbers, prices, discounts, delivery times, stock "
    "levels, customer reviews, testimonials, star ratings, awards, or how many were sold or how many customers "
    "you have. Do not claim anything that was not given."
)

_CLAIMS = re.compile(
    r"\b\d[\d,.]*\s*\+?\s*[kKmM]?\s*(?:sold|customers?|orders?|reviews?|buyers?|ratings?|happy|sales)\b"   # "5000 sold", "10k customers"
    r"|\bonly\s+\d+\s+(?:left|pieces?|units?|remaining|in stock)\b"                                          # invented scarcity
    r"|\btestimonials?\b|\bverified buyers?\b|\bcustomers? (?:say|love|rated)\b|\breviews? say\b"
    r"|\b(?:5|five)[\s-]*stars?\b|★|⭐|\brated\s+\d|\bbest[\s-]?sellers?\b|\bas seen on\b|(?<!\w)#1\b",
    re.IGNORECASE,
)


def unprovable_claim(text: str) -> bool:
    """True when the text makes a claim the seller never provided: a sold count, a review, a rating, fake scarcity."""
    return bool(_CLAIMS.search(text))
