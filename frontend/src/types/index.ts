export type UserRole = 'PASSENGER' | 'DRIVER' | 'FIELD_COLLECTOR' | 'ADMIN' | 'COMPANY_ADMIN' | 'EMPLOYEE' | 'OWNER';

export interface UserProfile {
  id: number;
  full_name: string;
  email: string;
  phone: string;
  role: UserRole;
  is_active: boolean;
  passenger_id?: number;
  default_zone?: string;
  driver_id?: number;
  verification_status?: string;
  rating_avg?: number;
}

export interface MunicipalityDTO {
  id: number;
  name: string;
  province: string;
}

export interface TransportZoneDTO {
  id: number;
  name: string;
  neighborhood: string;
  municipality: string;
  latitude: number;
  longitude: number;
}

export interface TaxiStopDTO {
  id: number;
  zone_id: number;
  zone_name: string;
  name: string;
  landmark?: string;
  latitude: number;
  longitude: number;
  is_validated: boolean;
  estimated_demand?: number;
  total_supply?: number;
  demand_level?: string;
}

export interface GeographyDTO {
  municipalities: MunicipalityDTO[];
  neighborhoods: { id: number; name: string; municipality_id: number }[];
  zones: TransportZoneDTO[];
  stops: TaxiStopDTO[];
  routes: {
    id: number;
    code: string;
    name: string;
    origin_zone: string;
    destination_zone: string;
    road_condition: string;
    corridor_description?: string;
  }[];
}

export interface CorridorStatusDTO {
  route_id?: number | null;
  route_code?: string;
  route_name: string;
  corridor_description?: string;
  origin_zone: string;
  destination_zone: string;
  municipality?: string;
  neighborhood?: string;
  origin_lat?: number;
  origin_lng?: number;
  destination_lat?: number;
  destination_lng?: number;
  has_sufficient_data: boolean;
  status_message?: string | null;
  estimated_demand: number;
  declared_demand: number;
  confirmed_demand: number;
  declared_supply: number;
  observed_supply: number;
  total_supply: number;
  demand_supply_ratio?: number | null;
  ratio_disclaimer: string;
  demand_level: 'PROCURA_ELEVADA' | 'PROCURA_MODERADA' | 'PROCURA_BAIXA' | 'INSUFFICIENT_DATA';
  supply_level: 'OFERTA_ELEVADA' | 'OFERTA_MODERADA' | 'OFERTA_REDUZIDA' | 'INSUFFICIENT_DATA';
  imbalance?: boolean;
  balance_label: string;
  driver_advisory: string;
  passenger_advisory: string;
  estimated_wait_min?: number | null;
  road_condition: string;
  freshness_status: 'RECENT' | 'STALE' | 'EXPIRED';
  confidence_level: 'HIGH' | 'MEDIUM' | 'LOW';
  validation_state: string;
  sources: string[];
  contains_demo_data: boolean;
  last_updated_at?: string | null;
  trend: string;
  distance_from_origin_km?: number;
  alternatives?: CorridorStatusDTO[];
}

export interface IntentionDTO {
  id: number;
  route_id?: number | null;
  origin_stop_id: number;
  destination_stop_id: number;
  origin_zone: string;
  destination_zone: string;
  passenger_count: number;
  status: 'DECLARED' | 'CONFIRMED_AT_STOP' | 'CANCELLED' | 'EXPIRED';
  source_type: string;
  validation_status: string;
  confidence_level: string;
  freshness_status: 'RECENT' | 'STALE' | 'EXPIRED';
  age_minutes: number;
  notes?: string | null;
  is_demo_data: boolean;
  last_confirmed_at?: string | null;
  expires_at?: string | null;
  created_at?: string | null;
}

export interface DriverReportDTO {
  id: number;
  origin_zone: string;
  destination_zone: string;
  availability_status: 'AVAILABLE' | 'AT_STOP' | 'EN_ROUTE' | 'UNAVAILABLE';
  estimated_seats: number;
  freshness_status: 'RECENT' | 'STALE' | 'EXPIRED';
  age_minutes: number;
  last_confirmed_at: string;
  expires_at: string;
}

export interface DriverInfoOverviewDTO {
  safety_notice: string;
  my_report: DriverReportDTO | null;
  routes: CorridorStatusDTO[];
  top_destinations: {
    destination: string;
    estimated_demand: number;
    total_supply: number;
    routes_count: number;
  }[];
  peak_hours: { hour: string; passengers: number }[];
  server_time_luanda: string;
}

export interface HistoricalAnalyticsDTO {
  demand_by_municipality: { name: string; passengers: number }[];
  demand_by_neighborhood: { name: string; passengers: number }[];
  demand_by_stop: { name: string; passengers: number }[];
  demand_by_destination: { name: string; passengers: number }[];
  demand_by_weekday: { day: string; passengers: number }[];
  demand_by_hour: { hour: string; passengers: number }[];
  avg_wait_min?: number | null;
  unmet_or_cancelled_intentions: number;
  data_quality: {
    total_records: number;
    validated_pct: number;
    stale_or_expired_pct: number;
    pending_validations: number;
    suspicious_records: number;
  };
  snapshots_count: number;
  predictive_model_note: string;
}

// Preserved legacy DTOs (disabled in active MVP per Section 3 & 14)
export interface TransportCardDTO {
  id: number;
  card_code: string;
  qr_token: string;
  card_technology: string;
  nfc_uid?: string;
  status: 'ACTIVE' | 'BLOCKED' | 'LOST' | 'REVOKED';
  block_reason?: string;
  balance_aoa: number;
  currency: string;
  passenger_id?: number;
  passenger_name: string;
  passenger_email?: string;
  issued_at?: string;
}

export interface TransportRequestDTO {
  id: number;
  pickup_zone: string;
  dropoff_zone: string;
  dropoff_lat: number;
  dropoff_lng: number;
  passenger_count: number;
  estimated_total_fare_aoa: number;
  status: string;
  created_at?: string;
}

export interface TripDTO {
  id: number;
  status: string;
  paid_total_aoa: number;
  total_fare_aoa: number;
}

