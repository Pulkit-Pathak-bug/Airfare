"""Core data types for the fare index collector.

The field list is driven by the PS, which requires the database to carry
"origin, destination, carrier, advance-purchase window, fare-class, base
fare, taxes and total fare". Components are nullable because most portals
only expose the split at a later step of the booking funnel -- record what
you can see, and let the cleaning layer decide what to do about the rest.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional


@dataclass(frozen=True)
class FareOffer:
    """A single observed one-way fare."""

    origin: str                 # IATA, e.g. "DEL"
    destination: str            # IATA, e.g. "BOM"
    departure_date: date
    collection_date: date
    total_fare_inr: float       # what the traveller actually pays
    source_portal: str          # adapter name, e.g. "serpapi", "indigo"

    carrier: Optional[str] = None
    depart_time_local: Optional[str] = None   # "HH:MM", disambiguates offers
    fare_class: Optional[str] = None          # cabin / fare family
    flight_number: Optional[str] = None

    # PS-mandated decomposition. None means "portal did not expose it",
    # which is different from zero and must stay distinguishable.
    base_fare_inr: Optional[float] = None
    taxes_inr: Optional[float] = None
    udf_inr: Optional[float] = None            # user development fee
    convenience_fee_inr: Optional[float] = None

    is_refundable: Optional[bool] = None
    raw: Optional[dict] = field(default=None, repr=False, compare=False)

    @property
    def advance_window_days(self) -> int:
        """The axis the whole index is built on."""
        return (self.departure_date - self.collection_date).days

    @property
    def components_sum(self) -> Optional[float]:
        parts = [self.base_fare_inr, self.taxes_inr, self.udf_inr,
                 self.convenience_fee_inr]
        known = [p for p in parts if p is not None]
        return sum(known) if known else None

    def validate(self) -> None:
        if self.advance_window_days < 0:
            raise ValueError(
                f"departure {self.departure_date} precedes collection "
                f"{self.collection_date}"
            )
        if not (self.total_fare_inr > 0):
            raise ValueError(f"non-positive fare: {self.total_fare_inr}")
        if len(self.origin) != 3 or len(self.destination) != 3:
            raise ValueError(f"bad IATA pair: {self.origin}-{self.destination}")
        for name in ("base_fare_inr", "taxes_inr", "udf_inr",
                     "convenience_fee_inr"):
            value = getattr(self, name)
            if value is not None and value < 0:
                raise ValueError(f"negative {name}: {value}")
