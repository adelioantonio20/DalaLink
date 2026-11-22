from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


# --- Auth ---
class RegisterRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=140)
    email: EmailStr
    phone: str = Field(min_length=8, max_length=32)
    password: str = Field(min_length=6, max_length=128)
    role: str = Field(default="PASSENGER")  # PASSENGER, DRIVER, COMPANY_ADMIN
    # Optional driver fields
    license_number: Optional[str] = None
    national_id: Optional[str] = None
    vehicle_make: Optional[str] = None
    vehicle_model: Optional[str] = None
    vehicle_plate: Optional[str] = None
    vehicle_color: Optional[str] = "Branco"
    vehicle_capacity: int = 4
    # Optional corporate fields
    company_name: Optional[str] = None
    company_nif: Optional[str] = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


# --- Quotes & Transport Requests ---
class QuoteRequest(BaseModel):
    pickup_lat: float
    pickup_lng: float
    dropoff_lat: float
    dropoff_lng: float
    passenger_count: int = Field(default=1, ge=1, le=20)


class CreateTransportRequest(BaseModel):
    pickup_label: str = Field(min_length=2, max_length=160)
    pickup_zone: str = Field(min_length=2, max_length=80)
    pickup_lat: float
    pickup_lng: float
    dropoff_label: str = Field(min_length=2, max_length=160)
    dropoff_zone: str = Field(min_length=2, max_length=80)
    dropoff_lat: float
    dropoff_lng: float
    passenger_count: int = Field(default=1, ge=1, le=20)
    request_type: str = Field(default="INDIVIDUAL")  # INDIVIDUAL, GROUP, CORPORATE
    companion_card_codes: list[str] = Field(default_factory=list)
    include_requester_card: bool = True


# --- Driver Operations ---
class DriverStatusUpdate(BaseModel):
    status: str  # AVAILABLE, BUSY, OFFLINE
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    zone_name: Optional[str] = None


class DriverLocationUpdate(BaseModel):
    latitude: float
    longitude: float
    heading: Optional[float] = None
    speed_kmh: Optional[float] = 28.0
    zone_name: Optional[str] = None


class RegisterVehicleRequest(BaseModel):
    make: str = Field(min_length=2, max_length=60)
    model: str = Field(min_length=1, max_length=60)
    year: int = Field(default=2023, ge=1995, le=2030)
    color: str = Field(default="Branco", max_length=40)
    license_plate: str = Field(min_length=5, max_length=32)
    vehicle_type: str = Field(default="TAXI_SEDAN")
    capacity: int = Field(default=4, ge=1, le=60)


class ValidateBoardingRequest(BaseModel):
    card_identifier: str = Field(min_length=3, max_length=160)  # MOB-000001 or signed QR token
    idempotency_key: Optional[str] = None


class RateTripRequest(BaseModel):
    score: int = Field(ge=1, le=5)
    comment: Optional[str] = Field(default=None, max_length=500)


# --- Cards & Wallet Admin ---
class CardTopupRequest(BaseModel):
    card_code: str
    amount_aoa: Decimal = Field(gt=0)
    description: str = "Carregamento administrativo"
    idempotency_key: Optional[str] = None


class CardStatusRequest(BaseModel):
    status: str  # ACTIVE, BLOCKED, LOST, REVOKED
    reason: Optional[str] = None


class RefundRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=300)


class VerifyDriverRequest(BaseModel):
    verification_status: str  # APPROVED, REJECTED, SUSPENDED
    notes: Optional[str] = None


# --- Corporate ---
class AddEmployeeRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=140)
    email: EmailStr
    department: str = "Operações"
    pickup_zone: str = "Talatona"
    dropoff_zone: str = "Aeroporto"
    shift_time: str = "17:00"


class CreateCorporateRouteRequest(BaseModel):
    name: str = Field(min_length=3, max_length=140)
    origin_zone: str
    destination_zone: str
    scheduled_time: str = "17:00"
    notes: Optional[str] = None


class CorporateBatchDispatchRequest(BaseModel):
    origin_zone: str = "Talatona"
    shift_time: str = "17:00"
    destination_zone: Optional[str] = None
    max_vehicle_capacity: int = Field(default=12, ge=2, le=50)


class EmployeeStatusUpdate(BaseModel):
    status: str  # INVITED, ACTIVE, SUSPENDED


class CreateRecurringBookingRequest(BaseModel):
    route_id: int
    days_of_week: str = "SEG,TER,QUA,QUI,SEX"
    shift_time: str = "17:00"
    vehicle_capacity_hint: int = Field(default=12, ge=2, le=50)


class UpdateSubscriptionRequest(BaseModel):
    plan_name: str = Field(min_length=3, max_length=80)
    max_employees: int = Field(ge=5, le=2000)
    monthly_fee_aoa: Decimal = Field(gt=0)
    status: str = "ACTIVE"  # ACTIVE, PAUSED


class AddRouteStopRequest(BaseModel):
    name: str = Field(min_length=2, max_length=140)
    zone_name: str
    latitude: float
    longitude: float
    sequence_order: int = 1


# --- Phase 4: NFC, Admin Card Issuance & Fleet Owner ---
class BindNfcRequest(BaseModel):
    nfc_uid: str = Field(min_length=4, max_length=64)
    card_technology: str = "QR+NFC"  # NFC, QR+NFC


class IssueCardAdminRequest(BaseModel):
    passenger_id: int
    initial_balance_aoa: Decimal = Field(default=Decimal("0.00"), ge=0)
    nfc_uid: Optional[str] = None


class AssignVehicleDriverRequest(BaseModel):
    driver_id: Optional[int] = None
    is_active: Optional[bool] = None

