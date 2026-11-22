import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Bell,
  Car,
  CheckCircle2,
  Clock,
  CreditCard,
  History,
  MapPin,
  Navigation,
  Plus,
  RefreshCw,
  ShieldCheck,
  Star,
  Trash2,
  Users,
  XCircle,
} from 'lucide-react';
import { LuandaMap, MapMarkerItem } from '../../components/LuandaMap';
import { MobilityCardVisual } from '../../components/MobilityCardVisual';
import { TopBar } from '../../components/TopBar';
import { useAuth } from '../../contexts/AuthContext';
import { apiRequest, formatAOA, formatLuandaTime } from '../../services/api';
import {
  CardTransactionDTO,
  LuandaStop,
  NotificationDTO,
  QuoteResponse,
  TransportCardDTO,
  TransportRequestDTO,
  TripDTO,
} from '../../types';

interface WalletPayload {
  wallet_id: number;
  balance_aoa: number;
  currency: string;
  is_locked: boolean;
  cards: TransportCardDTO[];
  transactions: CardTransactionDTO[];
}

export const PassengerApp: React.FC = () => {
  const { lastEvent, refreshProfile } = useAuth();
  const [tab, setTab] = useState<'ride' | 'card' | 'history'>('ride');
  const [stops, setStops] = useState<LuandaStop[]>([]);
  const [pickupZone, setPickupZone] = useState('Gamek');
  const [dropoffZone, setDropoffZone] = useState('Aeroporto');
  const [isGroupMode, setIsGroupMode] = useState(false);
  const [passengerCount, setPassengerCount] = useState(1);
  const [companionInput, setCompanionInput] = useState('');
  const [companions, setCompanions] = useState<{ card_code: string; passenger_name: string }[]>([]);
  const [quote, setQuote] = useState<QuoteResponse | null>(null);

  const [activeRequest, setActiveRequest] = useState<TransportRequestDTO | null>(null);
  const [activeTrip, setActiveTrip] = useState<TripDTO | null>(null);
  const [wallet, setWallet] = useState<WalletPayload | null>(null);
  const [history, setHistory] = useState<TripDTO[]>([]);
  const [notifications, setNotifications] = useState<NotificationDTO[]>([]);

  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<{ type: 'ok' | 'err'; text: string } | null>(null);
  const [ratingScore, setRatingScore] = useState(5);
  const [ratingComment, setRatingComment] = useState('');
  const [ratingTripId, setRatingTripId] = useState<number | null>(null);

  const loadAll = useCallback(async () => {
    try {
      const [stopsRes, activeRes, walletRes, histRes, notifRes] = await Promise.all([
        apiRequest<LuandaStop[]>('/mobility/stops'),
        apiRequest<{ active_request: TransportRequestDTO | null; active_trip: TripDTO | null }>(
          '/mobility/requests/active'
        ),
        apiRequest<WalletPayload>('/mobility/wallet'),
        apiRequest<TripDTO[]>('/mobility/trips/history'),
        apiRequest<NotificationDTO[]>('/mobility/notifications'),
      ]);
      setStops(stopsRes);
      setActiveRequest(activeRes.active_request);
      setActiveTrip(activeRes.active_trip);
      setWallet(walletRes);
      setHistory(histRes);
      setNotifications(notifRes);
    } catch {
      // ignore transient errors
    }
  }, []);

  useEffect(() => {
    loadAll();
    const timer = window.setInterval(loadAll, 6000);
    return () => window.clearInterval(timer);
  }, [loadAll]);

  useEffect(() => {
    if (!lastEvent) return;
    if (
      ['TRIP_ACCEPTED', 'TRIP_UPDATED', 'TRIP_COMPLETED', 'BOARDING_VALIDATED', 'DRIVER_LOCATION'].includes(
        lastEvent.event
      )
    ) {
      loadAll();
      refreshProfile();
    }
  }, [lastEvent, loadAll, refreshProfile]);

  const pickupStop = useMemo(
    () => stops.find((s) => s.zone_name === pickupZone) ?? stops[0],
    [stops, pickupZone]
  );
  const dropoffStop = useMemo(
    () => stops.find((s) => s.zone_name === dropoffZone) ?? stops[1] ?? stops[0],
    [stops, dropoffZone]
  );

  useEffect(() => {
    if (!pickupStop || !dropoffStop) return;
    const effectiveCount = isGroupMode ? Math.max(2, passengerCount, companions.length + 1) : 1;
    apiRequest<QuoteResponse>('/mobility/quote', {
      method: 'POST',
      body: JSON.stringify({
        pickup_lat: pickupStop.latitude,
        pickup_lng: pickupStop.longitude,
        dropoff_lat: dropoffStop.latitude,
        dropoff_lng: dropoffStop.longitude,
        passenger_count: effectiveCount,
      }),
    })
      .then(setQuote)
      .catch(() => setQuote(null));
  }, [pickupStop, dropoffStop, isGroupMode, passengerCount, companions.length]);

  const handleAddCompanion = async () => {
    if (!companionInput.trim()) return;
    setFeedback(null);
    try {
      const res = await apiRequest<{ valid: boolean; card_code: string; passenger_name: string }>(
        '/mobility/cards/verify-companion',
        {
          method: 'POST',
          body: JSON.stringify({ card_identifier: companionInput.trim() }),
        }
      );
      if (companions.some((c) => c.card_code === res.card_code)) {
        setFeedback({ type: 'err', text: 'Este cartão já foi adicionado ao grupo.' });
        return;
      }
      const next = [...companions, { card_code: res.card_code, passenger_name: res.passenger_name }];
      setCompanions(next);
      setPassengerCount(Math.max(passengerCount, next.length + 1));
      setCompanionInput('');
      setFeedback({ type: 'ok', text: `Cartão ${res.card_code} (${res.passenger_name}) validado para o grupo.` });
    } catch (err) {
      setFeedback({ type: 'err', text: err instanceof Error ? err.message : 'Cartão inválido.' });
    }
  };

  const handleCreateRequest = async () => {
    if (!pickupStop || !dropoffStop) return;
    if (pickupStop.zone_name === dropoffStop.zone_name) {
      setFeedback({ type: 'err', text: 'Selecione uma origem e um destino diferentes.' });
      return;
    }
    setBusy(true);
    setFeedback(null);
    try {
      const effectiveCount = isGroupMode ? Math.max(2, passengerCount, companions.length + 1) : 1;
      const res = await apiRequest<{
        request: TransportRequestDTO;
        matched_driver_found: boolean;
        estimated_driver_eta_min?: number;
      }>('/mobility/requests', {
        method: 'POST',
        body: JSON.stringify({
          pickup_label: pickupStop.name,
          pickup_zone: pickupStop.zone_name,
          pickup_lat: pickupStop.latitude,
          pickup_lng: pickupStop.longitude,
          dropoff_label: dropoffStop.name,
          dropoff_zone: dropoffStop.zone_name,
          dropoff_lat: dropoffStop.latitude,
          dropoff_lng: dropoffStop.longitude,
          passenger_count: effectiveCount,
          request_type: isGroupMode ? 'GROUP' : 'INDIVIDUAL',
          companion_card_codes: isGroupMode ? companions.map((c) => c.card_code) : [],
          include_requester_card: true,
        }),
      });
      setActiveRequest(res.request);
      setFeedback({
        type: 'ok',
        text: res.matched_driver_found
          ? `Solicitação enviada! Motorista disponível encontrado (~${res.estimated_driver_eta_min ?? 4} min). A aguardar aceitação...`
          : 'Solicitação registada! A procurar motoristas disponíveis na zona...',
      });
      await loadAll();
    } catch (err) {
      setFeedback({ type: 'err', text: err instanceof Error ? err.message : 'Erro ao solicitar transporte.' });
    } finally {
      setBusy(false);
    }
  };

  const handleCancelRequest = async () => {
    if (!activeRequest) return;
    setBusy(true);
    try {
      await apiRequest(`/mobility/requests/${activeRequest.id}/cancel`, { method: 'POST' });
      setActiveRequest(null);
      setFeedback({ type: 'ok', text: 'Solicitação cancelada.' });
      await loadAll();
    } catch (err) {
      setFeedback({ type: 'err', text: err instanceof Error ? err.message : 'Erro ao cancelar.' });
    } finally {
      setBusy(false);
    }
  };

  const handleSubmitRating = async (tripId: number) => {
    setBusy(true);
    try {
      await apiRequest(`/mobility/trips/${tripId}/rate`, {
        method: 'POST',
        body: JSON.stringify({ score: ratingScore, comment: ratingComment }),
      });
      setRatingTripId(null);
      setRatingComment('');
      setFeedback({ type: 'ok', text: 'Obrigado pela sua avaliação!' });
      await loadAll();
    } catch (err) {
      setFeedback({ type: 'err', text: err instanceof Error ? err.message : 'Erro ao avaliar.' });
    } finally {
      setBusy(false);
    }
  };

  const mapMarkers: MapMarkerItem[] = useMemo(() => {
    const items: MapMarkerItem[] = [];
    if (activeTrip?.request) {
      items.push({
        id: 'pickup',
        lat: activeTrip.request.pickup_lat,
        lng: activeTrip.request.pickup_lng,
        label: `Recolha: ${activeTrip.request.pickup_zone}`,
        sublabel: activeTrip.request.pickup_label,
        kind: 'pickup',
      });
      items.push({
        id: 'dropoff',
        lat: activeTrip.request.dropoff_lat,
        lng: activeTrip.request.dropoff_lng,
        label: `Destino: ${activeTrip.request.dropoff_zone}`,
        sublabel: activeTrip.request.dropoff_label,
        kind: 'dropoff',
      });
      if (activeTrip.driver?.current_lat && activeTrip.driver?.current_lng) {
        items.push({
          id: 'driver',
          lat: activeTrip.driver.current_lat,
          lng: activeTrip.driver.current_lng,
          label: `${activeTrip.vehicle?.make ?? ''} ${activeTrip.vehicle?.model ?? ''}`,
          sublabel: `${activeTrip.driver.full_name} • ${activeTrip.vehicle?.license_plate ?? ''}`,
          kind: 'vehicle_busy',
        });
      }
    } else if (pickupStop && dropoffStop) {
      items.push({
        id: 'pickup',
        lat: pickupStop.latitude,
        lng: pickupStop.longitude,
        label: `Origem: ${pickupStop.zone_name}`,
        sublabel: pickupStop.name,
        kind: 'pickup',
      });
      items.push({
        id: 'dropoff',
        lat: dropoffStop.latitude,
        lng: dropoffStop.longitude,
        label: `Destino: ${dropoffStop.zone_name}`,
        sublabel: dropoffStop.name,
        kind: 'dropoff',
      });
    }
    return items;
  }, [activeTrip, pickupStop, dropoffStop]);

  const routeLine: [number, number][] = useMemo(() => {
    if (activeTrip?.request) {
      return [
        [activeTrip.request.pickup_lat, activeTrip.request.pickup_lng],
        [activeTrip.request.dropoff_lat, activeTrip.request.dropoff_lng],
      ];
    }
    if (pickupStop && dropoffStop) {
      return [
        [pickupStop.latitude, pickupStop.longitude],
        [dropoffStop.latitude, dropoffStop.longitude],
      ];
    }
    return [];
  }, [activeTrip, pickupStop, dropoffStop]);

  const primaryCard = wallet?.cards[0];

  return (
    <div className="min-h-screen bg-slate-50 pb-20">
      <TopBar />

      <main className="mx-auto max-w-5xl px-4 py-5">
        {/* Top Balance & Navigation Strip */}
        <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-2 rounded-2xl bg-white p-1.5 shadow-xs ring-1 ring-slate-200">
            {[
              { id: 'ride', label: 'Solicitar Viagem', icon: Navigation },
              { id: 'card', label: 'Cartão QR & Saldo', icon: CreditCard },
              { id: 'history', label: 'Histórico', icon: History },
            ].map((item) => {
              const Icon = item.icon;
              const active = tab === item.id;
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => setTab(item.id as 'ride' | 'card' | 'history')}
                  className={`inline-flex flex-1 items-center justify-center gap-1.5 rounded-xl px-3.5 py-2 text-xs font-bold transition sm:flex-none ${
                    active ? 'bg-emerald-700 text-white shadow-xs' : 'text-slate-600 hover:bg-slate-100'
                  }`}
                >
                  <Icon className="h-4 w-4" />
                  {item.label}
                </button>
              );
            })}
          </div>

          <div className="flex items-center justify-between gap-3 rounded-2xl bg-slate-900 px-4 py-2.5 text-white shadow-xs">
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                Cartão {primaryCard?.card_code ?? '—'}
              </p>
              <p className="text-base font-extrabold text-emerald-400">
                {formatAOA(wallet?.balance_aoa ?? 0)}
              </p>
            </div>
            <button
              type="button"
              onClick={loadAll}
              className="rounded-lg bg-slate-800 p-2 text-slate-300 transition hover:bg-slate-700 hover:text-white"
              title="Atualizar estado"
            >
              <RefreshCw className="h-4 w-4" />
            </button>
          </div>
        </div>

        {feedback && (
          <div
            className={`mb-4 flex items-center justify-between rounded-xl border px-4 py-3 text-xs font-semibold ${
              feedback.type === 'ok'
                ? 'border-emerald-200 bg-emerald-50 text-emerald-900'
                : 'border-red-200 bg-red-50 text-red-800'
            }`}
          >
            <span>{feedback.text}</span>
            <button type="button" onClick={() => setFeedback(null)} className="ml-3 text-slate-400 hover:text-slate-700">
              ✕
            </button>
          </div>
        )}

        {/* TAB 1: RIDE */}
        {tab === 'ride' && (
          <div className="grid gap-5 lg:grid-cols-12">
            <div className="space-y-4 lg:col-span-7">
              <LuandaMap heightClass="h-80 sm:h-96" markers={mapMarkers} routeLine={routeLine} />

              {/* Recent Notifications */}
              {notifications.length > 0 && (
                <div className="rounded-2xl border border-slate-200 bg-white p-4">
                  <div className="mb-2.5 flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-slate-500">
                    <Bell className="h-4 w-4 text-emerald-700" />
                    Notificações em Tempo Real
                  </div>
                  <div className="space-y-2">
                    {notifications.slice(0, 4).map((n) => (
                      <div key={n.id} className="rounded-xl bg-slate-50 px-3 py-2 text-xs">
                        <div className="flex items-center justify-between gap-2">
                          <span className="font-bold text-slate-900">{n.title}</span>
                          <span className="text-[10px] text-slate-400">{formatLuandaTime(n.created_at)}</span>
                        </div>
                        <p className="mt-0.5 text-slate-600">{n.message}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            <div className="space-y-4 lg:col-span-5">
              {/* ACTIVE TRIP TRACKER */}
              {activeTrip ? (
                <div className="space-y-4 rounded-2xl border border-emerald-200 bg-white p-5 shadow-sm">
                  <div className="flex items-center justify-between">
                    <span className="rounded-full bg-emerald-100 px-3 py-1 text-xs font-bold text-emerald-800">
                      {activeTrip.status === 'DRIVER_EN_ROUTE' && 'Motorista a caminho'}
                      {activeTrip.status === 'DRIVER_ARRIVED' && 'Motorista chegou! Apresente o QR'}
                      {activeTrip.status === 'IN_PROGRESS' && 'Viagem em curso'}
                    </span>
                    <span className="inline-flex items-center gap-1 text-xs font-bold text-slate-700">
                      <Clock className="h-3.5 w-3.5 text-amber-600" />
                      ETA {activeTrip.eta_minutes} min
                    </span>
                  </div>

                  {/* Driver & Vehicle Identification */}
                  <div className="rounded-xl bg-slate-900 p-4 text-white">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-xs text-slate-400">Veículo atribuído</p>
                        <p className="text-lg font-extrabold">
                          {activeTrip.vehicle?.make} {activeTrip.vehicle?.model}
                        </p>
                        <p className="text-xs text-slate-300">
                          {activeTrip.vehicle?.color} • {activeTrip.vehicle?.capacity} lugares
                        </p>
                      </div>
                      <div className="text-right">
                        <span className="font-mono-code rounded-lg bg-amber-500 px-2.5 py-1 text-xs font-extrabold text-slate-950">
                          {activeTrip.vehicle?.license_plate}
                        </span>
                        <p className="mt-1.5 text-xs text-slate-300">{activeTrip.driver?.full_name}</p>
                      </div>
                    </div>

                    <div className="mt-3 flex items-center justify-between border-t border-slate-800 pt-3">
                      <div>
                        <p className="text-[11px] text-slate-400">Código de Embarque</p>
                        <p className="font-mono-code text-xl font-extrabold tracking-widest text-emerald-400">
                          {activeTrip.boarding_code}
                        </p>
                      </div>
                      <div className="text-right">
                        <p className="text-[11px] text-slate-400">Tarifa Total</p>
                        <p className="text-base font-extrabold">{formatAOA(activeTrip.total_fare_aoa)}</p>
                        <p className="text-[11px] text-emerald-400">
                          Pago: {formatAOA(activeTrip.paid_total_aoa)}
                        </p>
                      </div>
                    </div>
                  </div>

                  {/* Boarding Status */}
                  <div className="space-y-2">
                    <p className="text-xs font-bold text-slate-700">
                      Passageiros validados ({activeTrip.boarded_count}/{activeTrip.request?.passenger_count ?? 1})
                    </p>
                    {activeTrip.boarded_passengers.length === 0 ? (
                      <div className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">
                        Apresente o seu cartão QR (<strong>{primaryCard?.card_code}</strong>) ao motorista no
                        embarque para validação e débito automático.
                      </div>
                    ) : (
                      activeTrip.boarded_passengers.map((bp) => (
                        <div
                          key={bp.id}
                          className="flex items-center justify-between rounded-xl bg-emerald-50 px-3 py-2 text-xs text-emerald-900"
                        >
                          <span className="inline-flex items-center gap-1.5 font-semibold">
                            <CheckCircle2 className="h-4 w-4 text-emerald-700" />
                            {bp.passenger_name} ({bp.card_code})
                          </span>
                          <span className="font-bold">{formatAOA(bp.fare_charged_aoa)}</span>
                        </div>
                      ))
                    )}
                  </div>

                  {primaryCard && <MobilityCardVisual card={primaryCard} compact />}
                </div>
              ) : activeRequest ? (
                /* PENDING / OFFERED REQUEST */
                <div className="space-y-4 rounded-2xl border border-amber-200 bg-white p-5 shadow-sm">
                  <div className="flex items-center gap-2">
                    <span className="h-2.5 w-2.5 animate-ping rounded-full bg-amber-500" />
                    <h2 className="text-base font-bold text-slate-900">
                      A procurar motorista disponível...
                    </h2>
                  </div>

                  <div className="space-y-2 rounded-xl bg-slate-50 p-3.5 text-xs">
                    <div className="flex justify-between">
                      <span className="text-slate-500">Origem</span>
                      <span className="font-bold text-slate-900">{activeRequest.pickup_zone}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-500">Destino</span>
                      <span className="font-bold text-slate-900">{activeRequest.dropoff_zone}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-500">Passageiros</span>
                      <span className="font-bold text-slate-900">
                        {activeRequest.passenger_count} ({activeRequest.request_type})
                      </span>
                    </div>
                    <div className="flex justify-between border-t border-slate-200 pt-2">
                      <span className="text-slate-500">Tarifa estimada</span>
                      <span className="text-sm font-extrabold text-emerald-700">
                        {formatAOA(activeRequest.estimated_total_fare_aoa)}
                      </span>
                    </div>
                  </div>

                  {activeRequest.group_members.length > 0 && (
                    <div className="space-y-1.5">
                      <p className="text-xs font-bold text-slate-700">Cartões associados ao grupo</p>
                      {activeRequest.group_members.map((gm) => (
                        <div
                          key={gm.id}
                          className="flex items-center justify-between rounded-lg bg-slate-100 px-3 py-1.5 text-xs"
                        >
                          <span>
                            {gm.passenger_name} (<strong className="font-mono-code">{gm.card_code}</strong>)
                          </span>
                          <span className="font-semibold">{formatAOA(gm.individual_fare_aoa)}</span>
                        </div>
                      ))}
                    </div>
                  )}

                  <button
                    type="button"
                    disabled={busy}
                    onClick={handleCancelRequest}
                    className="inline-flex w-full items-center justify-center gap-2 rounded-xl border border-red-200 bg-red-50 py-2.5 text-xs font-bold text-red-700 transition hover:bg-red-100"
                  >
                    <XCircle className="h-4 w-4" />
                    Cancelar Solicitação
                  </button>
                </div>
              ) : (
                /* NEW BOOKING FORM */
                <div className="space-y-4 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                  <div className="flex items-center justify-between">
                    <h2 className="text-base font-bold text-slate-900">Para onde vamos em Luanda?</h2>
                    <div className="flex rounded-lg bg-slate-100 p-0.5 text-xs font-bold">
                      <button
                        type="button"
                        onClick={() => {
                          setIsGroupMode(false);
                          setPassengerCount(1);
                        }}
                        className={`rounded-md px-2.5 py-1 transition ${
                          !isGroupMode ? 'bg-white text-slate-900 shadow-xs' : 'text-slate-500'
                        }`}
                      >
                        Individual
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          setIsGroupMode(true);
                          setPassengerCount(Math.max(2, companions.length + 1));
                        }}
                        className={`inline-flex items-center gap-1 rounded-md px-2.5 py-1 transition ${
                          isGroupMode ? 'bg-white text-emerald-800 shadow-xs' : 'text-slate-500'
                        }`}
                      >
                        <Users className="h-3.5 w-3.5" /> Grupo
                      </button>
                    </div>
                  </div>

                  <div className="space-y-3">
                    <div>
                      <label className="mb-1 flex items-center gap-1.5 text-xs font-semibold text-slate-700">
                        <MapPin className="h-3.5 w-3.5 text-emerald-700" /> Ponto de Recolha
                      </label>
                      <select
                        id="passenger-pickup-select"
                        value={pickupZone}
                        onChange={(e) => setPickupZone(e.target.value)}
                        className="w-full rounded-xl border border-slate-300 bg-white px-3 py-2.5 text-sm font-medium focus:border-emerald-600 focus:outline-none"
                      >
                        {stops.map((s) => (
                          <option key={s.id} value={s.zone_name}>
                            {s.zone_name} — {s.name}
                          </option>
                        ))}
                      </select>
                    </div>

                    <div>
                      <label className="mb-1 flex items-center gap-1.5 text-xs font-semibold text-slate-700">
                        <Navigation className="h-3.5 w-3.5 text-amber-600" /> Destino
                      </label>
                      <select
                        id="passenger-dropoff-select"
                        value={dropoffZone}
                        onChange={(e) => setDropoffZone(e.target.value)}
                        className="w-full rounded-xl border border-slate-300 bg-white px-3 py-2.5 text-sm font-medium focus:border-emerald-600 focus:outline-none"
                      >
                        {stops.map((s) => (
                          <option key={s.id} value={s.zone_name}>
                            {s.zone_name} — {s.name}
                          </option>
                        ))}
                      </select>
                    </div>
                  </div>

                  {/* Group Passenger Cards */}
                  {isGroupMode && (
                    <div className="space-y-2.5 rounded-xl border border-slate-200 bg-slate-50 p-3.5">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-bold text-slate-800">
                          Passageiros no Grupo (validação individual)
                        </span>
                        <input
                          type="number"
                          min={2}
                          max={12}
                          value={passengerCount}
                          onChange={(e) => setPassengerCount(Math.max(2, Number(e.target.value)))}
                          className="w-16 rounded-lg border border-slate-300 bg-white px-2 py-1 text-center text-xs font-bold"
                        />
                      </div>

                      <div className="flex gap-2">
                        <input
                          type="text"
                          value={companionInput}
                          onChange={(e) => setCompanionInput(e.target.value)}
                          placeholder="Adicionar cartão QR (ex: MOB-000002)"
                          className="font-mono-code flex-1 rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-xs"
                        />
                        <button
                          type="button"
                          onClick={handleAddCompanion}
                          className="inline-flex items-center gap-1 rounded-lg bg-slate-900 px-3 py-1.5 text-xs font-bold text-white hover:bg-slate-800"
                        >
                          <Plus className="h-3.5 w-3.5" /> Validar
                        </button>
                      </div>

                      {companions.length > 0 && (
                        <div className="space-y-1">
                          {companions.map((c) => (
                            <div
                              key={c.card_code}
                              className="flex items-center justify-between rounded-lg bg-white px-2.5 py-1.5 text-xs ring-1 ring-slate-200"
                            >
                              <span>
                                <strong>{c.card_code}</strong> • {c.passenger_name}
                              </span>
                              <button
                                type="button"
                                onClick={() =>
                                  setCompanions(companions.filter((x) => x.card_code !== c.card_code))
                                }
                                className="text-red-500 hover:text-red-700"
                              >
                                <Trash2 className="h-3.5 w-3.5" />
                              </button>
                            </div>
                          ))}
                        </div>
                      )}
                      <p className="text-[11px] text-slate-500">
                        Cada passageiro paga individualmente com o seu próprio cartão no embarque.
                      </p>
                    </div>
                  )}

                  {/* Fare Estimate Box */}
                  {quote && (
                    <div className="rounded-xl bg-emerald-50/80 p-4 ring-1 ring-emerald-200">
                      <div className="flex items-center justify-between text-xs text-emerald-900">
                        <span>
                          Distância: <strong>{quote.distance_km} km</strong> • Tempo:{' '}
                          <strong>~{quote.duration_min} min</strong>
                        </span>
                        <span className="font-semibold">
                          {formatAOA(quote.fare_per_passenger_aoa)} / pass.
                        </span>
                      </div>
                      <div className="mt-2 flex items-baseline justify-between border-t border-emerald-200/80 pt-2">
                        <span className="text-xs font-bold uppercase tracking-wider text-emerald-800">
                          Tarifa Estimada Total
                        </span>
                        <span className="text-2xl font-extrabold text-emerald-900">
                          {formatAOA(quote.total_fare_aoa)}
                        </span>
                      </div>
                    </div>
                  )}

                  <button
                    id="passenger-request-ride-btn"
                    type="button"
                    disabled={busy || !quote}
                    onClick={handleCreateRequest}
                    className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-emerald-700 py-3.5 text-sm font-bold text-white shadow-sm transition hover:bg-emerald-800 disabled:opacity-50"
                  >
                    <Car className="h-5 w-5" />
                    {busy ? 'A procurar motorista...' : 'Confirmar Solicitação de Transporte'}
                  </button>
                </div>
              )}
            </div>
          </div>
        )}

        {/* TAB 2: CARD & WALLET */}
        {tab === 'card' && (
          <div className="space-y-6">
            {primaryCard && <MobilityCardVisual card={primaryCard} />}

            <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-xs">
              <div className="mb-4 flex items-center justify-between">
                <h2 className="text-base font-bold text-slate-900">Histórico de Transações da Carteira</h2>
                <span className="inline-flex items-center gap-1 text-xs font-medium text-emerald-700">
                  <ShieldCheck className="h-4 w-4" /> Registo Auditável no Servidor
                </span>
              </div>

              {wallet && wallet.transactions.length > 0 ? (
                <div className="divide-y divide-slate-100">
                  {wallet.transactions.map((tx) => {
                    const isDebit = tx.tx_type === 'TRIP_DEBIT';
                    return (
                      <div key={tx.id} className="flex items-center justify-between gap-3 py-3 text-xs">
                        <div>
                          <p className="font-bold text-slate-900">{tx.description}</p>
                          <p className="mt-0.5 text-slate-500">
                            {formatLuandaTime(tx.created_at)} • {tx.card_code} • Saldo após:{' '}
                            <strong>{formatAOA(tx.balance_after_aoa)}</strong>
                          </p>
                        </div>
                        <span
                          className={`whitespace-nowrap font-mono-code text-sm font-extrabold ${
                            isDebit ? 'text-red-600' : 'text-emerald-700'
                          }`}
                        >
                          {isDebit ? '-' : '+'}
                          {formatAOA(tx.amount_aoa)}
                        </span>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <p className="text-xs text-slate-500">Ainda sem transações registadas.</p>
              )}
            </div>
          </div>
        )}

        {/* TAB 3: HISTORY & RATING */}
        {tab === 'history' && (
          <div className="space-y-4">
            <h2 className="text-base font-bold text-slate-900">Histórico de Viagens</h2>
            {history.length === 0 ? (
              <div className="rounded-2xl border border-slate-200 bg-white p-8 text-center text-sm text-slate-500">
                Ainda não realizou viagens. Solicite a sua primeira viagem de Gamek para o Aeroporto!
              </div>
            ) : (
              history.map((t) => (
                <div
                  key={t.id}
                  className="rounded-2xl border border-slate-200 bg-white p-4 shadow-xs"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <p className="text-sm font-bold text-slate-900">
                        {t.request?.pickup_zone} → {t.request?.dropoff_zone}
                      </p>
                      <p className="text-xs text-slate-500">
                        {formatLuandaTime(t.completed_at ?? t.accepted_at)} • {t.vehicle?.make}{' '}
                        {t.vehicle?.model} ({t.vehicle?.license_plate}) • {t.driver?.full_name}
                      </p>
                    </div>
                    <div className="text-right">
                      <p className="text-sm font-extrabold text-emerald-700">
                        {formatAOA(t.paid_total_aoa || t.total_fare_aoa)}
                      </p>
                      <span className="rounded-full bg-slate-100 px-2.5 py-0.5 text-[11px] font-bold text-slate-700">
                        {t.status}
                      </span>
                    </div>
                  </div>

                  {t.status === 'COMPLETED' && !t.rating && (
                    <div className="mt-3 border-t border-slate-100 pt-3">
                      {ratingTripId === t.id ? (
                        <div className="space-y-2">
                          <div className="flex items-center gap-1">
                            {[1, 2, 3, 4, 5].map((star) => (
                              <button
                                key={star}
                                type="button"
                                onClick={() => setRatingScore(star)}
                                className="p-1"
                              >
                                <Star
                                  className={`h-5 w-5 ${
                                    star <= ratingScore
                                      ? 'fill-amber-400 text-amber-400'
                                      : 'text-slate-300'
                                  }`}
                                />
                              </button>
                            ))}
                          </div>
                          <div className="flex gap-2">
                            <input
                              type="text"
                              value={ratingComment}
                              onChange={(e) => setRatingComment(e.target.value)}
                              placeholder="Comentário opcional sobre a viagem..."
                              className="flex-1 rounded-lg border border-slate-300 px-3 py-1.5 text-xs"
                            />
                            <button
                              type="button"
                              disabled={busy}
                              onClick={() => handleSubmitRating(t.id)}
                              className="rounded-lg bg-emerald-700 px-3.5 py-1.5 text-xs font-bold text-white"
                            >
                              Enviar
                            </button>
                          </div>
                        </div>
                      ) : (
                        <button
                          type="button"
                          onClick={() => setRatingTripId(t.id)}
                          className="inline-flex items-center gap-1 text-xs font-bold text-amber-700 hover:underline"
                        >
                          <Star className="h-3.5 w-3.5" /> Avaliar esta viagem
                        </button>
                      )}
                    </div>
                  )}

                  {t.rating && (
                    <p className="mt-2 text-xs font-medium text-amber-700">
                      Avaliação atribuída: {'★'.repeat(t.rating.score)} {t.rating.comment ? `— "${t.rating.comment}"` : ''}
                    </p>
                  )}
                </div>
              ))
            )}
          </div>
        )}
      </main>
    </div>
  );
};
