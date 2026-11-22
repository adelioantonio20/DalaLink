import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  AlertTriangle,
  Car,
  CheckCircle2,
  Compass,
  Flag,
  MapPin,
  Navigation,
  Play,
  Plus,
  TrendingUp,
  Users,
  Volume2,
  VolumeX,
  Wallet,
  XCircle,
} from 'lucide-react';
import { LuandaMap, MapMarkerItem } from '../../components/LuandaMap';
import { QrScannerPanel } from '../../components/QrScannerPanel';
import { TopBar } from '../../components/TopBar';
import { useAuth } from '../../contexts/AuthContext';
import { apiRequest, formatAOA, formatLuandaTime } from '../../services/api';
import { playTone, speakPortuguese } from '../../services/audio';
import { DemandPressureZone, TransportRequestDTO, TripDTO } from '../../types';

interface DriverDashboardDTO {
  driver: {
    id: number;
    full_name: string;
    phone: string;
    license_number: string;
    national_id: string;
    verification_status: string;
    verification_notes?: string;
    rating_avg: number;
    total_trips: number;
  };
  availability: {
    status: 'AVAILABLE' | 'BUSY' | 'OFFLINE';
    active_vehicle_id?: number;
    current_lat: number;
    current_lng: number;
    current_zone: string;
  };
  vehicles: {
    id: number;
    make: string;
    model: string;
    year: number;
    color: string;
    license_plate: string;
    vehicle_type: string;
    capacity: number;
    is_active: boolean;
  }[];
  pending_offer: TransportRequestDTO | null;
  active_trip: TripDTO | null;
  recent_trips: TripDTO[];
  earnings: {
    gross_aoa: number;
    platform_commission_aoa: number;
    driver_net_aoa: number;
  };
  opportunity_zones: DemandPressureZone[];
}

export const DriverApp: React.FC = () => {
  const { lastEvent } = useAuth();
  const [data, setData] = useState<DriverDashboardDTO | null>(null);
  const [soundEnabled, setSoundEnabled] = useState(true);
  const [busy, setBusy] = useState(false);
  const [alertBanner, setAlertBanner] = useState<{ type: 'ok' | 'err'; text: string } | null>(null);
  const [showAddVehicle, setShowAddVehicle] = useState(false);
  const [vehForm, setVehForm] = useState({
    make: '',
    model: '',
    year: 2023,
    color: 'Branco',
    license_plate: '',
    capacity: 4,
  });
  const lastAnnouncedOfferRef = useRef<number | null>(null);

  const loadDashboard = useCallback(async () => {
    try {
      const res = await apiRequest<DriverDashboardDTO>('/driver/dashboard');
      setData(res);
      if (res.pending_offer && res.pending_offer.id !== lastAnnouncedOfferRef.current) {
        lastAnnouncedOfferRef.current = res.pending_offer.id;
        if (soundEnabled) {
          playTone('offer');
          speakPortuguese(
            `Nova solicitação de transporte. Origem ${res.pending_offer.pickup_zone}, destino ${res.pending_offer.dropoff_zone}, ${res.pending_offer.passenger_count} passageiro.`
          );
        }
      }
    } catch {
      // ignore transient error
    }
  }, [soundEnabled]);

  useEffect(() => {
    loadDashboard();
    const timer = window.setInterval(loadDashboard, 4500);
    return () => window.clearInterval(timer);
  }, [loadDashboard]);

  useEffect(() => {
    if (!lastEvent) return;
    if (['NEW_OFFER', 'REQUEST_CANCELLED', 'DRIVER_VERIFICATION_UPDATED'].includes(lastEvent.event)) {
      loadDashboard();
    }
  }, [lastEvent, loadDashboard]);

  const handleStatusChange = async (status: 'AVAILABLE' | 'BUSY' | 'OFFLINE') => {
    setBusy(true);
    setAlertBanner(null);
    try {
      await apiRequest('/driver/status', {
        method: 'PUT',
        body: JSON.stringify({ status }),
      });
      await loadDashboard();
    } catch (err) {
      setAlertBanner({ type: 'err', text: err instanceof Error ? err.message : 'Erro ao mudar estado.' });
    } finally {
      setBusy(false);
    }
  };

  const handleAcceptOffer = async (reqId: number) => {
    setBusy(true);
    setAlertBanner(null);
    try {
      await apiRequest(`/driver/offers/${reqId}/accept`, { method: 'POST' });
      if (soundEnabled) {
        playTone('success');
        speakPortuguese('Viagem aceite. Siga para o ponto de recolha.');
      }
      setAlertBanner({ type: 'ok', text: 'Solicitação aceite! Siga até ao passageiro.' });
      await loadDashboard();
    } catch (err) {
      if (soundEnabled) playTone('error');
      setAlertBanner({ type: 'err', text: err instanceof Error ? err.message : 'Erro ao aceitar.' });
    } finally {
      setBusy(false);
    }
  };

  const handleRejectOffer = async (reqId: number) => {
    setBusy(true);
    try {
      await apiRequest(`/driver/offers/${reqId}/reject`, { method: 'POST' });
      setAlertBanner({ type: 'ok', text: 'Solicitação rejeitada e redistribuída.' });
      await loadDashboard();
    } catch (err) {
      setAlertBanner({ type: 'err', text: err instanceof Error ? err.message : 'Erro ao rejeitar.' });
    } finally {
      setBusy(false);
    }
  };

  const handleSimulateGpsStep = async (tripId: number) => {
    setBusy(true);
    try {
      const res = await apiRequest<{ zone: string; eta_minutes: number; distance_remaining_km: number }>(
        `/driver/trips/${tripId}/simulate-step`,
        { method: 'POST' }
      );
      setAlertBanner({
        type: 'ok',
        text: `GPS atualizado (${res.zone}) • Distância restante: ${res.distance_remaining_km} km • ETA ${res.eta_minutes} min.`,
      });
      await loadDashboard();
    } catch (err) {
      setAlertBanner({ type: 'err', text: err instanceof Error ? err.message : 'Erro GPS.' });
    } finally {
      setBusy(false);
    }
  };

  const handleArrive = async (tripId: number) => {
    setBusy(true);
    try {
      await apiRequest(`/driver/trips/${tripId}/arrive`, { method: 'POST' });
      if (soundEnabled) {
        playTone('success');
        speakPortuguese('Chegada confirmada. Leia o cartão QR do passageiro.');
      }
      setAlertBanner({ type: 'ok', text: 'Chegada confirmada! Valide o cartão QR do passageiro.' });
      await loadDashboard();
    } catch (err) {
      setAlertBanner({ type: 'err', text: err instanceof Error ? err.message : 'Erro ao confirmar chegada.' });
    } finally {
      setBusy(false);
    }
  };

  const handleValidateCard = async (cardIdentifier: string) => {
    if (!data?.active_trip) return;
    setBusy(true);
    setAlertBanner(null);
    try {
      const res = await apiRequest<{
        validation: {
          message: string;
          card_code: string;
          passenger_name: string;
          amount_debited_aoa: number;
          balance_after_aoa: number;
        };
      }>(`/driver/trips/${data.active_trip.id}/validate-card`, {
        method: 'POST',
        body: JSON.stringify({
          card_identifier: cardIdentifier,
          idempotency_key: `DRV-SCAN-${data.active_trip.id}-${cardIdentifier.slice(0, 24)}`,
        }),
      });
      if (soundEnabled) {
        playTone('success');
        speakPortuguese('Embarque autorizado.');
      }
      setAlertBanner({
        type: 'ok',
        text: `${res.validation.message} (${res.validation.passenger_name} • Saldo restante: ${formatAOA(res.validation.balance_after_aoa)})`,
      });
      await loadDashboard();
    } catch (err) {
      if (soundEnabled) {
        playTone('error');
        speakPortuguese('Embarque recusado.');
      }
      setAlertBanner({
        type: 'err',
        text: err instanceof Error ? err.message : 'Validação recusada.',
      });
    } finally {
      setBusy(false);
    }
  };

  const handleStartTrip = async (tripId: number) => {
    setBusy(true);
    try {
      await apiRequest(`/driver/trips/${tripId}/start`, { method: 'POST' });
      if (soundEnabled) {
        playTone('success');
        speakPortuguese('Viagem iniciada. Conduza com segurança.');
      }
      setAlertBanner({ type: 'ok', text: 'Viagem iniciada!' });
      await loadDashboard();
    } catch (err) {
      setAlertBanner({ type: 'err', text: err instanceof Error ? err.message : 'Não foi possível iniciar.' });
    } finally {
      setBusy(false);
    }
  };

  const handleCompleteTrip = async (tripId: number) => {
    setBusy(true);
    try {
      const completed = await apiRequest<TripDTO>(`/driver/trips/${tripId}/complete`, { method: 'POST' });
      if (soundEnabled) {
        playTone('success');
        speakPortuguese('Viagem concluída com sucesso.');
      }
      setAlertBanner({
        type: 'ok',
        text: `Viagem concluída! Receita líquida: ${formatAOA(completed.commission?.driver_net_aoa ?? 0)} (Comissão plataforma: ${formatAOA(completed.commission?.platform_fee_aoa ?? 0)}).`,
      });
      await loadDashboard();
    } catch (err) {
      setAlertBanner({ type: 'err', text: err instanceof Error ? err.message : 'Erro ao concluir viagem.' });
    } finally {
      setBusy(false);
    }
  };

  const handleRegisterVehicle = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      await apiRequest('/driver/vehicles', {
        method: 'POST',
        body: JSON.stringify(vehForm),
      });
      setShowAddVehicle(false);
      setVehForm({ make: '', model: '', year: 2023, color: 'Branco', license_plate: '', capacity: 4 });
      setAlertBanner({ type: 'ok', text: 'Veículo registado com sucesso!' });
      await loadDashboard();
    } catch (err) {
      setAlertBanner({ type: 'err', text: err instanceof Error ? err.message : 'Erro ao registar veículo.' });
    } finally {
      setBusy(false);
    }
  };

  const mapMarkers: MapMarkerItem[] = useMemo(() => {
    if (!data) return [];
    const items: MapMarkerItem[] = [
      {
        id: 'self',
        lat: data.availability.current_lat,
        lng: data.availability.current_lng,
        label: 'A minha localização',
        sublabel: data.availability.current_zone,
        kind: data.availability.status === 'AVAILABLE' ? 'vehicle_available' : 'vehicle_busy',
      },
    ];
    const req = data.active_trip?.request ?? data.pending_offer;
    if (req) {
      items.push({
        id: 'pickup',
        lat: req.pickup_lat,
        lng: req.pickup_lng,
        label: `Recolha: ${req.pickup_zone}`,
        sublabel: req.pickup_label,
        kind: 'pickup',
      });
      items.push({
        id: 'dropoff',
        lat: req.dropoff_lat,
        lng: req.dropoff_lng,
        label: `Destino: ${req.dropoff_zone}`,
        sublabel: req.dropoff_label,
        kind: 'dropoff',
      });
    }
    return items;
  }, [data]);

  const routeLine: [number, number][] = useMemo(() => {
    const req = data?.active_trip?.request ?? data?.pending_offer;
    if (!req) return [];
    return [
      [req.pickup_lat, req.pickup_lng],
      [req.dropoff_lat, req.dropoff_lng],
    ];
  }, [data]);

  const activeVehicle = data?.vehicles.find((v) => v.id === data.availability.active_vehicle_id) ?? data?.vehicles[0];

  return (
    <div className="min-h-screen bg-slate-950 pb-16 text-slate-100">
      <TopBar dark />

      <main className="mx-auto max-w-6xl space-y-5 px-4 py-5">
        {/* Verification Warning if not APPROVED */}
        {data && data.driver.verification_status !== 'APPROVED' && (
          <div className="flex items-start gap-3 rounded-2xl border border-amber-500/40 bg-amber-500/10 p-4 text-amber-200">
            <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-amber-400" />
            <div className="text-xs">
              <p className="font-bold text-amber-100">
                Estado documental: {data.driver.verification_status}
              </p>
              <p className="mt-0.5">
                {data.driver.verification_notes ||
                  'Aguarda validação documental pelo administrador antes de poder aceitar viagens.'}
              </p>
            </div>
          </div>
        )}

        {/* High-Visibility Operational Header */}
        <div className="flex flex-col gap-4 rounded-2xl border border-slate-800 bg-slate-900 p-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-3">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-emerald-600/20 text-emerald-400">
              <Car className="h-6 w-6" />
            </div>
            <div>
              <p className="text-base font-extrabold text-white">
                {activeVehicle
                  ? `${activeVehicle.make} ${activeVehicle.model} • ${activeVehicle.license_plate}`
                  : 'Sem veículo registado'}
              </p>
              <p className="text-xs text-slate-400">
                Zona GPS: <strong className="text-slate-200">{data?.availability.current_zone ?? 'Luanda'}</strong>{' '}
                • ★ {data?.driver.rating_avg.toFixed(2) ?? '5.00'} • {data?.driver.total_trips ?? 0} viagens
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => setSoundEnabled((s) => !s)}
              className={`inline-flex items-center gap-1.5 rounded-xl px-3.5 py-2.5 text-xs font-bold transition ${
                soundEnabled
                  ? 'bg-emerald-600/20 text-emerald-300 ring-1 ring-emerald-500/40'
                  : 'bg-slate-800 text-slate-400'
              }`}
            >
              {soundEnabled ? <Volume2 className="h-4 w-4" /> : <VolumeX className="h-4 w-4" />}
              {soundEnabled ? 'Alertas Voz ON' : 'Voz OFF'}
            </button>

            <div className="grid grid-cols-3 gap-1 rounded-xl bg-slate-950 p-1">
              {(['AVAILABLE', 'BUSY', 'OFFLINE'] as const).map((st) => {
                const current = data?.availability.status === st;
                const label = st === 'AVAILABLE' ? 'Disponível' : st === 'BUSY' ? 'Ocupado' : 'Indisponível';
                return (
                  <button
                    key={st}
                    type="button"
                    disabled={busy}
                    onClick={() => handleStatusChange(st)}
                    className={`rounded-lg px-3 py-2 text-xs font-extrabold transition ${
                      current
                        ? st === 'AVAILABLE'
                          ? 'bg-emerald-600 text-white'
                          : st === 'BUSY'
                            ? 'bg-amber-600 text-white'
                            : 'bg-slate-700 text-white'
                        : 'text-slate-400 hover:text-white'
                    }`}
                  >
                    {label}
                  </button>
                );
              })}
            </div>
          </div>
        </div>

        {alertBanner && (
          <div
            className={`flex items-center justify-between rounded-xl border px-4 py-3 text-sm font-semibold ${
              alertBanner.type === 'ok'
                ? 'border-emerald-500/40 bg-emerald-500/15 text-emerald-200'
                : 'border-red-500/40 bg-red-500/15 text-red-200'
            }`}
          >
            <span>{alertBanner.text}</span>
            <button type="button" onClick={() => setAlertBanner(null)} className="ml-4 text-slate-300">
              ✕
            </button>
          </div>
        )}

        {/* INCOMING OFFER (BIG HANDS-FREE TARGETS) */}
        {data?.pending_offer && !data.active_trip && (
          <div className="rounded-2xl border-2 border-amber-500 bg-slate-900 p-5 shadow-xl">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <span className="inline-flex items-center gap-2 rounded-full bg-amber-500 px-3 py-1 text-xs font-extrabold uppercase tracking-wider text-slate-950">
                Nova Solicitação Recebida
              </span>
              <span className="text-2xl font-extrabold text-emerald-400">
                {formatAOA(data.pending_offer.estimated_total_fare_aoa)}
              </span>
            </div>

            <div className="grid gap-3 rounded-xl bg-slate-950 p-4 sm:grid-cols-3">
              <div>
                <p className="text-[11px] uppercase text-slate-400">Origem</p>
                <p className="text-base font-extrabold text-white">{data.pending_offer.pickup_zone}</p>
                <p className="text-xs text-slate-400">{data.pending_offer.pickup_label}</p>
              </div>
              <div>
                <p className="text-[11px] uppercase text-slate-400">Destino</p>
                <p className="text-base font-extrabold text-amber-400">{data.pending_offer.dropoff_zone}</p>
                <p className="text-xs text-slate-400">{data.pending_offer.dropoff_label}</p>
              </div>
              <div>
                <p className="text-[11px] uppercase text-slate-400">Passageiros & Distância</p>
                <p className="inline-flex items-center gap-1.5 text-base font-extrabold text-white">
                  <Users className="h-4 w-4 text-emerald-400" /> {data.pending_offer.passenger_count}{' '}
                  ({data.pending_offer.request_type})
                </p>
                <p className="text-xs text-slate-400">
                  {data.pending_offer.estimated_distance_km} km • ~{data.pending_offer.estimated_duration_min} min
                </p>
              </div>
            </div>

            <div className="mt-4 grid grid-cols-2 gap-3">
              <button
                id="driver-reject-offer-btn"
                type="button"
                disabled={busy}
                onClick={() => handleRejectOffer(data.pending_offer!.id)}
                className="inline-flex items-center justify-center gap-2 rounded-2xl bg-slate-800 py-4 text-base font-extrabold text-red-300 transition hover:bg-red-900/60"
              >
                <XCircle className="h-6 w-6" /> REJEITAR
              </button>
              <button
                id="driver-accept-offer-btn"
                type="button"
                disabled={busy}
                onClick={() => handleAcceptOffer(data.pending_offer!.id)}
                className="inline-flex items-center justify-center gap-2 rounded-2xl bg-emerald-600 py-4 text-base font-extrabold text-white transition hover:bg-emerald-500"
              >
                <CheckCircle2 className="h-6 w-6" /> ACEITAR VIAGEM
              </button>
            </div>
          </div>
        )}

        <div className="grid gap-5 lg:grid-cols-12">
          {/* LEFT: LIVE NAVIGATION MAP & ACTIVE TRIP ACTIONS */}
          <div className="space-y-4 lg:col-span-7">
            <LuandaMap heightClass="h-80" markers={mapMarkers} routeLine={routeLine} />

            {data?.active_trip && (
              <div className="space-y-4 rounded-2xl border border-slate-800 bg-slate-900 p-5">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <p className="text-xs font-bold uppercase tracking-wider text-emerald-400">
                      Viagem #{data.active_trip.id} • {data.active_trip.status}
                    </p>
                    <h2 className="text-lg font-extrabold text-white">
                      {data.active_trip.request?.pickup_zone} → {data.active_trip.request?.dropoff_zone}
                    </h2>
                    <p className="text-xs text-slate-400">
                      Passageiro: <strong className="text-white">{data.active_trip.request?.passenger_name}</strong> •{' '}
                      {data.active_trip.request?.passenger_count} lugar(es) • Código PIN:{' '}
                      <strong className="font-mono-code text-amber-400">{data.active_trip.boarding_code}</strong>
                    </p>
                  </div>
                  <div className="text-right">
                    <p className="text-xs text-slate-400">Validados</p>
                    <p className="text-xl font-extrabold text-emerald-400">
                      {data.active_trip.boarded_count}/{data.active_trip.request?.passenger_count ?? 1}
                    </p>
                    <p className="text-xs text-slate-300">
                      Cobrado: {formatAOA(data.active_trip.paid_total_aoa)}
                    </p>
                  </div>
                </div>

                {/* Big Operational Step Buttons */}
                <div className="grid gap-2.5 sm:grid-cols-2">
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => handleSimulateGpsStep(data.active_trip!.id)}
                    className="inline-flex items-center justify-center gap-2 rounded-xl bg-slate-800 py-3 text-xs font-bold text-slate-100 transition hover:bg-slate-700"
                  >
                    <Compass className="h-4 w-4 text-emerald-400" />
                    Avançar Posição GPS (Simulação)
                  </button>

                  {data.active_trip.status === 'DRIVER_EN_ROUTE' && (
                    <button
                      id="driver-arrive-btn"
                      type="button"
                      disabled={busy}
                      onClick={() => handleArrive(data.active_trip!.id)}
                      className="inline-flex items-center justify-center gap-2 rounded-xl bg-amber-600 py-3 text-sm font-extrabold text-white transition hover:bg-amber-500"
                    >
                      <MapPin className="h-5 w-5" /> Marcar Chegada ao Passageiro
                    </button>
                  )}

                  {(data.active_trip.status === 'DRIVER_ARRIVED' ||
                    data.active_trip.status === 'DRIVER_EN_ROUTE') && (
                    <button
                      id="driver-start-trip-btn"
                      type="button"
                      disabled={busy || data.active_trip.boarded_count < 1}
                      onClick={() => handleStartTrip(data.active_trip!.id)}
                      className="inline-flex items-center justify-center gap-2 rounded-xl bg-emerald-600 py-3.5 text-sm font-extrabold text-white transition hover:bg-emerald-500 disabled:cursor-not-allowed disabled:bg-slate-800 disabled:text-slate-500 sm:col-span-2"
                    >
                      <Play className="h-5 w-5" />
                      {data.active_trip.boarded_count < 1
                        ? 'Valide o cartão QR abaixo para iniciar a viagem'
                        : 'INICIAR VIAGEM'}
                    </button>
                  )}

                  {data.active_trip.status === 'IN_PROGRESS' && (
                    <button
                      id="driver-complete-trip-btn"
                      type="button"
                      disabled={busy}
                      onClick={() => handleCompleteTrip(data.active_trip!.id)}
                      className="inline-flex items-center justify-center gap-2 rounded-xl bg-emerald-600 py-3.5 text-sm font-extrabold text-white transition hover:bg-emerald-500 sm:col-span-2"
                    >
                      <Flag className="h-5 w-5" /> CONCLUIR VIAGEM NO DESTINO
                    </button>
                  )}
                </div>

                {/* QR Boarding Validator */}
                <QrScannerPanel
                  onValidate={handleValidateCard}
                  busy={busy}
                  suggestedCards={
                    data.active_trip.request?.group_members.length
                      ? data.active_trip.request.group_members.map((m) => m.card_code)
                      : ['MOB-000001', 'MOB-000002', 'MOB-000003', 'MOB-000004']
                  }
                />
              </div>
            )}
          </div>

          {/* RIGHT: EARNINGS, DEMAND ZONES & VEHICLES */}
          <div className="space-y-4 lg:col-span-5">
            {/* Earnings & Commissions */}
            <div className="rounded-2xl border border-slate-800 bg-slate-900 p-5">
              <div className="mb-3 flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-slate-400">
                <Wallet className="h-4 w-4 text-emerald-400" />
                Receitas e Comissões
              </div>
              <div className="grid grid-cols-3 gap-2.5">
                <div className="rounded-xl bg-slate-950 p-3">
                  <p className="text-[10px] uppercase text-slate-400">Bruto</p>
                  <p className="mt-1 text-sm font-extrabold text-white">
                    {formatAOA(data?.earnings.gross_aoa ?? 0)}
                  </p>
                </div>
                <div className="rounded-xl bg-slate-950 p-3">
                  <p className="text-[10px] uppercase text-slate-400">Comissão</p>
                  <p className="mt-1 text-sm font-extrabold text-amber-400">
                    {formatAOA(data?.earnings.platform_commission_aoa ?? 0)}
                  </p>
                </div>
                <div className="rounded-xl bg-emerald-950/60 p-3 ring-1 ring-emerald-500/30">
                  <p className="text-[10px] uppercase text-emerald-300">Líquido</p>
                  <p className="mt-1 text-sm font-extrabold text-emerald-400">
                    {formatAOA(data?.earnings.driver_net_aoa ?? 0)}
                  </p>
                </div>
              </div>
            </div>

            {/* Opportunity Zones (Demand Pressure Intelligence) */}
            <div className="rounded-2xl border border-slate-800 bg-slate-900 p-5">
              <div className="mb-3 flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-slate-400">
                <TrendingUp className="h-4 w-4 text-amber-400" />
                Zonas com Maior Oportunidade (Luanda)
              </div>
              <div className="space-y-2">
                {data?.opportunity_zones.map((z) => (
                  <div
                    key={z.zone}
                    className="flex items-center justify-between rounded-xl bg-slate-950 px-3.5 py-2.5 text-xs"
                  >
                    <div>
                      <p className="font-bold text-white">{z.zone}</p>
                      <p className="text-[11px] text-slate-400">
                        Procura: {z.active_requests} • Veículos livres: {z.available_vehicles}
                      </p>
                    </div>
                    <span
                      className={`rounded-full px-2.5 py-0.5 text-[10px] font-extrabold ${
                        z.pressure_level === 'ELEVADA'
                          ? 'bg-red-500/20 text-red-300'
                          : z.pressure_level === 'MODERADA'
                            ? 'bg-amber-500/20 text-amber-300'
                            : 'bg-emerald-500/20 text-emerald-300'
                      }`}
                    >
                      {z.pressure_level}
                    </span>
                  </div>
                ))}
              </div>
            </div>

            {/* Vehicle Registration */}
            <div className="rounded-2xl border border-slate-800 bg-slate-900 p-5">
              <div className="mb-3 flex items-center justify-between">
                <span className="inline-flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-slate-400">
                  <Navigation className="h-4 w-4 text-emerald-400" /> Os Meus Veículos
                </span>
                <button
                  type="button"
                  onClick={() => setShowAddVehicle((s) => !s)}
                  className="inline-flex items-center gap-1 rounded-lg bg-slate-800 px-2.5 py-1 text-xs font-bold text-white hover:bg-slate-700"
                >
                  <Plus className="h-3.5 w-3.5" /> Novo
                </button>
              </div>

              {showAddVehicle && (
                <form onSubmit={handleRegisterVehicle} className="mb-3 space-y-2 rounded-xl bg-slate-950 p-3">
                  <div className="grid grid-cols-2 gap-2">
                    <input
                      required
                      placeholder="Marca (ex: Hyundai)"
                      value={vehForm.make}
                      onChange={(e) => setVehForm({ ...vehForm, make: e.target.value })}
                      className="rounded-lg border border-slate-700 bg-slate-900 px-2.5 py-1.5 text-xs text-white"
                    />
                    <input
                      required
                      placeholder="Modelo (ex: i10)"
                      value={vehForm.model}
                      onChange={(e) => setVehForm({ ...vehForm, model: e.target.value })}
                      className="rounded-lg border border-slate-700 bg-slate-900 px-2.5 py-1.5 text-xs text-white"
                    />
                  </div>
                  <div className="grid grid-cols-3 gap-2">
                    <input
                      required
                      placeholder="Matrícula LD"
                      value={vehForm.license_plate}
                      onChange={(e) => setVehForm({ ...vehForm, license_plate: e.target.value })}
                      className="rounded-lg border border-slate-700 bg-slate-900 px-2.5 py-1.5 text-xs text-white"
                    />
                    <input
                      placeholder="Cor"
                      value={vehForm.color}
                      onChange={(e) => setVehForm({ ...vehForm, color: e.target.value })}
                      className="rounded-lg border border-slate-700 bg-slate-900 px-2.5 py-1.5 text-xs text-white"
                    />
                    <input
                      type="number"
                      min={1}
                      max={50}
                      value={vehForm.capacity}
                      onChange={(e) => setVehForm({ ...vehForm, capacity: Number(e.target.value) })}
                      className="rounded-lg border border-slate-700 bg-slate-900 px-2.5 py-1.5 text-xs text-white"
                    />
                  </div>
                  <button
                    type="submit"
                    disabled={busy}
                    className="w-full rounded-lg bg-emerald-600 py-2 text-xs font-bold text-white"
                  >
                    Registar Veículo
                  </button>
                </form>
              )}

              <div className="space-y-2">
                {data?.vehicles.map((v) => (
                  <div
                    key={v.id}
                    className="flex items-center justify-between rounded-xl bg-slate-950 px-3 py-2.5 text-xs"
                  >
                    <div>
                      <p className="font-bold text-white">
                        {v.make} {v.model} ({v.year})
                      </p>
                      <p className="text-slate-400">
                        {v.color} • {v.capacity} lugares
                      </p>
                    </div>
                    <span className="font-mono-code rounded-md bg-slate-800 px-2 py-1 font-bold text-amber-300">
                      {v.license_plate}
                    </span>
                  </div>
                ))}
              </div>
            </div>

            {/* Recent Completed Trips */}
            {data && data.recent_trips.length > 0 && (
              <div className="rounded-2xl border border-slate-800 bg-slate-900 p-5">
                <p className="mb-3 text-xs font-bold uppercase tracking-wider text-slate-400">
                  Últimas Viagens Concluídas
                </p>
                <div className="space-y-2">
                  {data.recent_trips.slice(0, 5).map((t) => (
                    <div
                      key={t.id}
                      className="flex items-center justify-between rounded-xl bg-slate-950 px-3 py-2 text-xs"
                    >
                      <div>
                        <p className="font-bold text-white">
                          {t.request?.pickup_zone} → {t.request?.dropoff_zone}
                        </p>
                        <p className="text-[11px] text-slate-400">{formatLuandaTime(t.completed_at)}</p>
                      </div>
                      <span className="font-bold text-emerald-400">
                        +{formatAOA(t.commission?.driver_net_aoa ?? t.paid_total_aoa)}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
};
