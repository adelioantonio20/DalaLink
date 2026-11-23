import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  AlertCircle,
  CheckCircle2,
  Clock,
  Compass,
  History,
  Info,
  Map as MapIcon,
  MapPin,
  Navigation,
  RefreshCw,
  Search,
  ShieldCheck,
  TrendingDown,
  TrendingUp,
  User as UserIcon,
  Users,
  XCircle,
} from 'lucide-react';
import { DemandCircleItem, LuandaMap, MapMarkerItem } from '../../components/LuandaMap';
import { TopBar } from '../../components/TopBar';
import { useAuth } from '../../contexts/AuthContext';
import { apiRequest, formatLuandaTime } from '../../services/api';
import {
  CorridorStatusDTO,
  GeographyDTO,
  IntentionDTO,
  TaxiStopDTO,
} from '../../types';

const DEMAND_LABELS: Record<string, { text: string; cls: string }> = {
  PROCURA_ELEVADA: { text: 'Procura elevada', cls: 'bg-red-100 text-red-800' },
  PROCURA_MODERADA: { text: 'Procura moderada', cls: 'bg-amber-100 text-amber-800' },
  PROCURA_BAIXA: { text: 'Procura baixa', cls: 'bg-emerald-100 text-emerald-800' },
  INSUFFICIENT_DATA: { text: 'Informação insuficiente', cls: 'bg-slate-100 text-slate-600' },
};

const SUPPLY_LABELS: Record<string, { text: string; cls: string }> = {
  OFERTA_ELEVADA: { text: 'Oferta elevada', cls: 'bg-emerald-100 text-emerald-800' },
  OFERTA_MODERADA: { text: 'Oferta moderada', cls: 'bg-amber-100 text-amber-800' },
  OFERTA_REDUZIDA: { text: 'Oferta reduzida', cls: 'bg-red-100 text-red-800' },
  INSUFFICIENT_DATA: { text: 'Sem oferta sinalizada', cls: 'bg-slate-100 text-slate-600' },
};

const ROAD_LABELS: Record<string, string> = {
  NORMAL: 'Circulação normal',
  MODERATE_TRAFFIC: 'Trânsito moderado',
  HEAVY_TRAFFIC: 'Trânsito intenso',
  DISRUPTED: 'Via condicionada',
};

export const PassengerApp: React.FC = () => {
  const { user, lastEvent } = useAuth();
  const [tab, setTab] = useState<'consult' | 'map' | 'history' | 'profile'>('consult');
  const [geo, setGeo] = useState<GeographyDTO | null>(null);
  const [originZone, setOriginZone] = useState('Gamek');
  const [destinationZone, setDestinationZone] = useState('Maianga');
  const [passengerCount, setPassengerCount] = useState(1);

  const [corridor, setCorridor] = useState<CorridorStatusDTO | null>(null);
  const [mapStops, setMapStops] = useState<TaxiStopDTO[]>([]);
  const [allRoutes, setAllRoutes] = useState<CorridorStatusDTO[]>([]);
  const [mapFilterZone, setMapFilterZone] = useState('');
  const [mapFilterDemand, setMapFilterDemand] = useState('');

  const [myActive, setMyActive] = useState<IntentionDTO | null>(null);
  const [myHistory, setMyHistory] = useState<IntentionDTO[]>([]);
  const [consultHistory, setConsultHistory] = useState<{ origin: string; dest: string; time: string }[]>([]);

  const [busy, setBusy] = useState(false);
  const [banner, setBanner] = useState<{ type: 'ok' | 'err'; text: string } | null>(null);

  const consultCorridor = useCallback(
    async (oz: string, dz: string, track = false) => {
      try {
        const res = await apiRequest<CorridorStatusDTO>(
          `/info/corridor?origin_zone=${encodeURIComponent(oz)}&destination_zone=${encodeURIComponent(dz)}`
        );
        setCorridor(res);
        if (track) {
          setConsultHistory((prev) => [
            { origin: oz, dest: dz, time: new Date().toLocaleTimeString('pt-PT', { hour: '2-digit', minute: '2-digit' }) },
            ...prev.slice(0, 9),
          ]);
        }
      } catch {
        // ignore transient error
      }
    },
    []
  );

  const loadAll = useCallback(async () => {
    try {
      const mapParams = new URLSearchParams();
      if (mapFilterZone) mapParams.set('zone', mapFilterZone);
      if (mapFilterDemand) mapParams.set('demand_level', mapFilterDemand);

      const [geoRes, mineRes, mapRes] = await Promise.all([
        apiRequest<GeographyDTO>('/info/geography'),
        apiRequest<{ active: IntentionDTO | null; history: IntentionDTO[] }>('/info/intentions/mine'),
        apiRequest<{ stops: TaxiStopDTO[]; routes: CorridorStatusDTO[] }>(
          `/info/map${mapParams.toString() ? `?${mapParams}` : ''}`
        ),
      ]);
      setGeo(geoRes);
      setMyActive(mineRes.active);
      setMyHistory(mineRes.history);
      setMapStops(mapRes.stops);
      setAllRoutes(mapRes.routes);
      await consultCorridor(originZone, destinationZone);
    } catch {
      // ignore transient error
    }
  }, [originZone, destinationZone, mapFilterZone, mapFilterDemand, consultCorridor]);

  useEffect(() => {
    loadAll();
    const timer = window.setInterval(loadAll, 12000);
    return () => window.clearInterval(timer);
  }, [loadAll]);

  useEffect(() => {
    if (lastEvent) loadAll();
  }, [lastEvent, loadAll]);

  const handleDeclareIntention = async () => {
    if (originZone === destinationZone) {
      setBanner({ type: 'err', text: 'Seleccione uma origem e um destino diferentes.' });
      return;
    }
    setBusy(true);
    setBanner(null);
    try {
      const res = await apiRequest<{ intention: IntentionDTO; corridor: CorridorStatusDTO }>(
        '/info/intentions',
        {
          method: 'POST',
          body: JSON.stringify({
            origin_zone: originZone,
            destination_zone: destinationZone,
            passenger_count: passengerCount,
          }),
        }
      );
      setMyActive(res.intention);
      setBanner({
        type: 'ok',
        text: `Intenção declarada (${originZone} → ${destinationZone}). Quando chegar à paragem, confirme a sua presença.`,
      });
      await loadAll();
    } catch (err) {
      setBanner({ type: 'err', text: err instanceof Error ? err.message : 'Erro ao declarar intenção.' });
    } finally {
      setBusy(false);
    }
  };

  const handleConfirmAtStop = async () => {
    if (!myActive) return;
    setBusy(true);
    setBanner(null);
    try {
      const originStop = geo?.stops.find((s) => s.zone_name === myActive.origin_zone);
      await apiRequest(`/info/intentions/${myActive.id}/confirm-at-stop`, {
        method: 'POST',
        body: JSON.stringify({
          latitude: originStop?.latitude,
          longitude: originStop?.longitude,
        }),
      });
      setBanner({
        type: 'ok',
        text: `Presença confirmada na paragem (${myActive.origin_zone}). O seu registo conta agora como procura confirmada.`,
      });
      await loadAll();
    } catch (err) {
      setBanner({ type: 'err', text: err instanceof Error ? err.message : 'Erro ao confirmar presença.' });
    } finally {
      setBusy(false);
    }
  };

  const handleCancelIntention = async () => {
    if (!myActive) return;
    setBusy(true);
    try {
      await apiRequest(`/info/intentions/${myActive.id}/cancel`, { method: 'POST' });
      setMyActive(null);
      setBanner({ type: 'ok', text: 'Intenção de viagem cancelada.' });
      await loadAll();
    } catch (err) {
      setBanner({ type: 'err', text: err instanceof Error ? err.message : 'Erro ao cancelar.' });
    } finally {
      setBusy(false);
    }
  };

  const mapMarkers: MapMarkerItem[] = useMemo(() => {
    return mapStops.map((s) => ({
      id: `stop-${s.id}`,
      lat: s.latitude,
      lng: s.longitude,
      label: s.name,
      sublabel: `${s.zone_name} • Procura est.: ${s.estimated_demand ?? 0} | Táxis: ${s.total_supply ?? 0}`,
      kind:
        s.zone_name === originZone
          ? 'pickup'
          : s.zone_name === destinationZone
            ? 'dropoff'
            : s.demand_level === 'PROCURA_ELEVADA'
              ? 'request'
              : 'stop',
    }));
  }, [mapStops, originZone, destinationZone]);

  const demandCircles: DemandCircleItem[] = useMemo(() => {
    return mapStops
      .filter((s) => (s.estimated_demand ?? 0) > 0 || (s.total_supply ?? 0) > 0)
      .map((s) => ({
        zone: s.zone_name,
        lat: s.latitude,
        lng: s.longitude,
        level:
          s.demand_level === 'PROCURA_ELEVADA'
            ? 'ELEVADA'
            : s.demand_level === 'PROCURA_MODERADA'
              ? 'MODERADA'
              : 'BAIXA',
        activeRequests: s.estimated_demand ?? 0,
        availableVehicles: s.total_supply ?? 0,
      }));
  }, [mapStops]);

  const routeLine: [number, number][] = useMemo(() => {
    const o = geo?.zones.find((z) => z.name === originZone);
    const d = geo?.zones.find((z) => z.name === destinationZone);
    if (!o || !d) return [];
    return [
      [o.latitude, o.longitude],
      [d.latitude, d.longitude],
    ];
  }, [geo, originZone, destinationZone]);

  const dMeta = DEMAND_LABELS[corridor?.demand_level ?? 'INSUFFICIENT_DATA'];
  const sMeta = SUPPLY_LABELS[corridor?.supply_level ?? 'INSUFFICIENT_DATA'];

  return (
    <div className="min-h-screen bg-slate-50 pb-20">
      <TopBar />

      <main className="mx-auto max-w-5xl space-y-5 px-4 py-5">
        {/* Clean Navigation */}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap gap-1.5 rounded-2xl bg-white p-1.5 shadow-xs ring-1 ring-slate-200">
            {[
              { id: 'consult', label: 'Consultar Via', icon: Search },
              { id: 'map', label: 'Mapa de Luanda', icon: MapIcon },
              { id: 'history', label: 'Histórico', icon: History },
              { id: 'profile', label: 'Perfil', icon: UserIcon },
            ].map((item) => {
              const Icon = item.icon;
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => setTab(item.id as typeof tab)}
                  className={`inline-flex items-center gap-1.5 rounded-xl px-3.5 py-2 text-xs font-bold transition ${
                    tab === item.id ? 'bg-emerald-700 text-white shadow-xs' : 'text-slate-600 hover:bg-slate-100'
                  }`}
                >
                  <Icon className="h-4 w-4" />
                  {item.label}
                </button>
              );
            })}
          </div>

          <button
            type="button"
            onClick={loadAll}
            className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50"
          >
            <RefreshCw className="h-3.5 w-3.5" /> Actualizar
          </button>
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

        {/* TAB 1: CONSULTAR VIA (MAIN PASSENGER SCREEN) */}
        {tab === 'consult' && (
          <div className="grid gap-5 lg:grid-cols-12">
            {/* Left: Simple Query Form + Active Intention */}
            <div className="space-y-4 lg:col-span-5">
              <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-xs">
                <p className="text-xs font-bold uppercase tracking-wider text-emerald-700">
                  Antes de sair de casa
                </p>
                <h1 className="mt-1 text-lg font-extrabold text-slate-900">
                  Como está a sua via agora?
                </h1>

                <div className="mt-4 space-y-3">
                  <div>
                    <label className="mb-1 flex items-center gap-1.5 text-xs font-semibold text-slate-700">
                      <MapPin className="h-3.5 w-3.5 text-emerald-700" /> De onde vais sair?
                    </label>
                    <select
                      value={originZone}
                      onChange={(e) => setOriginZone(e.target.value)}
                      className="w-full rounded-xl border border-slate-300 bg-white px-3 py-2.5 text-sm font-semibold focus:border-emerald-600 focus:outline-none"
                    >
                      {geo?.zones.map((z) => (
                        <option key={z.id} value={z.name}>
                          {z.name} ({z.municipality})
                        </option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="mb-1 flex items-center gap-1.5 text-xs font-semibold text-slate-700">
                      <Navigation className="h-3.5 w-3.5 text-amber-600" /> Para onde pretendes ir?
                    </label>
                    <select
                      value={destinationZone}
                      onChange={(e) => setDestinationZone(e.target.value)}
                      className="w-full rounded-xl border border-slate-300 bg-white px-3 py-2.5 text-sm font-semibold focus:border-emerald-600 focus:outline-none"
                    >
                      {geo?.zones.map((z) => (
                        <option key={z.id} value={z.name}>
                          {z.name} ({z.municipality})
                        </option>
                      ))}
                    </select>
                  </div>

                  <button
                    type="button"
                    onClick={() => consultCorridor(originZone, destinationZone, true)}
                    className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-emerald-700 py-3 text-sm font-bold text-white transition hover:bg-emerald-800"
                  >
                    <Search className="h-4 w-4" /> Consultar disponibilidade
                  </button>
                </div>

                {/* Quick Presets for testing */}
                <div className="mt-3 flex flex-wrap gap-1.5 text-[11px]">
                  {[
                    ['Gamek', 'Maianga'],
                    ['Rocha Gamek', 'Maianga'],
                    ['Talatona', 'Maianga'],
                    ['Viana', 'Kilamba'],
                  ].map(([o, d]) => (
                    <button
                      key={`${o}-${d}`}
                      type="button"
                      onClick={() => {
                        setOriginZone(o);
                        setDestinationZone(d);
                        consultCorridor(o, d, true);
                      }}
                      className="rounded-lg border border-slate-200 bg-slate-50 px-2.5 py-1 font-semibold text-slate-600 hover:border-emerald-500 hover:text-emerald-800"
                    >
                      {o} → {d}
                    </button>
                  ))}
                </div>
              </div>

              {/* Active Intention Card OR Declare Intention */}
              {myActive ? (
                <div className="space-y-3 rounded-2xl border border-emerald-200 bg-emerald-50/60 p-4">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-extrabold uppercase tracking-wider text-emerald-800">
                      A Sua Intenção Activa
                    </span>
                    <span className="rounded-full bg-white px-2.5 py-0.5 text-[11px] font-bold text-emerald-800 ring-1 ring-emerald-200">
                      {myActive.status === 'CONFIRMED_AT_STOP' ? 'Confirmado na Paragem' : 'Declarado'}
                    </span>
                  </div>
                  <p className="text-sm font-extrabold text-slate-900">
                    {myActive.origin_zone} → {myActive.destination_zone} ({myActive.passenger_count} pessoa(s))
                  </p>
                  <p className="text-[11px] text-slate-600">
                    Actualizado: {formatLuandaTime(myActive.last_confirmed_at)} • Validade até{' '}
                    {formatLuandaTime(myActive.expires_at)}
                  </p>
                  <div className="grid grid-cols-2 gap-2">
                    {myActive.status !== 'CONFIRMED_AT_STOP' && (
                      <button
                        type="button"
                        disabled={busy}
                        onClick={handleConfirmAtStop}
                        className="inline-flex items-center justify-center gap-1.5 rounded-xl bg-emerald-700 py-2.5 text-xs font-bold text-white hover:bg-emerald-800"
                      >
                        <CheckCircle2 className="h-4 w-4" /> Estou na Paragem
                      </button>
                    )}
                    <button
                      type="button"
                      disabled={busy}
                      onClick={handleCancelIntention}
                      className={`inline-flex items-center justify-center gap-1.5 rounded-xl border border-red-200 bg-white py-2.5 text-xs font-bold text-red-700 hover:bg-red-50 ${
                        myActive.status === 'CONFIRMED_AT_STOP' ? 'col-span-2' : ''
                      }`}
                    >
                      <XCircle className="h-4 w-4" /> Cancelar Intenção
                    </button>
                  </div>
                </div>
              ) : (
                <div className="space-y-3 rounded-2xl border border-slate-200 bg-white p-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-xs font-bold text-slate-900">Pretende viajar nesta via?</p>
                      <p className="text-[11px] text-slate-500">
                        Ajude os motoristas a saber onde existe procura real (sem custo).
                      </p>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <Users className="h-3.5 w-3.5 text-slate-400" />
                      <input
                        type="number"
                        min={1}
                        max={10}
                        value={passengerCount}
                        onChange={(e) => setPassengerCount(Math.max(1, Number(e.target.value)))}
                        className="w-14 rounded-lg border border-slate-300 px-2 py-1 text-center text-xs font-bold"
                      />
                    </div>
                  </div>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={handleDeclareIntention}
                    className="w-full rounded-xl bg-slate-900 py-2.5 text-xs font-bold text-white hover:bg-slate-800 disabled:opacity-50"
                  >
                    Declarar Intenção ({originZone} → {destinationZone})
                  </button>
                </div>
              )}
            </div>

            {/* Right: Live Intelligence Card + Alternatives + Mini Map */}
            <div className="space-y-4 lg:col-span-7">
              {corridor && (
                <div className="space-y-4 rounded-2xl border border-slate-200 bg-white p-5 shadow-xs">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div>
                      <h2 className="text-base font-extrabold text-slate-900">{corridor.route_name}</h2>
                      <p className="text-xs text-slate-500">
                        Condição da via: <strong>{ROAD_LABELS[corridor.road_condition] ?? corridor.road_condition}</strong>
                        {corridor.contains_demo_data && (
                          <span className="ml-2 rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-bold text-slate-500">
                            Contém dados de demonstração
                          </span>
                        )}
                      </p>
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      <span className={`rounded-full px-2.5 py-0.5 text-[11px] font-bold ${dMeta.cls}`}>
                        {dMeta.text}
                      </span>
                      <span className={`rounded-full px-2.5 py-0.5 text-[11px] font-bold ${sMeta.cls}`}>
                        {sMeta.text}
                      </span>
                    </div>
                  </div>

                  {!corridor.has_sufficient_data ? (
                    <div className="flex items-start gap-3 rounded-xl border border-slate-200 bg-slate-50 p-4 text-xs text-slate-700">
                      <Info className="mt-0.5 h-5 w-5 shrink-0 text-slate-400" />
                      <div>
                        <p className="font-bold text-slate-900">{corridor.status_message}</p>
                        <p className="mt-1">{corridor.passenger_advisory}</p>
                      </div>
                    </div>
                  ) : (
                    <>
                      {corridor.freshness_status === 'STALE' && (
                        <div className="flex items-center gap-2 rounded-xl border border-amber-200 bg-amber-50 px-3.5 py-2 text-xs font-semibold text-amber-900">
                          <AlertCircle className="h-4 w-4 shrink-0 text-amber-600" />
                          Atenção: os registos desta via encontram-se desactualizados.
                        </div>
                      )}

                      <div className="grid gap-3 sm:grid-cols-3">
                        <div className="rounded-xl bg-slate-50 p-3.5 ring-1 ring-slate-200/70">
                          <p className="text-[11px] font-semibold text-slate-500">Passageiros Interessados</p>
                          <p className="mt-1 text-2xl font-extrabold text-slate-900">
                            {corridor.estimated_demand}
                          </p>
                          <p className="mt-1 text-[11px] text-slate-500">
                            Confirmados: <strong className="text-emerald-700">{corridor.confirmed_demand}</strong> •
                            Declarados: {corridor.declared_demand}
                          </p>
                        </div>

                        <div className="rounded-xl bg-slate-50 p-3.5 ring-1 ring-slate-200/70">
                          <p className="text-[11px] font-semibold text-slate-500">Táxis Disponíveis</p>
                          <p className="mt-1 text-2xl font-extrabold text-emerald-700">
                            {corridor.total_supply}
                          </p>
                          <p className="mt-1 text-[11px] text-slate-500">
                            Observados: <strong>{corridor.observed_supply}</strong> • Declarados:{' '}
                            {corridor.declared_supply}
                          </p>
                        </div>

                        <div className="rounded-xl bg-slate-50 p-3.5 ring-1 ring-slate-200/70">
                          <p className="text-[11px] font-semibold text-slate-500">Espera & Tendência</p>
                          <p className="mt-1 text-2xl font-extrabold text-slate-900">
                            {corridor.estimated_wait_min ? `~${corridor.estimated_wait_min} min` : '—'}
                          </p>
                          <p className="mt-1 inline-flex items-center gap-1 text-[11px] font-semibold text-slate-600">
                            {corridor.trend === 'A_SUBIR' ? (
                              <TrendingUp className="h-3.5 w-3.5 text-red-600" />
                            ) : (
                              <TrendingDown className="h-3.5 w-3.5 text-emerald-600" />
                            )}
                            Tendência: {corridor.trend}
                          </p>
                        </div>
                      </div>

                      <div className="rounded-xl border border-slate-200 bg-slate-50/70 p-3.5 text-xs text-slate-700">
                        <p className="font-semibold text-slate-900">{corridor.passenger_advisory}</p>
                        <p className="mt-1 text-[11px] text-slate-500">{corridor.ratio_disclaimer}</p>
                      </div>

                      {/* Data Quality & Freshness Footer */}
                      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-slate-100 pt-3 text-[11px] text-slate-500">
                        <span className="inline-flex items-center gap-1">
                          <Clock className="h-3.5 w-3.5" />
                          Última actualização: <strong>{formatLuandaTime(corridor.last_updated_at)}</strong> (
                          {corridor.freshness_status === 'RECENT' ? 'Recente' : 'Desactualizado'})
                        </span>
                        <span className="inline-flex items-center gap-1">
                          <ShieldCheck className="h-3.5 w-3.5 text-emerald-700" />
                          Confiança: <strong>{corridor.confidence_level}</strong> • Fontes:{' '}
                          {corridor.sources.join(', ')}
                        </span>
                      </div>
                    </>
                  )}

                  {/* Nearby Alternative Stops Comparison */}
                  {corridor.alternatives && corridor.alternatives.length > 0 && (
                    <div className="border-t border-slate-100 pt-3">
                      <p className="mb-2 flex items-center gap-1.5 text-xs font-bold text-slate-800">
                        <Compass className="h-4 w-4 text-emerald-700" />
                        Paragens e Vias Alternativas Próximas para {corridor.destination_zone}
                      </p>
                      <div className="grid gap-2 sm:grid-cols-2">
                        {corridor.alternatives.map((alt) => (
                          <button
                            key={alt.route_name}
                            type="button"
                            onClick={() => {
                              setOriginZone(alt.origin_zone);
                              consultCorridor(alt.origin_zone, alt.destination_zone, true);
                            }}
                            className="rounded-xl border border-slate-200 bg-slate-50 p-3 text-left text-xs transition hover:border-emerald-600"
                          >
                            <div className="flex items-center justify-between">
                              <strong className="text-slate-900">{alt.origin_zone}</strong>
                              <span className="text-[10px] font-semibold text-slate-500">
                                {alt.distance_from_origin_km} km
                              </span>
                            </div>
                            <p className="mt-1 text-[11px] text-slate-600">
                              {alt.has_sufficient_data
                                ? `${alt.estimated_demand} pass. • ${alt.total_supply} táxis • ${alt.balance_label}`
                                : 'Informação insuficiente'}
                            </p>
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}

              <LuandaMap heightClass="h-64" markers={mapMarkers} routeLine={routeLine} demandCircles={demandCircles} />
            </div>
          </div>
        )}

        {/* TAB 2: FULL MAP WITH FILTERS */}
        {tab === 'map' && (
          <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-2 rounded-2xl border border-slate-200 bg-white p-3.5 text-xs">
              <select
                value={mapFilterZone}
                onChange={(e) => setMapFilterZone(e.target.value)}
                className="rounded-xl border border-slate-300 bg-white px-3 py-2 font-semibold"
              >
                <option value="">Todas as Zonas</option>
                {geo?.zones.map((z) => (
                  <option key={z.id} value={z.name}>{z.name}</option>
                ))}
              </select>
              <select
                value={mapFilterDemand}
                onChange={(e) => setMapFilterDemand(e.target.value)}
                className="rounded-xl border border-slate-300 bg-white px-3 py-2 font-semibold"
              >
                <option value="">Todos os Níveis de Procura</option>
                <option value="PROCURA_ELEVADA">Procura Elevada</option>
                <option value="PROCURA_MODERADA">Procura Moderada</option>
                <option value="PROCURA_BAIXA">Procura Baixa</option>
              </select>
              <span className="ml-auto text-[11px] text-slate-500">
                Privacidade: apenas dados agregados por paragem são apresentados.
              </span>
            </div>

            <LuandaMap heightClass="h-[420px]" zoom={12} markers={mapMarkers} demandCircles={demandCircles} />

            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {allRoutes.map((r) => (
                <div key={r.route_name} className="rounded-2xl border border-slate-200 bg-white p-4 text-xs">
                  <div className="flex items-center justify-between gap-2">
                    <strong className="text-slate-900">{r.route_name}</strong>
                    <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${(DEMAND_LABELS[r.demand_level] ?? DEMAND_LABELS.INSUFFICIENT_DATA).cls}`}>
                      {(DEMAND_LABELS[r.demand_level] ?? DEMAND_LABELS.INSUFFICIENT_DATA).text}
                    </span>
                  </div>
                  <p className="mt-1.5 text-slate-600">
                    {r.has_sufficient_data
                      ? `Procura: ${r.estimated_demand} (${r.confirmed_demand} conf.) • Oferta: ${r.total_supply} táxis`
                      : r.status_message}
                  </p>
                  <p className="mt-1 text-[11px] text-slate-400">
                    {r.last_updated_at ? `Actualizado: ${formatLuandaTime(r.last_updated_at)}` : 'Sem actualização recente'}
                  </p>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* TAB 3: HISTORY */}
        {tab === 'history' && (
          <div className="grid gap-5 lg:grid-cols-2">
            <div className="rounded-2xl border border-slate-200 bg-white p-5">
              <h2 className="mb-3 text-sm font-bold text-slate-900">Histórico das Minhas Intenções</h2>
              {myHistory.length === 0 ? (
                <p className="text-xs text-slate-500">Ainda não declarou intenções de viagem.</p>
              ) : (
                <div className="divide-y divide-slate-100">
                  {myHistory.map((it) => (
                    <div key={it.id} className="flex items-center justify-between py-2.5 text-xs">
                      <div>
                        <p className="font-bold text-slate-900">
                          {it.origin_zone} → {it.destination_zone} ({it.passenger_count} pass.)
                        </p>
                        <p className="text-[11px] text-slate-500">{formatLuandaTime(it.created_at)}</p>
                      </div>
                      <span className="rounded-full bg-slate-100 px-2.5 py-0.5 text-[10px] font-bold text-slate-700">
                        {it.status}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="rounded-2xl border border-slate-200 bg-white p-5">
              <h2 className="mb-3 text-sm font-bold text-slate-900">Consultas Recentes Nesta Sessão</h2>
              {consultHistory.length === 0 ? (
                <p className="text-xs text-slate-500">As vias consultadas aparecem aqui para acesso rápido.</p>
              ) : (
                <div className="divide-y divide-slate-100">
                  {consultHistory.map((c, idx) => (
                    <div key={idx} className="flex items-center justify-between py-2 text-xs">
                      <span className="font-semibold text-slate-800">
                        {c.origin} → {c.dest}
                      </span>
                      <span className="text-slate-400">{c.time}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {/* TAB 4: PROFILE */}
        {tab === 'profile' && (
          <div className="rounded-2xl border border-slate-200 bg-white p-6 text-xs">
            <h2 className="text-base font-bold text-slate-900">Perfil do Passageiro</h2>
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              <div className="rounded-xl bg-slate-50 p-3">
                <p className="text-slate-500">Nome</p>
                <p className="mt-0.5 text-sm font-bold text-slate-900">{user?.full_name}</p>
              </div>
              <div className="rounded-xl bg-slate-50 p-3">
                <p className="text-slate-500">Contacto</p>
                <p className="mt-0.5 text-sm font-bold text-slate-900">
                  {user?.email} • {user?.phone}
                </p>
              </div>
            </div>
            <p className="mt-4 text-slate-500">
              Privacidade: a DalaLink nunca partilha a sua localização exacta com outros utilizadores — todas
              as contagens nas paragens são apresentadas de forma agregada.
            </p>
          </div>
        )}
      </main>
    </div>
  );
};
