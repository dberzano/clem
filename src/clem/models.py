import datetime as dt

from pydantic import BaseModel, ConfigDict


class StrictModel(BaseModel):
    """Base of every model: no extra fields accepted, immutable."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class Kid(StrictModel):
    id: int
    name: str


class Registration(StrictModel):
    """One kid x activity subscription, as listed on the dashboard."""

    kid_id: int
    ins: int
    lieu: int
    clg: int
    activity: str
    place: str


class Reservation(StrictModel):
    """One booked day of one registration."""

    kid_id: int
    kid_name: str
    registration_id: int
    activity: str
    place: str
    unit: str
    date: dt.date
    quantity: int
    editable: bool


class ErrorDetail(StrictModel):
    code: str
    message: str


class ErrorOutput(StrictModel):
    error: ErrorDetail
