import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  BarChart3,
  Clock,
  Compass,
  Map as MapIcon,
  Radio,
  RefreshCw,
  Route as RouteIcon,
  ShieldAlert,
  TrendingUp,
  User as UserIcon,
} from 'lucide-react';
import { DemandCircleItem, LuandaMap, MapMarkerItem } from '../../components/LuandaMap';
import { TopBar } from '../../components/TopBar';
import { useAuth } from '../../contexts/AuthContext';
import { apiRequest, formatLuandaTime } from '../../services/api';
import { DriverInfoOverviewDTO, GeographyDTO } from '../../types';

export const DriverApp: React.FC = () => {
  const { user, lastEvent } = useAuth();
  const [tab, setTab] = useState<'panel' | 'map' | 'routes' | 'availability' | 'profile'>('panel');
  const [geo, setGeo] = useState<GeographyDTO | null>(null);
  const [overview, setOverview] = useState<DriverInfoOverviewDTO | null>(null);

  const [originZone, setOriginZone] = useState('Golf 2');
  const [destinationZone, setDestinationZone] = useState('Maianga');
  const [availabilityStatus, setAvailabilityStatus] = useState<'AVAILABLE' | 'AT_STOP' | 'EN_ROUTE' | 'UNAVAILABLE'>('AVAILABLE');
  const [seats, setSeats] = useState(4);
  const [busy, setBusy] = useState(false);
  const [banner, setBanner] = useState<{ type: 'ok' | 'err'; text: string } | null>(null);

  const loadAll = useCallback(async () => {
    try {
      const [geoRes, ovRes] = await Promise.all([
        apiRequest<GeographyDTO>('/info/geography'),
        apiRequest<DriverInfoOverviewDTO>('/info/driver/overview'),
      ]);
      setGeo(geoRes);
      setOverview(ovRes);
      if (ovRes.my_report) {
        setOriginZone(ovRes.my_report.origin_zone);
        setDestinationZone(ovRes.my_report.destination_zone);
        setAvailabilityStatus(ovRes.my_report.availability_status);
        setSeats(ovRes.my_report.estimated_seats);
      }
    } catch {
      // ignore transient error
    }
  }, []);

  useEffect(() => {
    loadAll();
    const timer = window.setInterval(loadAll, 12000);
    return () => window.clearInterval(timer);
  }, [loadAll]);

  useEffect(() => {
    if (lastEvent) loadAll();
  }, [lastEvent, loadAll]);

  const handleReportAvailability = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    setBusy(true);
    setBanner(null);
    try {
      await apiRequest('/info/driver/availability', {
        method: 'POST',
        body: JSON.stringify({
          origin_zone: originZone,
          destination_zone: destinationZone,
          availability_status: availabilityStatus,
          estimated_seats: seats,
        }),
      });
      setBanner({
        type: 'ok',
        text:
          availabilityStatus === 'UNAVAILABLE'
            ? 'Estado actualizado para Indisponível.'
            : `Disponibilidade registada para ${originZone} → ${destinationZone} (${availabilityStatus}).`,
      });
      await loadAll();
    } catch (err) {
      setBanner({ type: 'err', text: err instanceof Error ? err.message : 'Erro ao actualizar estado.' });
    } finally {
      setBusy(false);
    }
  };

  const demandCircles: DemandCircleItem[] = useMemo(() => {
    if (!overview) return [];
    const seen = new Set<string>();
    const out: DemandCircleItem[] = [];
    overview.routes.forEach((r) => {
      if (!r.origin_lat || !r.origin_lng || seen.has(r.origin_zone)) return;
      seen.add(r.origin_zone);
      out.push({
        zone: r.origin_zone,
        lat: r.origin_lat,
        lng: r.origin_lng,
        level:
          r.demand_level === 'PROCURA_ELEVADA'
            ? 'ELEVADA'
            : r.demand_level === 'PROCURA_MODERADA'
              ? 'MODERADA'
              : 'BAIXA',
        activeRequests: r.estimated_demand,
        availableVehicles: r.total_supply,
      });
    });
    return out;
  }, [overview]);

  const mapMarkers: MapMarkerItem[] = useMemo(() => {
    return (geo?.stops ?? []).map((s) => ({
      id: `drv-stop-${s.id}`,
      lat: s.latitude,
      lng: s.longitude,
      label: s.zone_name,
      sublabel: s.name,
      kind: s.zone_name === originZone ? 'vehicle_available' : 'stop',
    }));
  }, [geo, originZone]);

  const maxHour = useMemo(() => {
    if (!overview) return 1;
    return Math.max(1, ...overview.peak_hours.map((h) => h.passengers));
  }, [overview]);

  return (
    <div className="min-h-screen bg-slate-950 pb-20 text-slate-100">
      <TopBar dark />

      <main className="mx-auto max-w-6xl space-y-5 px-4 py-5">
        {/* Mandatory Road Safety Banner */}
        <div className="flex items-start gap-3 rounded-2xl border border-amber-500/35 bg-amber-500/10 p-3.5 text-xs text-amber-200">
          <ShieldAlert className="mt-0.5 h-5 w-5 shrink-0 text-amber-400" />
          <div>
            <strong className="text-amber-100">Segurança Rodoviária:</strong>{' '}
            {overview?.safety_notice ??
              'Consulte esta informação apenas com o veículo imobilizado. Os indicadores são estimativas baseadas nos últimos registos.'}
          </div>
        </div>

        {/* Navigation Strip */}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap gap-1.5 rounded-2xl border border-slate-800 bg-slate-900 p-1.5">
            {[
              { id: 'panel', label: 'Painel', icon: TrendingUp },
              { id: 'map', label: 'Mapa de Procura', icon: MapIcon },
              { id: 'routes', label: 'Vias', icon: RouteIcon },
              { id: 'availability', label: 'Disponibilidade', icon: Radio },
              { id: 'profile', label: 'Perfil', icon: UserIcon },
            ].map((item) => {
              const Icon = item.icon;
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => setTab(item.id as typeof tab)}
                  className={`inline-flex items-center gap-1.5 rounded-xl px-3.5 py-2 text-xs font-bold transition ${
                    tab === item.id ? 'bg-emerald-600 text-white' : 'text-slate-300 hover:bg-slate-800'
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
            className="inline-flex items-center gap-1.5 rounded-xl border border-slate-700 bg-slate-900 px-3 py-2 text-xs font-bold text-slate-200 hover:bg-slate-800"
          >
            <RefreshCw className="h-3.5 w-3.5" /> Actualizar
          </button>
        </div>

        {banner && (
          <div
            className={`flex items-center justify-between rounded-xl border px-4 py-3 text-xs font-semibold ${
              banner.type === 'ok'
                ? 'border-emerald-500/40 bg-emerald-500/15 text-emerald-200'
                : 'border-red-500/40 bg-red-500/15 text-red-200'
            }`}
          >
            <span>{banner.text}</span>
            <button type="button" onClick={() => setBanner(null)}>✕</button>
          </div>
        )}

        {/* TAB 1: DRIVER INTELLIGENCE PANEL */}
        {tab === 'panel' && overview && (
          <div className="grid gap-5 lg:grid-cols-12">
            <div className="space-y-4 lg:col-span-7">
              <div className="rounded-2xl border border-slate-800 bg-slate-900 p-5">
                <div className="mb-3 flex items-center justify-between">
                  <div>
                    <p className="text-xs font-bold uppercase tracking-wider text-emerald-400">
                      Onde existe procura em Luanda?
                    </p>
                    <h1 className="text-base font-extrabold text-white">
                      Vias Ordenadas por Procura Estimada
                    </h1>
                  </div>
                  <span className="text-[11px] text-slate-400">
                    {formatLuandaTime(overview.server_time_luanda)}
                  </span>
                </div>

                <div className="space-y-2.5">
                  {overview.routes.map((r) => (
                    <div
                      key={r.route_name}
                      className="rounded-xl border border-slate-800 bg-slate-950 p-3.5 text-xs"
                    >
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <span className="text-sm font-extrabold text-white">{r.route_name}</span>
                        <span
                          className={`rounded-full px-2.5 py-0.5 text-[10px] font-extrabold ${
                            r.demand_level === 'PROCURA_ELEVADA'
                              ? 'bg-red-500/20 text-red-300'
                              : r.demand_level === 'PROCURA_MODERADA'
                                ? 'bg-amber-500/20 text-amber-300'
                                : r.demand_level === 'PROCURA_BAIXA'
                                  ? 'bg-emerald-500/20 text-emerald-300'
                                  : 'bg-slate-800 text-slate-400'
                          }`}
                        >
                          {r.demand_level.replace('_', ' ')}
                        </span>
                      </div>

                      {r.has_sufficient_data ? (
                        <>
                          <p className="mt-1.5 text-slate-300">{r.driver_advisory}</p>
                          <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-[11px] text-slate-400">
                            <span>
                              Passageiros est.: <strong className="text-white">{r.estimated_demand}</strong> (
                              {r.confirmed_demand} conf.) • Táxis: <strong className="text-emerald-400">{r.total_supply}</strong>
                              {r.demand_supply_ratio !== null && r.demand_supply_ratio !== undefined
                                ? ` • Rácio ~${r.demand_supply_ratio}:1`
                                : ''}
                            </span>
                            <span className="inline-flex items-center gap-1">
                              <Clock className="h-3 w-3" />
                              {formatLuandaTime(r.last_updated_at)}
                              {r.freshness_status === 'STALE' && (
                                <strong className="text-amber-400"> (Desactualizado)</strong>
                              )}
                            </span>
                          </div>
                        </>
                      ) : (
                        <p className="mt-1.5 text-slate-400">{r.status_message}</p>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <div className="space-y-4 lg:col-span-5">
              {/* Current Availability Quick Card */}
              <div className="rounded-2xl border border-slate-800 bg-slate-900 p-5">
                <div className="mb-2 flex items-center justify-between">
                  <span className="text-xs font-bold uppercase tracking-wider text-slate-400">
                    A Minha Disponibilidade Declarada
                  </span>
                  <button
                    type="button"
                    onClick={() => setTab('availability')}
                    className="text-xs font-bold text-emerald-400 hover:underline"
                  >
                    Alterar
                  </button>
                </div>
                {overview.my_report ? (
                  <div className="rounded-xl bg-slate-950 p-3.5 text-xs">
                    <p className="text-sm font-extrabold text-white">
                      {overview.my_report.origin_zone} → {overview.my_report.destination_zone}
                    </p>
                    <p className="mt-1 text-emerald-400">
                      Estado: <strong>{overview.my_report.availability_status}</strong> •{' '}
                      {overview.my_report.estimated_seats} lugares
                    </p>
                    <p className="mt-1 text-[11px] text-slate-400">
                      Válido até {formatLuandaTime(overview.my_report.expires_at)} ({overview.my_report.freshness_status})
                    </p>
                  </div>
                ) : (
                  <p className="text-xs text-slate-400">
                    Ainda não declarou a sua via actual. Indique a sua disponibilidade para ajudar passageiros.
                  </p>
                )}
              </div>

              {/* Top Destinations */}
              <div className="rounded-2xl border border-slate-800 bg-slate-900 p-5">
                <div className="mb-3 flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-slate-400">
                  <Compass className="h-4 w-4 text-amber-400" /> Destinos Mais Procurados
                </div>
                <div className="space-y-2">
                  {overview.top_destinations.map((d) => (
                    <div
                      key={d.destination}
                      className="flex items-center justify-between rounded-xl bg-slate-950 px-3.5 py-2.5 text-xs"
                    >
                      <span className="font-bold text-white">{d.destination}</span>
                      <span className="text-slate-300">
                        <strong className="text-amber-300">{d.estimated_demand}</strong> pass. est. •{' '}
                        <strong className="text-emerald-400">{d.total_supply}</strong> táxis
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Peak Hours Mini Chart */}
              <div className="rounded-2xl border border-slate-800 bg-slate-900 p-5">
                <div className="mb-3 flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-slate-400">
                  <BarChart3 className="h-4 w-4 text-emerald-400" /> Horários de Maior Procura (Luanda)
                </div>
                <div className="flex h-28 items-end gap-1">
                  {overview.peak_hours.map((h) => {
                    const pct = Math.max(8, Math.round((h.passengers / maxHour) * 100));
                    return (
                      <div key={h.hour} className="flex flex-1 flex-col items-center gap-1">
                        <div
                          className={`w-full rounded-t ${h.passengers > 0 ? 'bg-emerald-500' : 'bg-slate-800'}`}
                          style={{ height: `${h.passengers > 0 ? pct : 8}%` }}
                          title={`${h.hour}: ${h.passengers} pass.`}
                        />
                        <span className="text-[8px] text-slate-500">{h.hour.replace('h', '')}</span>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* TAB 2: DEMAND HEATMAP */}
        {tab === 'map' && (
          <div className="space-y-3 rounded-2xl border border-slate-800 bg-slate-900 p-4">
            <h2 className="text-sm font-bold text-white">
              Mapa de Calor de Procura em Luanda (Dados Agregados)
            </h2>
            <LuandaMap heightClass="h-[440px]" zoom={12} markers={mapMarkers} demandCircles={demandCircles} />
          </div>
        )}

        {/* TAB 3: ROUTES LIST */}
        {tab === 'routes' && overview && (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {overview.routes.map((r) => (
              <div key={r.route_name} className="rounded-2xl border border-slate-800 bg-slate-900 p-4 text-xs">
                <p className="text-sm font-extrabold text-white">{r.route_name}</p>
                <p className="mt-1 text-slate-400">{r.corridor_description}</p>
                <p className="mt-2 font-semibold text-emerald-400">
                  {r.has_sufficient_data
                    ? `${r.estimated_demand} pass. est. • ${r.total_supply} táxis • ${r.balance_label}`
                    : r.status_message}
                </p>
              </div>
            ))}
          </div>
        )}

        {/* TAB 4: DECLARE AVAILABILITY */}
        {tab === 'availability' && (
          <form
            onSubmit={handleReportAvailability}
            className="mx-auto max-w-xl space-y-4 rounded-2xl border border-slate-800 bg-slate-900 p-6"
          >
            <h2 className="text-base font-extrabold text-white">
              Indicar Disponibilidade e Via de Operação
            </h2>
            <p className="text-xs text-slate-400">
              A sua declaração expira automaticamente após o tempo configurado para manter a informação
              sempre actualizada.
            </p>

            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <label className="mb-1 block text-xs font-semibold text-slate-300">Zona / Paragem Actual</label>
                <select
                  value={originZone}
                  onChange={(e) => setOriginZone(e.target.value)}
                  className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2.5 text-sm text-white"
                >
                  {geo?.zones.map((z) => (
                    <option key={z.id} value={z.name}>{z.name}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="mb-1 block text-xs font-semibold text-slate-300">Via / Destino Pretendido</label>
                <select
                  value={destinationZone}
                  onChange={(e) => setDestinationZone(e.target.value)}
                  className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2.5 text-sm text-white"
                >
                  {geo?.zones.map((z) => (
                    <option key={z.id} value={z.name}>{z.name}</option>
                  ))}
                </select>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              {([
                ['AVAILABLE', 'Disponível'],
                ['AT_STOP', 'Na Paragem'],
                ['EN_ROUTE', 'Em Trânsito'],
                ['UNAVAILABLE', 'Indisponível'],
              ] as const).map(([st, lbl]) => (
                <button
                  key={st}
                  type="button"
                  onClick={() => setAvailabilityStatus(st)}
                  className={`rounded-xl py-2.5 text-xs font-extrabold transition ${
                    availabilityStatus === st
                      ? st === 'UNAVAILABLE'
                        ? 'bg-red-600 text-white'
                        : 'bg-emerald-600 text-white'
                      : 'bg-slate-950 text-slate-400 hover:text-white'
                  }`}
                >
                  {lbl}
                </button>
              ))}
            </div>

            <div>
              <label className="mb-1 block text-xs font-semibold text-slate-300">Lugares estimados</label>
              <input
                type="number"
                min={1}
                max={30}
                value={seats}
                onChange={(e) => setSeats(Number(e.target.value))}
                className="w-28 rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
              />
            </div>

            <button
              type="submit"
              disabled={busy}
              className="w-full rounded-xl bg-emerald-600 py-3.5 text-sm font-extrabold text-white transition hover:bg-emerald-500 disabled:opacity-50"
            >
              {busy ? 'A actualizar...' : 'Guardar Disponibilidade'}
            </button>
          </form>
        )}

        {/* TAB 5: PROFILE */}
        {tab === 'profile' && (
          <div className="rounded-2xl border border-slate-800 bg-slate-900 p-6 text-xs">
            <h2 className="text-base font-bold text-white">Perfil do Motorista</h2>
            <p className="mt-2 text-slate-300">
              <strong>{user?.full_name}</strong> • {user?.email} • {user?.phone}
            </p>
            <div className="mt-3 flex items-center gap-2 rounded-xl bg-slate-950 p-3 text-slate-400">
              <AlertTriangle className="h-4 w-4 text-amber-400" />
              A DalaLink actua exclusivamente como plataforma de inteligência de procura e oferta nesta fase,
              sem cobranças nem comissões sobre viagens.
            </div>
          </div>
        )}
      </main>
    </div>
  );
};
