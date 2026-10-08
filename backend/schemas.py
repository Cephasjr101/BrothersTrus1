"""Pydantic request/response schemas."""
from datetime import date
from typing import Literal, Optional

import re

from pydantic import BaseModel, EmailStr, Field, field_validator

PHONE_RE = re.compile(r"^\+?[0-9][0-9\s\-]{6,19}$")


def _phone(v: str) -> str:
    if not PHONE_RE.match(v or ""):
        raise ValueError("contact_phone must be a valid phone number (7+ digits)")
    return v


# ------------------------------------------------------------------ auth
class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)
    full_name: str = Field(min_length=2, max_length=120)
    phone: str = Field(default="", max_length=30)
    website: Optional[str] = Field(default=None, max_length=100)  # honeypot (must stay empty)


class ForgotPasswordIn(BaseModel):
    email: EmailStr


class ResetPasswordIn(BaseModel):
    token: str = Field(min_length=20, max_length=100)
    new_password: str = Field(min_length=6, max_length=128)


class DeleteAccountIn(BaseModel):
    password: str = Field(min_length=1, max_length=128)


class FirebaseSignIn(BaseModel):
    id_token: str = Field(min_length=20, max_length=4096)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


# ------------------------------------------------------------------ flights
class FlightLegIn(BaseModel):
    origin: str = Field(min_length=3, max_length=3)
    dest: str = Field(min_length=3, max_length=3)
    date: date
    flight_key: str


class PassengerIn(BaseModel):
    type: Literal["adult", "child", "infant"] = "adult"
    title: str = "Mr"
    first_name: str = Field(min_length=1, max_length=60)
    last_name: str = Field(min_length=1, max_length=60)
    dob: Optional[date] = None


class FlightBookingIn(BaseModel):
    trip_type: Literal["one_way", "round_trip"] = "one_way"
    cabin: Literal["economy", "premium", "business", "first"] = "economy"
    legs: list[FlightLegIn] = Field(min_length=1, max_length=2)
    passengers: list[PassengerIn] = Field(min_length=1, max_length=9)
    contact_email: EmailStr
    contact_phone: str = Field(min_length=7, max_length=30)

    _v_phone = field_validator("contact_phone")(classmethod(lambda cls, v: _phone(v)))

    @field_validator("legs")
    @classmethod
    def sensible_legs(cls, legs):
        if len(legs) == 2:
            if legs[0].origin != legs[1].dest or legs[0].dest != legs[1].origin:
                raise ValueError("round-trip legs must be A->B then B->A")
            if legs[1].date < legs[0].date:
                raise ValueError("return date cannot be before departure")
        return legs


# ------------------------------------------------------------------ hotels
class HotelBookingIn(BaseModel):
    hotel_id: str
    room_type: str
    checkin: date
    checkout: date
    rooms: int = Field(ge=1, le=5)
    guests: int = Field(ge=1, le=10)
    guest_name: str = Field(min_length=2, max_length=120)
    contact_email: EmailStr
    contact_phone: str = Field(min_length=7, max_length=30)

    _v_phone = field_validator("contact_phone")(classmethod(lambda cls, v: _phone(v)))
    special_requests: str = Field(default="", max_length=500)

    @field_validator("checkout")
    @classmethod
    def after_checkin(cls, v, info):
        if "checkin" in info.data and v <= info.data["checkin"]:
            raise ValueError("checkout must be after checkin")
        return v


# ------------------------------------------------------------------ cars
class CarBookingIn(BaseModel):
    city: str
    category: str
    pickup_date: date
    return_date: date
    pickup_location: str = Field(default="Airport", max_length=120)
    driver_name: str = Field(min_length=2, max_length=120)
    driver_age: int = Field(ge=18, le=90)
    contact_email: EmailStr
    contact_phone: str = Field(min_length=7, max_length=30)

    _v_phone = field_validator("contact_phone")(classmethod(lambda cls, v: _phone(v)))

    @field_validator("return_date")
    @classmethod
    def after_pickup(cls, v, info):
        if "pickup_date" in info.data and v <= info.data["pickup_date"]:
            raise ValueError("return date must be after pickup")
        return v


# ------------------------------------------------------------------ visa
class VisaApplicantIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    passport_no: str = Field(min_length=5, max_length=20)
    dob: date


class VisaBookingIn(BaseModel):
    country_code: str = Field(min_length=2, max_length=2)
    center: str = Field(default="", max_length=120)
    date: date
    time: str = Field(min_length=4, max_length=5)
    applicants: list[VisaApplicantIn] = Field(min_length=1, max_length=6)
    contact_email: EmailStr
    contact_phone: str = Field(min_length=7, max_length=30)

    _v_phone = field_validator("contact_phone")(classmethod(lambda cls, v: _phone(v)))


# ------------------------------------------------------------------ payments
class PaymentInitIn(BaseModel):
    reference: str = Field(min_length=6)          # booking reference


class PaymentConfirmIn(BaseModel):
    reference: str                                # booking reference
    method: Literal["card", "bank_transfer", "ussd", "qr"] = "card"
