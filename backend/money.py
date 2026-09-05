"""Money representation helpers.

All monetary values in Financial Doctor are stored and computed as **integer minor units**
(for INR, paise). No financial value ever uses floating point.

    ₹1.00  == 100 paise
    ₹94,200 == 9,420,000 paise
"""

from __future__ import annotations

MINOR_UNITS: dict[str, int] = {
    "INR": 100,
    "USD": 100,
    "EUR": 100,
}

DEFAULT_CURRENCY = "INR"


def minor_units_per_unit(currency: str) -> int:
    """Return the number of minor units in one major unit for ``currency``."""
    if currency not in MINOR_UNITS:
        raise ValueError(f"Unsupported currency: {currency}")
    return MINOR_UNITS[currency]


def rupees_to_minor(rupees: int, currency: str = DEFAULT_CURRENCY) -> int:
    """Convert an integer number of major units to minor units.

    ``rupees`` must be an integer; fractional major units are never produced internally.
    """
    if not isinstance(rupees, int):
        raise TypeError(f"rupees must be an int, got {type(rupees).__name__}")
    return rupees * minor_units_per_unit(currency)


def minor_to_major(minor: int, currency: str = DEFAULT_CURRENCY) -> int:
    """Convert minor units to whole major units, truncating any remainder."""
    if not isinstance(minor, int):
        raise TypeError(f"minor must be an int, got {type(minor).__name__}")
    return minor // minor_units_per_unit(currency)


def sum_minor(values: list[int]) -> int:
    """Sum integer minor units exactly (no floating point)."""
    return sum(values)


def format_minor(minor: int, currency: str = DEFAULT_CURRENCY) -> str:
    """Format minor units as a human-readable money string (no precision loss)."""
    if not isinstance(minor, int):
        raise TypeError(f"minor must be an int, got {type(minor).__name__}")
    factor = minor_units_per_unit(currency)
    sign = "-" if minor < 0 else ""
    abs_minor = abs(minor)
    whole, frac = divmod(abs_minor, factor)
    return f"{sign}{currency} {whole}.{frac:02d}"