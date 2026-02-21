from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel


class PerformanceTime(BaseModel):
    date: str
    time: str


class TheatreData(BaseModel):
    title: str
    venue_url: str
    category: str
    venue: str
    address: str
    city: str
    country: str
    open_date: Optional[datetime] = None
    close_date: Optional[datetime] = None
    booking_start_date: Optional[datetime] = None
    booking_end_date: Optional[datetime] = None
    upcoming_performances: Optional[List[PerformanceTime]] = None
    capacity: Optional[int] = None
    currency: Optional[str] = None
    seat_pricing: Optional[Dict] = None
    scrape_datetime: Optional[datetime] = None
