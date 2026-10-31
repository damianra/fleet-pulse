"""Schemas Pydantic de FleetPulse — In para payloads de escritura, Out
para respuestas (from_attributes lee directo de las entities).

Los enums viven como Literal acá (las columnas son String). Los
datetimes de entrada se normalizan a naive-UTC (NaiveDT) para que las
comparaciones en sqlite y postgres sean consistentes."""
from datetime import date, datetime, timezone
from typing import Annotated, Literal, Optional

from pydantic import (AliasChoices, BaseModel, ConfigDict, Field,
                      AfterValidator)


def _naive_utc(v):
    if isinstance(v, datetime) and v.tzinfo is not None:
        return v.astimezone(timezone.utc).replace(tzinfo=None)
    return v


NaiveDT = Annotated[datetime, AfterValidator(_naive_utc)]


class Location(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


# ---------- auth / users ----------

ROLE = Literal['admin', 'dispatcher', 'driver', 'viewer']


class RegisterIn(BaseModel):
    email: str
    password: str
    full_name: str = ''
    role: Optional[ROLE] = None  # solo la respeta un admin autenticado


class LoginIn(BaseModel):
    email: str
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    full_name: str
    role: str
    is_active: bool
    last_login: Optional[datetime] = None
    created_at: Optional[datetime] = None


class ProfileUpdateIn(BaseModel):
    full_name: Optional[str] = None


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str


class UserAdminUpdateIn(BaseModel):
    role: Optional[ROLE] = None
    is_active: Optional[bool] = None
    full_name: Optional[str] = None


# ---------- vehicles ----------

VEHICLE_TYPE = Literal['truck', 'van', 'car', 'motorcycle']
FUEL_TYPE = Literal['diesel', 'gasoline', 'electric', 'hybrid']
VEHICLE_STATUS = Literal['available', 'in_route', 'maintenance', 'out_of_service']


class VehicleIn(BaseModel):
    plate: str = Field(min_length=1, max_length=20)
    type: VEHICLE_TYPE = 'van'
    brand: str = ''
    model: str = ''
    year: Optional[int] = Field(default=None, ge=1900, le=2100)
    capacity_kg: Optional[float] = None
    capacity_m3: Optional[float] = None
    fuel_type: FUEL_TYPE = 'diesel'
    status: VEHICLE_STATUS = 'available'
    mileage: int = Field(default=0, ge=0)


class VehicleUpdateIn(BaseModel):
    plate: Optional[str] = None
    type: Optional[VEHICLE_TYPE] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = Field(default=None, ge=1900, le=2100)
    capacity_kg: Optional[float] = None
    capacity_m3: Optional[float] = None
    fuel_type: Optional[FUEL_TYPE] = None
    status: Optional[VEHICLE_STATUS] = None
    mileage: Optional[int] = Field(default=None, ge=0)


class VehicleOut(VehicleIn):
    model_config = ConfigDict(from_attributes=True)

    id: str
    lat: Optional[float] = None
    lng: Optional[float] = None
    last_location_update: Optional[datetime] = None
    assigned_driver_id: Optional[str] = None
    is_active: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class AssignDriverIn(BaseModel):
    driver_id: Optional[str] = None  # null = desasignar


# ---------- drivers ----------

DRIVER_STATUS = Literal['available', 'on_duty', 'off_duty', 'suspended']


class DriverIn(BaseModel):
    user_id: Optional[str] = None
    license_number: str = Field(min_length=1, max_length=50)
    license_type: str = ''
    license_expiration: Optional[date] = None
    phone: str = ''
    emergency_contact: Optional[dict] = None
    certifications: Optional[list] = None
    status: DRIVER_STATUS = 'available'
    shift_start: Optional[str] = None
    shift_end: Optional[str] = None


class DriverUpdateIn(BaseModel):
    user_id: Optional[str] = None
    license_number: Optional[str] = None
    license_type: Optional[str] = None
    license_expiration: Optional[date] = None
    phone: Optional[str] = None
    emergency_contact: Optional[dict] = None
    certifications: Optional[list] = None
    rating: Optional[float] = Field(default=None, ge=0, le=5)
    status: Optional[DRIVER_STATUS] = None
    shift_start: Optional[str] = None
    shift_end: Optional[str] = None


class DriverOut(DriverIn):
    model_config = ConfigDict(from_attributes=True)

    id: str
    rating: float
    total_deliveries: int
    current_vehicle_id: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ShiftOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    driver_id: str
    shift_date: Optional[date] = None
    start_time: datetime
    end_time: Optional[datetime] = None
    total_hours: Optional[float] = None
    vehicle_id: Optional[str] = None
    notes: str = ''


class StartShiftIn(BaseModel):
    vehicle_id: Optional[str] = None
    notes: str = ''


# ---------- routes ----------

ROUTE_TYPE = Literal['fixed', 'dynamic', 'optimized']
ROUTE_STATUS = Literal['planned', 'in_progress', 'completed', 'cancelled']


class RouteIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ''
    type: ROUTE_TYPE = 'dynamic'
    origin_lat: float = Field(ge=-90, le=90)
    origin_lng: float = Field(ge=-180, le=180)
    destination_lat: float = Field(ge=-90, le=90)
    destination_lng: float = Field(ge=-180, le=180)
    waypoints: Optional[list] = None
    assigned_vehicle_id: Optional[str] = None
    assigned_driver_id: Optional[str] = None
    planned_start: Optional[NaiveDT] = None
    planned_end: Optional[NaiveDT] = None


class RouteUpdateIn(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    type: Optional[ROUTE_TYPE] = None
    origin_lat: Optional[float] = Field(default=None, ge=-90, le=90)
    origin_lng: Optional[float] = Field(default=None, ge=-180, le=180)
    destination_lat: Optional[float] = Field(default=None, ge=-90, le=90)
    destination_lng: Optional[float] = Field(default=None, ge=-180, le=180)
    waypoints: Optional[list] = None
    status: Optional[ROUTE_STATUS] = None
    assigned_vehicle_id: Optional[str] = None
    assigned_driver_id: Optional[str] = None
    planned_start: Optional[NaiveDT] = None
    planned_end: Optional[NaiveDT] = None


class RouteOut(RouteIn):
    model_config = ConfigDict(from_attributes=True)

    id: str
    status: str
    total_distance_km: Optional[float] = None
    estimated_duration_minutes: Optional[int] = None
    actual_start: Optional[datetime] = None
    actual_end: Optional[datetime] = None
    optimization_data: Optional[dict] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class OptimizeIn(BaseModel):
    algorithm: Literal['nearest_neighbor', 'genetic', 'simulated_annealing'] = 'nearest_neighbor'
    constraints: dict = Field(default_factory=dict)
    priorities: dict = Field(default_factory=dict)


class AddDeliveryIn(BaseModel):
    delivery_id: str


# ---------- deliveries ----------

PRIORITY = Literal['low', 'medium', 'high', 'urgent']
DELIVERY_STATUS = Literal['pending', 'in_transit', 'delivered', 'failed', 'rescheduled']


class DeliveryIn(BaseModel):
    order_number: str = Field(min_length=1, max_length=50)
    customer_name: str = ''
    customer_phone: str = ''
    customer_email: str = ''
    delivery_address: dict = Field(default_factory=dict)
    delivery_window_start: Optional[NaiveDT] = None
    delivery_window_end: Optional[NaiveDT] = None
    priority: PRIORITY = 'medium'
    packages: Optional[list] = None
    special_instructions: str = ''
    required_signature: bool = True
    sla_deadline: Optional[NaiveDT] = None
    notes: str = ''
    route_id: Optional[str] = None


class DeliveryUpdateIn(BaseModel):
    order_number: Optional[str] = None
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    customer_email: Optional[str] = None
    delivery_address: Optional[dict] = None
    delivery_window_start: Optional[NaiveDT] = None
    delivery_window_end: Optional[NaiveDT] = None
    priority: Optional[PRIORITY] = None
    packages: Optional[list] = None
    special_instructions: Optional[str] = None
    required_signature: Optional[bool] = None
    sla_deadline: Optional[NaiveDT] = None
    notes: Optional[str] = None


class DeliveryOut(DeliveryIn):
    model_config = ConfigDict(from_attributes=True)

    id: str
    status: str
    proof_of_delivery: Optional[dict] = None
    actual_delivery_time: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class CompleteDeliveryIn(BaseModel):
    signature_url: Optional[str] = None
    photo_urls: list[str] = Field(default_factory=list)
    notes: str = ''
    delivered_at: Optional[NaiveDT] = None


class FailDeliveryIn(BaseModel):
    reason: str = ''


class RescheduleDeliveryIn(BaseModel):
    delivery_window_start: Optional[NaiveDT] = None
    delivery_window_end: Optional[NaiveDT] = None
    sla_deadline: Optional[NaiveDT] = None
    notes: str = ''


class ProofIn(BaseModel):
    signature_url: Optional[str] = None
    photo_urls: list[str] = Field(default_factory=list)
    notes: str = ''


# ---------- tracking ----------

ENGINE_STATUS = Literal['on', 'off', 'idle']


class TrackingUpdateIn(BaseModel):
    vehicle_id: str
    driver_id: Optional[str] = None
    location: Location
    speed_kmh: Optional[float] = Field(default=None, ge=0)
    heading: Optional[float] = Field(default=None, ge=0, lt=360)
    timestamp: Optional[NaiveDT] = None
    accuracy_meters: Optional[float] = None
    battery_level: Optional[int] = Field(default=None, ge=0, le=100)
    engine_status: Optional[ENGINE_STATUS] = None
    fuel_level: Optional[float] = Field(default=None, ge=0, le=100)
    metadata: Optional[dict] = None


class TrackingEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: str
    vehicle_id: str
    driver_id: Optional[str] = None
    lat: float
    lng: float
    speed_kmh: Optional[float] = None
    heading: Optional[float] = None
    timestamp: datetime
    accuracy_meters: Optional[float] = None
    battery_level: Optional[int] = None
    engine_status: Optional[str] = None
    fuel_level: Optional[float] = None
    metadata: Optional[dict] = Field(
        default=None,
        validation_alias=AliasChoices('event_metadata', 'metadata'))


class TrackingEventArchiveOut(TrackingEventOut):
    archived_at: Optional[datetime] = None


# ---------- alerts ----------

ALERT_TYPE = Literal['sla_breach', 'route_deviation', 'maintenance_due',
                     'driver_fatigue', 'geofence_violation', 'speed_violation']
ALERT_SEVERITY = Literal['low', 'medium', 'high', 'critical']
ALERT_STATUS = Literal['active', 'acknowledged', 'resolved']


class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: str
    type: str
    severity: str
    title: str
    description: str = ''
    status: str
    vehicle_id: Optional[str] = None
    driver_id: Optional[str] = None
    route_id: Optional[str] = None
    delivery_id: Optional[str] = None
    triggered_at: Optional[datetime] = None
    acknowledged_at: Optional[datetime] = None
    acknowledged_by: Optional[str] = None
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None
    resolution_notes: str = ''
    metadata: Optional[dict] = Field(
        default=None,
        validation_alias=AliasChoices('alert_metadata', 'metadata'))


class ResolveAlertIn(BaseModel):
    notes: str = ''


# ---------- maintenance ----------

MAINT_TYPE = Literal['preventive', 'corrective', 'inspection']
MAINT_STATUS = Literal['scheduled', 'in_progress', 'completed', 'cancelled']


class MaintenanceIn(BaseModel):
    vehicle_id: str
    type: MAINT_TYPE = 'preventive'
    description: str = ''
    scheduled_date: Optional[date] = None
    cost: Optional[float] = None
    provider: str = ''
    mileage_at_service: Optional[int] = None
    next_service_mileage: Optional[int] = None
    next_service_date: Optional[date] = None
    status: MAINT_STATUS = 'scheduled'
    documents: Optional[list] = None
    notes: str = ''


class MaintenanceUpdateIn(BaseModel):
    type: Optional[MAINT_TYPE] = None
    description: Optional[str] = None
    scheduled_date: Optional[date] = None
    cost: Optional[float] = None
    provider: Optional[str] = None
    mileage_at_service: Optional[int] = None
    next_service_mileage: Optional[int] = None
    next_service_date: Optional[date] = None
    status: Optional[MAINT_STATUS] = None
    documents: Optional[list] = None
    notes: Optional[str] = None


class MaintenanceOut(MaintenanceIn):
    model_config = ConfigDict(from_attributes=True)

    id: str
    completed_date: Optional[date] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ---------- geofences ----------

GEOFENCE_RULE = Literal['enter', 'exit']


class GeofenceIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ''
    polygon: list[Location] = Field(min_length=3)
    rule: GEOFENCE_RULE = 'enter'
    severity: ALERT_SEVERITY = 'medium'
    vehicle_id: Optional[str] = None  # null = aplica a toda la flota
    is_active: bool = True


class GeofenceUpdateIn(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    polygon: Optional[list[Location]] = Field(default=None, min_length=3)
    rule: Optional[GEOFENCE_RULE] = None
    severity: Optional[ALERT_SEVERITY] = None
    vehicle_id: Optional[str] = None
    is_active: Optional[bool] = None


class GeofenceOut(GeofenceIn):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

# ---------- métricas diarias ----------


class DailyMetricOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    metric_date: date
    data: dict
    computed_at: datetime


class SnapshotIn(BaseModel):
    day: Optional[date] = None  # default: hoy (UTC) — `day` evita el
    # shadowing del tipo `date` en la propia anotación (pydantic)
