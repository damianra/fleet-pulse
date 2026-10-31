"""Entities FleetPulse — flota, conductores, rutas, entregas, tracking,
alertas, mantenimiento, turnos y usuarios.

Decisiones de portabilidad (sqlite en dev/tests, postgres en deploy via
DATABASE_URL):
- PKs UUID como String(32 hex) — no depende de extensiones de postgres.
- Enums como String validados en la capa Pydantic (schemas.py).
- Geometría como lat/lng Float o JSON ({lat,lng}) — no requiere PostGIS.
- Timestamps naive UTC (utcnow) — comparables en sqlite y postgres."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import (JSON, Boolean, Column, Date, DateTime, Float,
                        ForeignKey, Index, Integer, String, Text)
from sqlalchemy.orm import relationship

from .db import Base


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def new_id():
    return uuid.uuid4().hex


class User(Base):
    __tablename__ = 'users'

    id = Column(String(32), primary_key=True, default=new_id)
    email = Column(String(200), unique=True, nullable=False, index=True)
    hashed_password = Column(String(200), nullable=False)
    full_name = Column(String(200), default='')
    role = Column(String(20), nullable=False, default='viewer')  # admin|dispatcher|driver|viewer
    is_active = Column(Boolean, nullable=False, default=True)
    last_login = Column(DateTime)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class Vehicle(Base):
    __tablename__ = 'vehicles'

    id = Column(String(32), primary_key=True, default=new_id)
    plate = Column(String(20), unique=True, nullable=False, index=True)
    type = Column(String(20), nullable=False, default='van')  # truck|van|car|motorcycle
    brand = Column(String(100), default='')
    model = Column(String(100), default='')
    year = Column(Integer)
    capacity_kg = Column(Float)
    capacity_m3 = Column(Float)
    fuel_type = Column(String(20), default='diesel')  # diesel|gasoline|electric|hybrid
    status = Column(String(20), nullable=False, default='available')  # available|in_route|maintenance|out_of_service
    lat = Column(Float)
    lng = Column(Float)
    last_location_update = Column(DateTime)
    mileage = Column(Integer, default=0)
    assigned_driver_id = Column(String(32), ForeignKey('drivers.id'))
    is_active = Column(Boolean, nullable=False, default=True)  # soft delete
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    assigned_driver = relationship('Driver', foreign_keys=[assigned_driver_id])


class Driver(Base):
    __tablename__ = 'drivers'

    id = Column(String(32), primary_key=True, default=new_id)
    user_id = Column(String(32), ForeignKey('users.id'), unique=True)
    license_number = Column(String(50), unique=True, nullable=False)
    license_type = Column(String(20), default='')
    license_expiration = Column(Date)
    phone = Column(String(20), default='')
    emergency_contact = Column(JSON)
    certifications = Column(JSON)
    rating = Column(Float, default=0.0)
    total_deliveries = Column(Integer, default=0)
    status = Column(String(20), nullable=False, default='available')  # available|on_duty|off_duty|suspended
    current_vehicle_id = Column(String(32), ForeignKey('vehicles.id'))
    shift_start = Column(String(10))  # HH:MM
    shift_end = Column(String(10))
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    user = relationship('User')
    current_vehicle = relationship('Vehicle', foreign_keys=[current_vehicle_id])


class Route(Base):
    __tablename__ = 'routes'

    id = Column(String(32), primary_key=True, default=new_id)
    name = Column(String(200), nullable=False)
    description = Column(Text, default='')
    type = Column(String(20), nullable=False, default='dynamic')  # fixed|dynamic|optimized
    origin_lat = Column(Float, nullable=False)
    origin_lng = Column(Float, nullable=False)
    destination_lat = Column(Float, nullable=False)
    destination_lng = Column(Float, nullable=False)
    waypoints = Column(JSON)  # [{lat,lng,order,address,delivery_id}]
    total_distance_km = Column(Float)
    estimated_duration_minutes = Column(Integer)
    status = Column(String(20), nullable=False, default='planned')  # planned|in_progress|completed|cancelled
    assigned_vehicle_id = Column(String(32), ForeignKey('vehicles.id'))
    assigned_driver_id = Column(String(32), ForeignKey('drivers.id'))
    planned_start = Column(DateTime)
    planned_end = Column(DateTime)
    actual_start = Column(DateTime)
    actual_end = Column(DateTime)
    optimization_data = Column(JSON)  # {status,algorithm,params,result}
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    assigned_vehicle = relationship('Vehicle')
    assigned_driver = relationship('Driver')
    stops = relationship('RouteDelivery', back_populates='route',
                         order_by='RouteDelivery.stop_order',
                         cascade='all, delete-orphan')


class Delivery(Base):
    __tablename__ = 'deliveries'

    id = Column(String(32), primary_key=True, default=new_id)
    route_id = Column(String(32), ForeignKey('routes.id'))
    order_number = Column(String(50), unique=True, nullable=False, index=True)
    customer_name = Column(String(200), default='')
    customer_phone = Column(String(20), default='')
    customer_email = Column(String(200), default='')
    delivery_address = Column(JSON)  # {street,city,state,zip,lat,lng}
    delivery_window_start = Column(DateTime)
    delivery_window_end = Column(DateTime)
    priority = Column(String(10), nullable=False, default='medium')  # low|medium|high|urgent
    status = Column(String(20), nullable=False, default='pending')  # pending|in_transit|delivered|failed|rescheduled
    packages = Column(JSON)  # [{weight,dimensions,description,barcode}]
    special_instructions = Column(Text, default='')
    required_signature = Column(Boolean, default=True)
    proof_of_delivery = Column(JSON)  # {signature_url,photo_urls,delivered_at,notes}
    sla_deadline = Column(DateTime, index=True)
    actual_delivery_time = Column(DateTime)
    notes = Column(Text, default='')
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class RouteDelivery(Base):
    __tablename__ = 'route_deliveries'

    route_id = Column(String(32), ForeignKey('routes.id'), primary_key=True)
    delivery_id = Column(String(32), ForeignKey('deliveries.id'), primary_key=True)
    stop_order = Column(Integer, nullable=False)
    estimated_arrival = Column(DateTime)
    actual_arrival = Column(DateTime)

    route = relationship('Route', back_populates='stops')
    delivery = relationship('Delivery')


class TrackingEvent(Base):
    __tablename__ = 'tracking_events'
    __table_args__ = (Index('ix_tracking_vehicle_ts', 'vehicle_id', 'timestamp'),)

    id = Column(String(32), primary_key=True, default=new_id)
    vehicle_id = Column(String(32), ForeignKey('vehicles.id'), nullable=False)
    driver_id = Column(String(32), ForeignKey('drivers.id'))
    lat = Column(Float, nullable=False)
    lng = Column(Float, nullable=False)
    speed_kmh = Column(Float)
    heading = Column(Float)
    timestamp = Column(DateTime, nullable=False, default=utcnow)
    accuracy_meters = Column(Float)
    battery_level = Column(Integer)
    engine_status = Column(String(10))  # on|off|idle
    fuel_level = Column(Float)
    event_metadata = Column('metadata', JSON)


class TrackingEventArchive(Base):
    """Eventos de tracking vencidos por retención (TRACKING_RETENTION_DAYS)
    — app/archive.py los mueve acá para mantener tracking_events chica.
    Sin FKs: la fila sobrevive aunque se borre el vehículo/driver."""
    __tablename__ = 'tracking_events_archive'
    __table_args__ = (Index('ix_tracking_archive_vehicle_ts',
                            'vehicle_id', 'timestamp'),)

    id = Column(String(32), primary_key=True)
    vehicle_id = Column(String(32), nullable=False)
    driver_id = Column(String(32))
    lat = Column(Float, nullable=False)
    lng = Column(Float, nullable=False)
    speed_kmh = Column(Float)
    heading = Column(Float)
    timestamp = Column(DateTime, nullable=False)
    accuracy_meters = Column(Float)
    battery_level = Column(Integer)
    engine_status = Column(String(10))
    fuel_level = Column(Float)
    event_metadata = Column('metadata', JSON)
    archived_at = Column(DateTime, nullable=False, default=utcnow)


class Geofence(Base):
    __tablename__ = 'geofences'

    id = Column(String(32), primary_key=True, default=new_id)
    name = Column(String(200), nullable=False)
    description = Column(Text, default='')
    polygon = Column(JSON, nullable=False)  # [{lat,lng},...] >= 3 vértices
    rule = Column(String(10), nullable=False, default='enter')  # enter|exit
    severity = Column(String(10), nullable=False, default='medium')
    vehicle_id = Column(String(32), ForeignKey('vehicles.id'))  # null = toda la flota
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    vehicle = relationship('Vehicle')


class Alert(Base):
    __tablename__ = 'alerts'
    __table_args__ = (Index('ix_alerts_status_triggered', 'status', 'triggered_at'),)

    id = Column(String(32), primary_key=True, default=new_id)
    type = Column(String(30), nullable=False)  # sla_breach|route_deviation|maintenance_due|driver_fatigue|geofence_violation|speed_violation
    severity = Column(String(10), nullable=False, default='medium')  # low|medium|high|critical
    title = Column(String(200), nullable=False)
    description = Column(Text, default='')
    status = Column(String(15), nullable=False, default='active')  # active|acknowledged|resolved
    vehicle_id = Column(String(32), ForeignKey('vehicles.id'))
    driver_id = Column(String(32), ForeignKey('drivers.id'))
    route_id = Column(String(32), ForeignKey('routes.id'))
    delivery_id = Column(String(32), ForeignKey('deliveries.id'))
    triggered_at = Column(DateTime, default=utcnow)
    acknowledged_at = Column(DateTime)
    acknowledged_by = Column(String(32), ForeignKey('users.id'))
    resolved_at = Column(DateTime)
    resolved_by = Column(String(32), ForeignKey('users.id'))
    resolution_notes = Column(Text, default='')
    alert_metadata = Column('metadata', JSON)


class MaintenanceRecord(Base):
    __tablename__ = 'maintenance_records'

    id = Column(String(32), primary_key=True, default=new_id)
    vehicle_id = Column(String(32), ForeignKey('vehicles.id'), nullable=False)
    type = Column(String(15), nullable=False, default='preventive')  # preventive|corrective|inspection
    description = Column(Text, default='')
    scheduled_date = Column(Date)
    completed_date = Column(Date)
    cost = Column(Float)
    provider = Column(String(200), default='')
    mileage_at_service = Column(Integer)
    next_service_mileage = Column(Integer)
    next_service_date = Column(Date, index=True)
    status = Column(String(15), nullable=False, default='scheduled')  # scheduled|in_progress|completed|cancelled
    documents = Column(JSON)
    notes = Column(Text, default='')
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    vehicle = relationship('Vehicle')


class DailyMetric(Base):
    """Snapshot agregado de un día (app/metrics.py lo upsertea) — los
    endpoints /api/analytics son el "ahora"; esta tabla es la serie
    histórica para gráficos del dashboard. `data` es un dict JSON
    con las secciones deliveries/routes/alerts/tracking/drivers/
    maintenance del día."""
    __tablename__ = 'daily_metrics'

    id = Column(String(32), primary_key=True, default=new_id)
    metric_date = Column(Date, unique=True, nullable=False, index=True)
    data = Column(JSON, nullable=False)
    computed_at = Column(DateTime, nullable=False, default=utcnow)


class DriverShift(Base):
    __tablename__ = 'driver_shifts'

    id = Column(String(32), primary_key=True, default=new_id)
    driver_id = Column(String(32), ForeignKey('drivers.id'), nullable=False, index=True)
    shift_date = Column(Date)
    start_time = Column(DateTime, nullable=False, default=utcnow)
    end_time = Column(DateTime)
    total_hours = Column(Float)
    vehicle_id = Column(String(32), ForeignKey('vehicles.id'))
    notes = Column(Text, default='')

    driver = relationship('Driver')
    vehicle = relationship('Vehicle')
