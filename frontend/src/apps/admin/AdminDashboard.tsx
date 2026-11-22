import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Activity,
  Ban,
  BarChart3,
  Car,
  CheckCircle2,
  CreditCard,
  FileSearch,
  Filter,
  Link2,
  Map as MapIcon,
  PlusCircle,
  RefreshCw,
  RotateCcw,
  ShieldCheck,
  TrendingUp,
  Wallet,
  Wifi,
} from 'lucide-react';
import { DemandCircleItem, LuandaMap, MapMarkerItem } from '../../components/LuandaMap';
import { TopBar } from '../../components/TopBar';
import { useAuth } from '../../contexts/AuthContext';
import { apiRequest, formatAOA, formatLuandaTime } from '../../services/api';
import {
  CardTransactionDTO,
  DemandPressureZone,
  LuandaStop,
  TransportCardDTO,
  TransportRequestDTO,
  TripDTO,
} from '../../types';

interface AdminOverviewDTO {
  kpis: {
    passengers_registered: number;
    drivers_registered: number;
    drivers_approved: number;
    drivers_pending_verification: number;
    active_vehicles: number;
    available_vehicles: number;
    pending_requests: number;
    active_trips: number;
    completed_trips: number;
    cancelled_requests: number;
    gross_revenue_aoa: number;
    platform_commissions_aoa: number;
    total_cards_balance_aoa: number;
    active_cards: number;
    blocked_cards: number;
    partner_companies: number;
  };
  map_data: {
    vehicles: {
      driver_id: number;
      driver_name: string;
      verification_status: string;
      status: string;
      latitude: number;
      longitude: number;
      zone: string;
      vehicle_label: string;
      capacity: number;
    }[];
    pending_requests: TransportRequestDTO[];
    active_trips: TripDTO[];
    stops: LuandaStop[];
  };
  demand_pressure: DemandPressureZone[];
}

interface MobilityIntelligenceDTO {
  summary: {
    total_requests_analyzed: number;
    total_trips_completed: number;
    avg_wait_time_min: number;
    unmet_demand_rate_pct: number;
    peak_hour_luanda: string;
    high_pressure_zones: number;
  };
  forecast_model_status: {
    mode: string;
    sample_trips: number;
    required_trips_for_ml: number;
    note: string;
  };
  zones: (DemandPressureZone & {
    congestion_index: number;
    estimated_wait_min: number;
    unmet_rate_pct: number;
    busy_vehicles: number;
  })[];
  hourly_distribution: { hour: string; requests: number }[];
  top_corridors: {
    origin: string;
    destination: string;
    requests_count: number;
    total_passengers: number;
    avg_fare_aoa: number;
    total_volume_aoa: number;
  }[];
  repositioning_recommendations: {
    from_zone: string;
    to_zone: string;
    priority: string;
    reason: string;
  }[];
}

interface IntegrationAdapterRow {
  provider_code: string;
  display_name: string;
  category: string;
  status: string;
  supports_qr: boolean;
  supports_nfc: boolean;
  cost_tier: string;
  notes: string;
}

interface AdminDriverRow {
  id: number;
  full_name: string;
  email: string;
  phone: string;
  license_number: string;
  national_id: string;
  verification_status: string;
  verification_notes?: string;
  rating_avg: number;
  total_trips: number;
  operational_status: string;
  current_zone?: string;
  vehicle?: {
    make: string;
    model: string;
    license_plate: string;
    capacity: number;
    color: string;
  };
}

interface AdminPassengerRow {
  id: number;
  full_name: string;
  email: string;
  balance_aoa: number;
}

interface AuditLogRow {
  id: number;
  actor_user_id?: number;
  action: string;
  entity_type: string;
  entity_id?: string;
  details_json: string;
  created_at: string;
}

export const AdminDashboard: React.FC = () => {
  const { lastEvent } = useAuth();
  const [tab, setTab] = useState<'overview' | 'intelligence' | 'drivers' | 'cards' | 'trips' | 'audit'>('overview');
  const [zoneFilter, setZoneFilter] = useState<string>('');
  const [tripStatusFilter, setTripStatusFilter] = useState<string>('');
  const [dateFrom, setDateFrom] = useState<string>('');
  const [dateTo, setDateTo] = useState<string>('');

  const [overview, setOverview] = useState<AdminOverviewDTO | null>(null);
  const [intelligence, setIntelligence] = useState<MobilityIntelligenceDTO | null>(null);
  const [integrations, setIntegrations] = useState<IntegrationAdapterRow[]>([]);
  const [drivers, setDrivers] = useState<AdminDriverRow[]>([]);
  const [passengers, setPassengers] = useState<AdminPassengerRow[]>([]);
  const [cardsData, setCardsData] = useState<{
    cards: TransportCardDTO[];
    recent_transactions: CardTransactionDTO[];
  } | null>(null);
  const [trips, setTrips] = useState<TripDTO[]>([]);
  const [auditLogs, setAuditLogs] = useState<AuditLogRow[]>([]);

  const [topupCard, setTopupCard] = useState('MOB-000001');
  const [topupAmount, setTopupAmount] = useState('5000');
  const [topupDesc, setTopupDesc] = useState('Carregamento administrativo em posto DalaLink');

  const [issuePassengerId, setIssuePassengerId] = useState<number>(1);
  const [issueInitialBalance, setIssueInitialBalance] = useState('2000');
  const [issueNfcUid, setIssueNfcUid] = useState('');

  const [busy, setBusy] = useState(false);
  const [banner, setBanner] = useState<{ type: 'ok' | 'err'; text: string } | null>(null);

  const loadAll = useCallback(async () => {
    try {
      const ovUrl = zoneFilter ? `/admin/overview?zone=${encodeURIComponent(zoneFilter)}` : '/admin/overview';
      const intelUrl = zoneFilter
        ? `/admin/intelligence?zone=${encodeURIComponent(zoneFilter)}`
        : '/admin/intelligence';

      const tripsParams = new URLSearchParams();
      if (zoneFilter) tripsParams.set('zone', zoneFilter);
      if (tripStatusFilter) tripsParams.set('status_filter', tripStatusFilter);
      if (dateFrom) tripsParams.set('date_from', dateFrom);
      if (dateTo) tripsParams.set('date_to', `${dateTo}T23:59:59`);
      const tripsUrl = `/admin/trips${tripsParams.toString() ? `?${tripsParams}` : ''}`;

      const [ovRes, intelRes, integRes, drvRes, passRes, cardsRes, tripsRes, logsRes] = await Promise.all([
        apiRequest<AdminOverviewDTO>(ovUrl),
        apiRequest<MobilityIntelligenceDTO>(intelUrl),
        apiRequest<{ integrations: IntegrationAdapterRow[] }>('/admin/integrations'),
        apiRequest<AdminDriverRow[]>('/admin/drivers'),
        apiRequest<AdminPassengerRow[]>('/admin/passengers'),
        apiRequest<{ cards: TransportCardDTO[]; recent_transactions: CardTransactionDTO[] }>('/admin/cards'),
        apiRequest<TripDTO[]>(tripsUrl),
        apiRequest<AuditLogRow[]>('/admin/audit-logs?limit=50'),
      ]);
      setOverview(ovRes);
      setIntelligence(intelRes);
      setIntegrations(integRes.integrations);
      setDrivers(drvRes);
      setPassengers(passRes);
      if (passRes.length > 0 && !passRes.some((p) => p.id === issuePassengerId)) {
        setIssuePassengerId(passRes[0].id);
      }
      setCardsData(cardsRes);
      setTrips(tripsRes);
      setAuditLogs(logsRes);
    } catch {
      // ignore transient errors
    }
  }, [zoneFilter, tripStatusFilter, dateFrom, dateTo, issuePassengerId]);

  useEffect(() => {
    loadAll();
    const timer = window.setInterval(loadAll, 7000);
    return () => window.clearInterval(timer);
  }, [loadAll]);

  useEffect(() => {
    if (lastEvent) loadAll();
  }, [lastEvent, loadAll]);

  const handleVerifyDriver = async (driverId: number, status: 'APPROVED' | 'REJECTED' | 'SUSPENDED') => {
    setBusy(true);
    setBanner(null);
    try {
      await apiRequest(`/admin/drivers/${driverId}/verify`, {
        method: 'POST',
        body: JSON.stringify({
          verification_status: status,
          notes:
            status === 'APPROVED'
              ? 'Documentação validada pela administração DalaLink.'
              : `Estado atualizado para ${status} pela administração.`,
        }),
      });
      setBanner({ type: 'ok', text: `Motorista #${driverId} atualizado para ${status}.` });
      await loadAll();
    } catch (err) {
      setBanner({ type: 'err', text: err instanceof Error ? err.message : 'Erro na validação.' });
    } finally {
      setBusy(false);
    }
  };

  const handleTopup = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setBanner(null);
    try {
      const tx = await apiRequest<CardTransactionDTO>('/admin/cards/topup', {
        method: 'POST',
        body: JSON.stringify({
          card_code: topupCard,
          amount_aoa: Number(topupAmount),
          description: topupDesc,
        }),
      });
      setBanner({
        type: 'ok',
        text: `Cartão ${tx.card_code} carregado com ${formatAOA(tx.amount_aoa)}. Novo saldo: ${formatAOA(tx.balance_after_aoa)}.`,
      });
      await loadAll();
    } catch (err) {
      setBanner({ type: 'err', text: err instanceof Error ? err.message : 'Erro no carregamento.' });
    } finally {
      setBusy(false);
    }
  };

  const handleIssueCard = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setBanner(null);
    try {
      const created = await apiRequest<TransportCardDTO>('/admin/cards/issue', {
        method: 'POST',
        body: JSON.stringify({
          passenger_id: issuePassengerId,
          initial_balance_aoa: Number(issueInitialBalance || 0),
          nfc_uid: issueNfcUid.trim() || undefined,
        }),
      });
      setIssueNfcUid('');
      setBanner({
        type: 'ok',
        text: `Novo cartão ${created.card_code} emitido para ${created.passenger_name} (${created.card_technology}).`,
      });
      await loadAll();
    } catch (err) {
      setBanner({ type: 'err', text: err instanceof Error ? err.message : 'Erro ao emitir cartão.' });
    } finally {
      setBusy(false);
    }
  };

  const handleBindNfcQuick = async (cardCode: string) => {
    const uid = `NFC-AO-${cardCode.replace('MOB-', '')}`;
    setBusy(true);
    setBanner(null);
    try {
      await apiRequest(`/admin/cards/${encodeURIComponent(cardCode)}/nfc`, {
        method: 'PUT',
        body: JSON.stringify({ nfc_uid: uid, card_technology: 'QR+NFC' }),
      });
      setBanner({ type: 'ok', text: `NFC ${uid} associado ao cartão ${cardCode} (modo QR+NFC ativo).` });
      await loadAll();
    } catch (err) {
      setBanner({ type: 'err', text: err instanceof Error ? err.message : 'Erro ao associar NFC.' });
    } finally {
      setBusy(false);
    }
  };

  const handleCardStatus = async (cardCode: string, nextStatus: 'ACTIVE' | 'BLOCKED') => {
    setBusy(true);
    setBanner(null);
    try {
      await apiRequest(`/admin/cards/${encodeURIComponent(cardCode)}/status`, {
        method: 'PUT',
        body: JSON.stringify({
          status: nextStatus,
          reason: nextStatus === 'BLOCKED' ? 'Bloqueio preventivo administrativo' : 'Reativação administrativa',
        }),
      });
      setBanner({ type: 'ok', text: `Cartão ${cardCode} alterado para ${nextStatus}.` });
      await loadAll();
    } catch (err) {
      setBanner({ type: 'err', text: err instanceof Error ? err.message : 'Erro ao alterar cartão.' });
    } finally {
      setBusy(false);
    }
  };

  const handleRefund = async (txId: number) => {
    setBusy(true);
    setBanner(null);
    try {
      const tx = await apiRequest<CardTransactionDTO>(`/admin/transactions/${txId}/refund`, {
        method: 'POST',
        body: JSON.stringify({ reason: 'Reembolso administrativo autorizado' }),
      });
      setBanner({
        type: 'ok',
        text: `Reembolso de ${formatAOA(tx.amount_aoa)} creditado no cartão ${tx.card_code}.`,
      });
      await loadAll();
    } catch (err) {
      setBanner({ type: 'err', text: err instanceof Error ? err.message : 'Erro ao reembolsar.' });
    } finally {
      setBusy(false);
    }
  };

  const mapMarkers: MapMarkerItem[] = useMemo(() => {
    if (!overview) return [];
    const items: MapMarkerItem[] = [];
    overview.map_data.stops.forEach((s) =>
      items.push({
        id: `stop-${s.id}`,
        lat: s.latitude,
        lng: s.longitude,
        label: s.zone_name,
        sublabel: s.name,
        kind: 'stop',
      })
    );
    overview.map_data.vehicles.forEach((v) =>
      items.push({
        id: `veh-${v.driver_id}`,
        lat: v.latitude,
        lng: v.longitude,
        label: v.vehicle_label,
        sublabel: `${v.driver_name} • ${v.status} • ${v.zone}`,
        kind: v.status === 'AVAILABLE' ? 'vehicle_available' : 'vehicle_busy',
      })
    );
    overview.map_data.pending_requests.forEach((r) =>
      items.push({
        id: `req-${r.id}`,
        lat: r.pickup_lat,
        lng: r.pickup_lng,
        label: `Pedido #${r.id} (${r.pickup_zone} → ${r.dropoff_zone})`,
        sublabel: `${r.passenger_count} pass. • ${formatAOA(r.estimated_total_fare_aoa)}`,
        kind: 'request',
      })
    );
    return items;
  }, [overview]);

  const demandCircles: DemandCircleItem[] = useMemo(() => {
    if (!overview) return [];
    return overview.demand_pressure.map((z) => ({
      zone: z.zone,
      lat: z.latitude,
      lng: z.longitude,
      level: z.pressure_level,
      activeRequests: z.active_requests,
      availableVehicles: z.available_vehicles,
    }));
  }, [overview]);

  const maxHourly = useMemo(() => {
    if (!intelligence) return 1;
    return Math.max(1, ...intelligence.hourly_distribution.map((h) => h.requests));
  }, [intelligence]);

  const k = overview?.kpis;

  return (
    <div className="min-h-screen bg-slate-50 pb-16">
      <TopBar />

      <main className="mx-auto max-w-7xl space-y-5 px-4 py-5">
        {/* Control Bar */}
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex flex-wrap gap-1.5 rounded-2xl bg-white p-1.5 shadow-xs ring-1 ring-slate-200">
            {[
              { id: 'overview', label: 'Mapa & KPIs', icon: MapIcon },
              { id: 'intelligence', label: 'Inteligência & Heatmap', icon: BarChart3 },
              { id: 'drivers', label: 'Motoristas', icon: Car },
              { id: 'cards', label: 'Cartões QR/NFC', icon: CreditCard },
              { id: 'trips', label: 'Viagens', icon: Activity },
              { id: 'audit', label: 'Auditoria & Integrações', icon: FileSearch },
            ].map((item) => {
              const Icon = item.icon;
              const active = tab === item.id;
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => setTab(item.id as typeof tab)}
                  className={`inline-flex items-center gap-1.5 rounded-xl px-3 py-2 text-xs font-bold transition ${
                    active ? 'bg-slate-900 text-white shadow-xs' : 'text-slate-600 hover:bg-slate-100'
                  }`}
                >
                  <Icon className="h-4 w-4" />
                  {item.label}
                </button>
              );
            })}
          </div>

          <div className="flex items-center gap-2">
            <div className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs">
              <Filter className="h-3.5 w-3.5 text-slate-400" />
              <select
                value={zoneFilter}
                onChange={(e) => setZoneFilter(e.target.value)}
                className="bg-transparent font-semibold text-slate-700 focus:outline-none"
              >
                <option value="">Todas as Zonas de Luanda</option>
                {overview?.demand_pressure.map((z) => (
                  <option key={z.zone} value={z.zone}>{z.zone}</option>
                ))}
              </select>
            </div>
            <button
              type="button"
              onClick={loadAll}
              className="inline-flex items-center gap-1.5 rounded-xl bg-emerald-700 px-3.5 py-2 text-xs font-bold text-white hover:bg-emerald-800"
            >
              <RefreshCw className="h-3.5 w-3.5" /> Atualizar
            </button>
          </div>
        </div>

        {banner && (
          <div
            className={`flex items-center justify-between rounded-xl border px-4 py-3 text-xs font-semibold ${
              banner.type === 'ok'
                ? 'border-emerald-200 bg-emerald-50 text-emerald-900'
                : 'border-red-200 bg-red-50 text-red-800'
            }`}
          >
            <span>{banner.text}</span>
            <button type="button" onClick={() => setBanner(null)}>✕</button>
          </div>
        )}

        {/* KPI GRID */}
        {k && (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <div className="rounded-2xl border border-slate-200 bg-white p-4">
              <div className="flex items-center justify-between text-xs font-semibold text-slate-500">
                <span>Receita Bruta & Comissões</span>
                <Wallet className="h-4 w-4 text-emerald-700" />
              </div>
              <p className="mt-2 text-2xl font-extrabold text-slate-900">{formatAOA(k.gross_revenue_aoa)}</p>
              <p className="mt-1 text-xs font-semibold text-emerald-700">
                Comissões plataforma: {formatAOA(k.platform_commissions_aoa)}
              </p>
            </div>

            <div className="rounded-2xl border border-slate-200 bg-white p-4">
              <div className="flex items-center justify-between text-xs font-semibold text-slate-500">
                <span>Operação em Tempo Real</span>
                <Activity className="h-4 w-4 text-amber-600" />
              </div>
              <p className="mt-2 text-2xl font-extrabold text-slate-900">
                {k.active_trips} em curso • {k.completed_trips} concluídas
              </p>
              <p className="mt-1 text-xs text-slate-500">
                Pendentes: <strong>{k.pending_requests}</strong> • Canceladas: {k.cancelled_requests}
              </p>
            </div>

            <div className="rounded-2xl border border-slate-200 bg-white p-4">
              <div className="flex items-center justify-between text-xs font-semibold text-slate-500">
                <span>Frota & Motoristas</span>
                <Car className="h-4 w-4 text-slate-700" />
              </div>
              <p className="mt-2 text-2xl font-extrabold text-slate-900">
                {k.available_vehicles}/{k.active_vehicles} livres
              </p>
              <p className="mt-1 text-xs text-slate-500">
                {k.drivers_registered} motoristas ({k.drivers_pending_verification} pendentes) •{' '}
                {k.passengers_registered} passageiros
              </p>
            </div>

            <div className="rounded-2xl border border-slate-200 bg-white p-4">
              <div className="flex items-center justify-between text-xs font-semibold text-slate-500">
                <span>Cartões QR/NFC & B2B</span>
                <CreditCard className="h-4 w-4 text-emerald-700" />
              </div>
              <p className="mt-2 text-2xl font-extrabold text-slate-900">
                {formatAOA(k.total_cards_balance_aoa)}
              </p>
              <p className="mt-1 text-xs text-slate-500">
                {k.active_cards} ativos • {k.blocked_cards} bloqueados • {k.partner_companies} empresa(s)
              </p>
            </div>
          </div>
        )}

        {/* TAB 1: OVERVIEW MAP */}
        {tab === 'overview' && overview && (
          <div className="grid gap-5 lg:grid-cols-12">
            <div className="rounded-2xl border border-slate-200 bg-white p-4 lg:col-span-8">
              <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                <h2 className="text-sm font-bold text-slate-900">
                  Mapa Operacional de Luanda (Frota, Pedidos, Paragens e Pressão)
                </h2>
                <div className="flex flex-wrap gap-2 text-[11px] font-semibold text-slate-600">
                  <span className="inline-flex items-center gap-1">
                    <span className="h-2.5 w-2.5 rounded-full bg-emerald-600" /> Livre
                  </span>
                  <span className="inline-flex items-center gap-1">
                    <span className="h-2.5 w-2.5 rounded-full bg-slate-900" /> Em viagem
                  </span>
                  <span className="inline-flex items-center gap-1">
                    <span className="h-2.5 w-2.5 rounded-full bg-red-600" /> Procura / Pressão
                  </span>
                </div>
              </div>
              <LuandaMap heightClass="h-[430px]" zoom={12} markers={mapMarkers} demandCircles={demandCircles} />
            </div>

            <div className="rounded-2xl border border-slate-200 bg-white p-4 lg:col-span-4">
              <div className="mb-3 flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-slate-500">
                <TrendingUp className="h-4 w-4 text-amber-600" />
                Pressão de Procura por Zona
              </div>
              <div className="max-h-[400px] space-y-2.5 overflow-y-auto pr-1">
                {overview.demand_pressure.map((z) => (
                  <div key={z.zone} className="rounded-xl border border-slate-100 bg-slate-50 p-3 text-xs">
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-slate-900">{z.zone}</span>
                      <span
                        className={`rounded-full px-2.5 py-0.5 text-[10px] font-extrabold ${
                          z.pressure_level === 'ELEVADA'
                            ? 'bg-red-100 text-red-700'
                            : z.pressure_level === 'MODERADA'
                              ? 'bg-amber-100 text-amber-800'
                              : 'bg-emerald-100 text-emerald-800'
                        }`}
                      >
                        {z.pressure_level}
                      </span>
                    </div>
                    <p className="mt-1 text-slate-600">
                      Procura: <strong>{z.active_requests}</strong> • Livres: <strong>{z.available_vehicles}</strong> •
                      Hist.: {z.historical_requests}
                    </p>
                    <p className="mt-1 text-[11px] text-slate-500">{z.recommendation}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* TAB 2: PHASE 3 MOBILITY INTELLIGENCE & HEATMAP */}
        {tab === 'intelligence' && intelligence && (
          <div className="space-y-5">
            <div className="rounded-2xl border border-emerald-200 bg-emerald-50/70 p-4 text-xs text-emerald-950">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <strong className="uppercase tracking-wider">Motor de Inteligência de Mobilidade:</strong>{' '}
                  <span className="font-mono-code font-bold">{intelligence.forecast_model_status.mode}</span>
                  <p className="mt-0.5 text-emerald-900">{intelligence.forecast_model_status.note}</p>
                </div>
                <div className="text-right font-mono-code text-xs font-bold">
                  Amostra real: {intelligence.forecast_model_status.sample_trips} /{' '}
                  {intelligence.forecast_model_status.required_trips_for_ml} viagens
                </div>
              </div>
            </div>

            <div className="grid gap-3 sm:grid-cols-4">
              <div className="rounded-2xl border border-slate-200 bg-white p-4">
                <p className="text-xs text-slate-500">Tempo Médio de Espera</p>
                <p className="mt-1 text-2xl font-extrabold text-slate-900">
                  {intelligence.summary.avg_wait_time_min} min
                </p>
              </div>
              <div className="rounded-2xl border border-slate-200 bg-white p-4">
                <p className="text-xs text-slate-500">Taxa Não Atendida / Cancel.</p>
                <p className="mt-1 text-2xl font-extrabold text-amber-700">
                  {intelligence.summary.unmet_demand_rate_pct}%
                </p>
              </div>
              <div className="rounded-2xl border border-slate-200 bg-white p-4">
                <p className="text-xs text-slate-500">Hora de Ponta (Luanda)</p>
                <p className="mt-1 text-2xl font-extrabold text-emerald-700">
                  {intelligence.summary.peak_hour_luanda}
                </p>
              </div>
              <div className="rounded-2xl border border-slate-200 bg-white p-4">
                <p className="text-xs text-slate-500">Zonas de Pressão Elevada</p>
                <p className="mt-1 text-2xl font-extrabold text-red-600">
                  {intelligence.summary.high_pressure_zones}
                </p>
              </div>
            </div>

            <div className="grid gap-5 lg:grid-cols-12">
              {/* Hourly Demand Bar Chart */}
              <div className="rounded-2xl border border-slate-200 bg-white p-5 lg:col-span-7">
                <h2 className="mb-4 text-sm font-bold text-slate-900">
                  Distribuição Horária da Procura (Africa/Luanda — 00h às 23h)
                </h2>
                <div className="flex h-44 items-end gap-1.5 border-b border-slate-200 pb-2">
                  {intelligence.hourly_distribution.map((h) => {
                    const pct = Math.max(6, Math.round((h.requests / maxHourly) * 100));
                    return (
                      <div key={h.hour} className="group flex flex-1 flex-col items-center gap-1">
                        <span className="text-[9px] font-bold text-slate-500 opacity-0 transition group-hover:opacity-100">
                          {h.requests}
                        </span>
                        <div
                          className={`w-full rounded-t-md transition ${
                            h.requests > 0 ? 'bg-emerald-600 group-hover:bg-amber-500' : 'bg-slate-200'
                          }`}
                          style={{ height: `${h.requests > 0 ? pct : 6}%` }}
                          title={`${h.hour}: ${h.requests} solicitações`}
                        />
                        <span className="text-[9px] text-slate-400">{h.hour.replace('h', '')}</span>
                      </div>
                    );
                  })}
                </div>

                <h3 className="mb-2 mt-5 text-xs font-bold uppercase tracking-wider text-slate-500">
                  Principais Corredores Origem → Destino
                </h3>
                {intelligence.top_corridors.length === 0 ? (
                  <p className="text-xs text-slate-500">Sem pedidos registados ainda para análise de corredores.</p>
                ) : (
                  <div className="divide-y divide-slate-100">
                    {intelligence.top_corridors.map((c) => (
                      <div key={`${c.origin}-${c.destination}`} className="flex items-center justify-between py-2 text-xs">
                        <span className="font-bold text-slate-900">
                          {c.origin} → {c.destination}
                        </span>
                        <span className="text-slate-600">
                          <strong>{c.requests_count}</strong> pedidos ({c.total_passengers} pass.) • Média{' '}
                          <strong className="text-emerald-700">{formatAOA(c.avg_fare_aoa)}</strong>
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Congestion & Repositioning Recommendations */}
              <div className="space-y-4 lg:col-span-5">
                <div className="rounded-2xl border border-slate-200 bg-white p-5">
                  <h2 className="mb-3 text-sm font-bold text-slate-900">
                    Recomendações Operacionais de Reposicionamento
                  </h2>
                  {intelligence.repositioning_recommendations.length === 0 ? (
                    <p className="text-xs text-slate-500">
                      Equilíbrio estável entre oferta e procura em todas as zonas de Luanda neste momento.
                    </p>
                  ) : (
                    <div className="space-y-2">
                      {intelligence.repositioning_recommendations.map((rec, idx) => (
                        <div key={idx} className="rounded-xl bg-amber-50 p-3 text-xs text-amber-950">
                          <p className="font-bold">
                            {rec.from_zone} → {rec.to_zone} ({rec.priority})
                          </p>
                          <p className="mt-0.5 text-[11px]">{rec.reason}</p>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                <div className="rounded-2xl border border-slate-200 bg-white p-5">
                  <h2 className="mb-3 text-sm font-bold text-slate-900">
                    Índice de Congestionamento e Espera por Zona
                  </h2>
                  <div className="max-h-64 space-y-2 overflow-y-auto pr-1">
                    {intelligence.zones.map((z) => (
                      <div key={z.zone} className="flex items-center justify-between rounded-xl bg-slate-50 px-3 py-2 text-xs">
                        <div>
                          <p className="font-bold text-slate-900">{z.zone}</p>
                          <p className="text-[11px] text-slate-500">
                            Espera est.: ~{z.estimated_wait_min} min • Não atend.: {z.unmet_rate_pct}%
                          </p>
                        </div>
                        <span className="font-mono-code rounded-lg bg-slate-900 px-2.5 py-1 text-[11px] font-bold text-amber-300">
                          Trânsito {z.congestion_index}x
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* TAB 3: DRIVERS VERIFICATION */}
        {tab === 'drivers' && (
          <div className="rounded-2xl border border-slate-200 bg-white p-5">
            <h2 className="mb-4 text-base font-bold text-slate-900">
              Gestão e Validação Documental de Motoristas
            </h2>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-slate-200 text-slate-500">
                    <th className="py-2.5 pr-4">Motorista</th>
                    <th className="py-2.5 pr-4">Documentos (Carta / BI)</th>
                    <th className="py-2.5 pr-4">Veículo</th>
                    <th className="py-2.5 pr-4">Estado</th>
                    <th className="py-2.5 text-right">Ações</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {drivers.map((d) => (
                    <tr key={d.id}>
                      <td className="py-3 pr-4">
                        <p className="font-bold text-slate-900">{d.full_name}</p>
                        <p className="text-slate-500">
                          {d.phone} • ★ {d.rating_avg.toFixed(2)} ({d.total_trips} viagens)
                        </p>
                      </td>
                      <td className="py-3 pr-4 font-mono-code text-[11px] text-slate-700">
                        <div>Carta: {d.license_number}</div>
                        <div>BI: {d.national_id}</div>
                      </td>
                      <td className="py-3 pr-4">
                        {d.vehicle ? (
                          <div>
                            <p className="font-semibold text-slate-800">
                              {d.vehicle.make} {d.vehicle.model} ({d.vehicle.capacity} lug.)
                            </p>
                            <p className="font-mono-code text-[11px] text-slate-500">
                              {d.vehicle.license_plate} • {d.current_zone ?? '—'}
                            </p>
                          </div>
                        ) : (
                          '—'
                        )}
                      </td>
                      <td className="py-3 pr-4">
                        <span
                          className={`rounded-full px-2.5 py-0.5 text-[11px] font-bold ${
                            d.verification_status === 'APPROVED'
                              ? 'bg-emerald-100 text-emerald-800'
                              : d.verification_status === 'PENDING'
                                ? 'bg-amber-100 text-amber-800'
                                : 'bg-red-100 text-red-700'
                          }`}
                        >
                          {d.verification_status}
                        </span>
                        <span className="ml-2 text-[11px] text-slate-500">({d.operational_status})</span>
                      </td>
                      <td className="py-3 text-right">
                        <div className="inline-flex gap-1.5">
                          {d.verification_status !== 'APPROVED' && (
                            <button
                              type="button"
                              disabled={busy}
                              onClick={() => handleVerifyDriver(d.id, 'APPROVED')}
                              className="inline-flex items-center gap-1 rounded-lg bg-emerald-700 px-2.5 py-1.5 text-[11px] font-bold text-white hover:bg-emerald-800"
                            >
                              <CheckCircle2 className="h-3.5 w-3.5" /> Aprovar
                            </button>
                          )}
                          {d.verification_status !== 'SUSPENDED' && (
                            <button
                              type="button"
                              disabled={busy}
                              onClick={() => handleVerifyDriver(d.id, 'SUSPENDED')}
                              className="inline-flex items-center gap-1 rounded-lg bg-red-50 px-2.5 py-1.5 text-[11px] font-bold text-red-700 hover:bg-red-100"
                            >
                              <Ban className="h-3.5 w-3.5" /> Suspender
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* TAB 4: PREPAID QR & NFC CARDS */}
        {tab === 'cards' && cardsData && (
          <div className="grid gap-5 lg:grid-cols-12">
            <div className="space-y-4 lg:col-span-4">
              <form onSubmit={handleTopup} className="space-y-3 rounded-2xl border border-slate-200 bg-white p-5">
                <div className="flex items-center gap-2">
                  <PlusCircle className="h-5 w-5 text-emerald-700" />
                  <h2 className="text-sm font-bold text-slate-900">Carregamento Administrativo (AOA)</h2>
                </div>
                <div>
                  <label className="mb-1 block text-xs font-semibold text-slate-700">Cartão</label>
                  <select
                    value={topupCard}
                    onChange={(e) => setTopupCard(e.target.value)}
                    className="font-mono-code w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-xs font-bold"
                  >
                    {cardsData.cards.map((c) => (
                      <option key={c.id} value={c.card_code}>
                        {c.card_code} — {c.passenger_name} ({formatAOA(c.balance_aoa)})
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="mb-1 block text-xs font-semibold text-slate-700">Valor (AOA)</label>
                  <input
                    type="number"
                    min={100}
                    step={100}
                    required
                    value={topupAmount}
                    onChange={(e) => setTopupAmount(e.target.value)}
                    className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm font-bold"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-semibold text-slate-700">Descrição</label>
                  <input
                    type="text"
                    value={topupDesc}
                    onChange={(e) => setTopupDesc(e.target.value)}
                    className="w-full rounded-xl border border-slate-300 px-3 py-2 text-xs"
                  />
                </div>
                <button
                  type="submit"
                  disabled={busy}
                  className="w-full rounded-xl bg-emerald-700 py-2.5 text-xs font-bold text-white hover:bg-emerald-800"
                >
                  Creditar Saldo no Servidor
                </button>
              </form>

              {/* Phase 4: Issue New Card (QR / NFC) */}
              <form onSubmit={handleIssueCard} className="space-y-3 rounded-2xl border border-slate-200 bg-white p-5">
                <div className="flex items-center gap-2">
                  <CreditCard className="h-5 w-5 text-amber-600" />
                  <h2 className="text-sm font-bold text-slate-900">Emitir Novo Cartão QR / NFC</h2>
                </div>
                <select
                  value={issuePassengerId}
                  onChange={(e) => setIssuePassengerId(Number(e.target.value))}
                  className="w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-xs font-semibold"
                >
                  {passengers.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.full_name} ({p.email})
                    </option>
                  ))}
                </select>
                <input
                  type="number"
                  min={0}
                  step={500}
                  value={issueInitialBalance}
                  onChange={(e) => setIssueInitialBalance(e.target.value)}
                  placeholder="Saldo inicial (AOA)"
                  className="w-full rounded-xl border border-slate-300 px-3 py-2 text-xs"
                />
                <input
                  type="text"
                  value={issueNfcUid}
                  onChange={(e) => setIssueNfcUid(e.target.value)}
                  placeholder="UID NFC opcional (ex: NFC-AO-9910)"
                  className="font-mono-code w-full rounded-xl border border-slate-300 px-3 py-2 text-xs uppercase"
                />
                <button
                  type="submit"
                  disabled={busy}
                  className="w-full rounded-xl bg-slate-900 py-2.5 text-xs font-bold text-white hover:bg-slate-800"
                >
                  Emitir Cartão de Mobilidade
                </button>
              </form>
            </div>

            <div className="space-y-4 lg:col-span-8">
              <div className="rounded-2xl border border-slate-200 bg-white p-5">
                <h2 className="mb-3 text-sm font-bold text-slate-900">Cartões de Mobilidade Emitidos (QR / NFC)</h2>
                <div className="divide-y divide-slate-100">
                  {cardsData.cards.map((c) => (
                    <div key={c.id} className="flex flex-wrap items-center justify-between gap-3 py-3 text-xs">
                      <div>
                        <span className="font-mono-code font-extrabold text-slate-900">{c.card_code}</span>{' '}
                        <span className="text-slate-600">• {c.passenger_name}</span>
                        <span className="ml-2 rounded-md bg-slate-100 px-2 py-0.5 font-mono-code text-[10px] font-bold text-slate-700">
                          {c.card_technology}
                          {c.nfc_uid ? ` (${c.nfc_uid})` : ''}
                        </span>
                        <p className="mt-0.5 text-[11px] text-slate-500">
                          Saldo: <strong className="text-emerald-700">{formatAOA(c.balance_aoa)}</strong> • Estado:{' '}
                          <strong>{c.status}</strong>
                        </p>
                      </div>
                      <div className="flex items-center gap-1.5">
                        {!c.nfc_uid && (
                          <button
                            type="button"
                            disabled={busy}
                            onClick={() => handleBindNfcQuick(c.card_code)}
                            className="inline-flex items-center gap-1 rounded-lg bg-slate-100 px-2.5 py-1.5 text-[11px] font-bold text-slate-700 hover:bg-slate-200"
                          >
                            <Wifi className="h-3.5 w-3.5 rotate-90" /> Ativar NFC
                          </button>
                        )}
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() => handleCardStatus(c.card_code, c.status === 'ACTIVE' ? 'BLOCKED' : 'ACTIVE')}
                          className={`rounded-lg px-3 py-1.5 text-[11px] font-bold transition ${
                            c.status === 'ACTIVE'
                              ? 'bg-red-50 text-red-700 hover:bg-red-100'
                              : 'bg-emerald-50 text-emerald-800 hover:bg-emerald-100'
                          }`}
                        >
                          {c.status === 'ACTIVE' ? 'Bloquear' : 'Desbloquear'}
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="rounded-2xl border border-slate-200 bg-white p-5">
                <h2 className="mb-3 text-sm font-bold text-slate-900">
                  Últimas Operações Financeiras (com Reembolso Autorizado)
                </h2>
                <div className="divide-y divide-slate-100">
                  {cardsData.recent_transactions.slice(0, 12).map((tx) => (
                    <div key={tx.id} className="flex flex-wrap items-center justify-between gap-2 py-2.5 text-xs">
                      <div>
                        <p className="font-bold text-slate-900">
                          [{tx.tx_type}] {tx.card_code} — {tx.description}
                        </p>
                        <p className="text-[11px] text-slate-500">
                          {formatLuandaTime(tx.created_at)} • Antes: {formatAOA(tx.balance_before_aoa)} → Depois:{' '}
                          {formatAOA(tx.balance_after_aoa)}
                        </p>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="font-mono-code font-bold text-slate-900">{formatAOA(tx.amount_aoa)}</span>
                        {tx.tx_type === 'TRIP_DEBIT' && (
                          <button
                            type="button"
                            disabled={busy}
                            onClick={() => handleRefund(tx.id)}
                            className="inline-flex items-center gap-1 rounded-lg bg-amber-50 px-2.5 py-1 text-[11px] font-bold text-amber-800 hover:bg-amber-100"
                          >
                            <RotateCcw className="h-3 w-3" /> Reembolsar
                          </button>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* TAB 5: TRIPS WITH ADVANCED DATE & STATUS FILTERS */}
        {tab === 'trips' && (
          <div className="rounded-2xl border border-slate-200 bg-white p-5">
            <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
              <h2 className="text-base font-bold text-slate-900">Registo Operacional de Viagens</h2>
              <div className="flex flex-wrap items-center gap-2 text-xs">
                <input
                  type="date"
                  value={dateFrom}
                  onChange={(e) => setDateFrom(e.target.value)}
                  className="rounded-xl border border-slate-300 bg-white px-2.5 py-1.5 font-medium"
                />
                <span className="text-slate-400">a</span>
                <input
                  type="date"
                  value={dateTo}
                  onChange={(e) => setDateTo(e.target.value)}
                  className="rounded-xl border border-slate-300 bg-white px-2.5 py-1.5 font-medium"
                />
                <select
                  value={tripStatusFilter}
                  onChange={(e) => setTripStatusFilter(e.target.value)}
                  className="rounded-xl border border-slate-300 bg-white px-3 py-1.5 font-semibold"
                >
                  <option value="">Todos os Estados</option>
                  <option value="DRIVER_EN_ROUTE">A caminho</option>
                  <option value="DRIVER_ARRIVED">No local</option>
                  <option value="IN_PROGRESS">Em andamento</option>
                  <option value="COMPLETED">Concluídas</option>
                </select>
              </div>
            </div>
            {trips.length === 0 ? (
              <p className="text-xs text-slate-500">Sem viagens para os filtros selecionados.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead>
                    <tr className="border-b border-slate-200 text-slate-500">
                      <th className="py-2 pr-3">#</th>
                      <th className="py-2 pr-3">Rota</th>
                      <th className="py-2 pr-3">Motorista / Veículo</th>
                      <th className="py-2 pr-3">Estado</th>
                      <th className="py-2 pr-3">Validado</th>
                      <th className="py-2 text-right">Comissão</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {trips.map((t) => (
                      <tr key={t.id}>
                        <td className="py-2.5 pr-3 font-mono-code font-bold">#{t.id}</td>
                        <td className="py-2.5 pr-3">
                          <p className="font-bold text-slate-900">
                            {t.request?.pickup_zone} → {t.request?.dropoff_zone}
                          </p>
                          <p className="text-[11px] text-slate-500">
                            {t.request?.passenger_name} ({t.request?.request_type} • {t.request?.passenger_count} pass.)
                          </p>
                        </td>
                        <td className="py-2.5 pr-3">
                          <p className="font-semibold">{t.driver?.full_name}</p>
                          <p className="text-[11px] text-slate-500">
                            {t.vehicle?.make} {t.vehicle?.model} ({t.vehicle?.license_plate})
                          </p>
                        </td>
                        <td className="py-2.5 pr-3">
                          <span className="rounded-full bg-slate-100 px-2.5 py-0.5 text-[11px] font-bold">
                            {t.status}
                          </span>
                        </td>
                        <td className="py-2.5 pr-3 font-bold text-emerald-700">
                          {formatAOA(t.paid_total_aoa)} / {formatAOA(t.total_fare_aoa)}
                        </td>
                        <td className="py-2.5 text-right font-semibold text-amber-700">
                          {t.commission ? formatAOA(t.commission.platform_fee_aoa) : '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {/* TAB 6: AUDIT LOGS & PHASE 4 EXTERNAL INTEGRATIONS REGISTRY */}
        {tab === 'audit' && (
          <div className="grid gap-5 lg:grid-cols-12">
            <div className="rounded-2xl border border-slate-200 bg-white p-5 lg:col-span-5">
              <div className="mb-3 flex items-center gap-2">
                <Link2 className="h-5 w-5 text-amber-600" />
                <h2 className="text-sm font-bold text-slate-900">
                  Arquitetura de Integrações & Parceiros (Fase 4)
                </h2>
              </div>
              <div className="space-y-2.5">
                {integrations.map((ad) => (
                  <div key={ad.provider_code} className="rounded-xl border border-slate-200 bg-slate-50 p-3 text-xs">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-bold text-slate-900">{ad.display_name}</span>
                      <span
                        className={`rounded-full px-2 py-0.5 text-[10px] font-extrabold ${
                          ad.status.startsWith('ACTIVE')
                            ? 'bg-emerald-100 text-emerald-800'
                            : ad.status.startsWith('READY')
                              ? 'bg-amber-100 text-amber-800'
                              : 'bg-slate-200 text-slate-700'
                        }`}
                      >
                        {ad.status}
                      </span>
                    </div>
                    <p className="mt-1 text-[11px] text-slate-600">{ad.notes}</p>
                    <p className="mt-1 font-mono-code text-[10px] text-slate-400">
                      Custo: {ad.cost_tier} • QR: {ad.supports_qr ? 'Sim' : 'Não'} • NFC:{' '}
                      {ad.supports_nfc ? 'Sim' : 'Não'}
                    </p>
                  </div>
                ))}
              </div>
            </div>

            <div className="rounded-2xl border border-slate-200 bg-white p-5 lg:col-span-7">
              <div className="mb-3 flex items-center gap-2">
                <ShieldCheck className="h-5 w-5 text-emerald-700" />
                <h2 className="text-sm font-bold text-slate-900">Registo Imutável de Auditoria (Audit Logs)</h2>
              </div>
              <div className="max-h-[480px] divide-y divide-slate-100 overflow-y-auto pr-1">
                {auditLogs.map((log) => (
                  <div key={log.id} className="py-2.5 text-xs">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="font-mono-code font-bold text-slate-900">
                        {log.action} • {log.entity_type} #{log.entity_id ?? '—'}
                      </span>
                      <span className="text-[11px] text-slate-400">{formatLuandaTime(log.created_at)}</span>
                    </div>
                    <p className="mt-0.5 font-mono-code text-[11px] text-slate-500">{log.details_json}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
};
