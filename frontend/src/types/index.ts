export type UserRole = 'PASSENGER' | 'DRIVER' | 'COMPANY_ADMIN' | 'EMPLOYEE' | 'OWNER' | 'ADMIN';

export interface UserProfile {
  id: number;
  full_name: string;
  email: string;
  phone: string;
  role: UserRole;
  is_active: boolean;
  passenger_id?: number;
  default_zone?: string;
  wallet_balance_aoa?: number;
  primary_card_code?: string;
  driver_id?: number;
  verification_status?: string;
  rating_avg?: number;
  company_id?: number;
  company_name?: string;
}

export interface LuandaStop {
  id: number;
  name: string;
  zone_name: string;
  latitude: number;
  longitude: number;
}

export interface QuoteResponse {
  tariff_name: string;
  distance_km: number;
  duration_min: number;
  passenger_count: number;
  fare_per_passenger_aoa: number;
  total_fare_aoa: number;
  currency: string;
}

export interface GroupMember {
  id: number;
  passenger_name: string;
  card_code: string;
  individual_fare_aoa: number;
  validation_status: string;
}

export interface TransportRequestDTO {
  id: number;
  passenger_id: number;
  passenger_name: string;
  passenger_phone?: string;
  company_id?: number;
  request_type: 'INDIVIDUAL' | 'GROUP' | 'CORPORATE';
  pickup_label: string;
  pickup_zone: string;
  pickup_lat: number;
  pickup_lng: number;
  dropoff_label: string;
  dropoff_zone: string;
  dropoff_lat: number;
  dropoff_lng: number;
  passenger_count: number;
  estimated_distance_km: number;
  estimated_duration_min: number;
  fare_per_passenger_aoa: number;
  estimated_total_fare_aoa: number;
  status: string;
  offered_driver_id?: number;
  offer_expires_at?: string;
  group_members: GroupMember[];
  created_at?: string;
}

export interface BoardedPassenger {
  id: number;
  passenger_name: string;
  card_code: string;
  fare_charged_aoa: number;
  boarding_status: string;
  boarded_at?: string;
  card_transaction_id?: number;
}

export interface TripDTO {
  id: number;
  transport_request_id: number;
  status: 'DRIVER_EN_ROUTE' | 'DRIVER_ARRIVED' | 'IN_PROGRESS' | 'COMPLETED' | 'CANCELLED';
  boarding_code: string;
  eta_minutes: number;
  fare_per_passenger_aoa: number;
  total_fare_aoa: number;
  paid_total_aoa: number;
  request?: TransportRequestDTO;
  driver?: {
    id: number;
    full_name: string;
    phone?: string;
    rating_avg: number;
    total_trips: number;
    current_lat?: number;
    current_lng?: number;
    current_zone?: string;
  };
  vehicle?: {
    id: number;
    make: string;
    model: string;
    year: number;
    color: string;
    license_plate: string;
    vehicle_type: string;
    capacity: number;
  };
  boarded_passengers: BoardedPassenger[];
  boarded_count: number;
  commission?: {
    gross_fare_aoa: number;
    platform_fee_aoa: number;
    driver_net_aoa: number;
    commission_rate: number;
  };
  rating?: {
    score: number;
    comment?: string;
  };
  accepted_at?: string;
  arrived_at?: string;
  started_at?: string;
  completed_at?: string;
}

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

export interface CardTransactionDTO {
  id: number;
  card_code?: string;
  trip_id?: number;
  tx_type: 'TOPUP_ADMIN' | 'TRIP_DEBIT' | 'REFUND' | 'ADJUSTMENT';
  amount_aoa: number;
  balance_before_aoa: number;
  balance_after_aoa: number;
  status: string;
  description: string;
  idempotency_key: string;
  created_at?: string;
}

export interface DemandPressureZone {
  zone: string;
  latitude: number;
  longitude: number;
  active_requests: number;
  historical_requests: number;
  unmet_or_cancelled: number;
  available_vehicles: number;
  pressure_ratio: number;
  pressure_level: 'ELEVADA' | 'MODERADA' | 'BAIXA';
  recommendation: string;
}

export interface NotificationDTO {
  id: number;
  title: string;
  message: string;
  category: string;
  is_read: boolean;
  created_at?: string;
}
