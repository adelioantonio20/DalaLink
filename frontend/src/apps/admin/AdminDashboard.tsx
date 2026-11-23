import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Activity,
  BarChart3,
  CheckCircle2,
  ClipboardCheck,
  Clock,
  Map as MapIcon,
  MapPin,
  Plus,
  RefreshCw,
  Settings,
  ShieldCheck,
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
  HistoricalAnalyticsDTO,
  IntentionDTO,
} from '../../types';

interface AdminInfoDashboardDTO {
  kpis: {
    active_passengers: number;
    active_drivers: number;
    active_intentions_count: number;
    declared_waiting_passengers: number;
    confirmed_passengers: number;
    available_drivers: number;
    validated_data_pct: number;
    stale_or_expired_pct: number;
    pending_validations: number;
    suspicious_records: number;
  };
  routes: CorridorStatusDTO[];
  analytics: HistoricalAnalyticsDTO;
  demand_observations: {
    id: number;
    origin_zone: string;
    destination_zone: string;
    observed_passengers_count: number;
    estimated_wait_min?: number;
    validation_status: string;
    freshness_status: string;
    notes?: string;
    is_demo_data: boolean;
    observed_at?: string;
  }[];
  supply_observations: {
    id: number;
    origin_zone: string;
    destination_zone: string;
    observed_taxis_count: number;
    road_condition: string;
    validation_status: string;
    freshness_status: string;
    notes?: string;
    is_demo_data: boolean;
    observed_at?: string;
  }[];
  active_intentions: IntentionDTO[];
  configs: { key: string; value: string; description: string }[];
  users: { id: number; full_name: string; email: string; phone: string; role: string; is_active: boolean }[];
  audit_logs: { id: number; action: string; entity_type: string; entity_id?: string; details_json: string; created_at?: string }[];
}

export const AdminDashboard: React.FC = () => {
  const { user, lastEvent } = useAuth();
  const isFieldOnly = user?.role === 'FIELD_COLLECTOR';

  const [tab, setTab] = useState<'dashboard' | 'map' | 'geo' | 'field' | 'quality' | 'reports' | 'config'>(
    isFieldOnly ? 'field' : 'dashboard'
  );
  const [geo, setGeo] = useState<GeographyDTO | null>(null);
  const [data, setData] = useState<AdminInfoDashboardDTO | null>(null);
  const [busy, setBusy] = useState(false);
  const [banner, setBanner] = useState<{ type: 'ok' | 'err'; text: string } | null>(null);

  // Field observation form
  const [obsForm, setObsForm] = useState({
    origin_zone: 'Gamek',
    destination_zone: 'Maianga',
    observed_taxis_count: 15,
    observed_passengers_count: 32,
    estimated_wait_min: 12,
    road_condition: 'MODERATE_TRAFFIC',
    notes: 'Observação presencial na paragem principal',
  });

  // Stop & Route creation forms
  const [stopForm, setStopForm] = useState({
    zone_id: 1,
    name: '',
    landmark: '',
    latitude: -8.86,
    longitude: 13.22,
  });

  const [configDraft, setConfigDraft] = useState<Record<string, string>>({});

  const loadAll = useCallback(async () => {
    try {
      const [geoRes, dashRes] = await Promise.all([
        apiRequest<GeographyDTO>('/info/geography'),
        apiRequest<AdminInfoDashboardDTO>('/info/admin/dashboard'),
      ]);
      setGeo(geoRes);
      setData(dashRes);
      if (geoRes.zones.length > 0 && !geoRes.zones.some((z) => z.id === stopForm.zone_id)) {
        setStopForm((p) => ({ ...p, zone_id: geoRes.zones[0].id }));
      }
      setConfigDraft((prev) => {
        if (Object.keys(prev).length > 0) return prev;
        const map: Record<string, string> = {};
        dashRes.configs.forEach((c) => {
          map[c.key] = c.value;
        });
        return map;
      });
    } catch {
      // ignore transient error
    }
  }, [stopForm.zone_id]);

  useEffect(() => {
    loadAll();
    const timer = window.setInterval(loadAll, 12000);
    return () => window.clearInterval(timer);
  }, [loadAll]);

  useEffect(() => {
    if (lastEvent) loadAll();
  }, [lastEvent, loadAll]);

  const handleRecordObservation = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setBanner(null);
    try {
      const res = await apiRequest<{ validation_status: string }>('/info/observations/field', {
        method: 'POST',
        body: JSON.stringify({ ...obsForm, auto_validate: user?.role === 'ADMIN' }),
      });
      setBanner({
        type: 'ok',
        text: `Observação presencial registada (${obsForm.origin_zone} → ${obsForm.destination_zone}: ${obsForm.observed_taxis_count} táxis, ${obsForm.observed_passengers_count} pass.) • Estado: ${res.validation_status}.`,
      });
      await loadAll();
    } catch (err) {
      setBanner({ type: 'err', text: err instanceof Error ? err.message : 'Erro ao registar observação.' });
    } finally {
      setBusy(false);
    }
  };

  const handleValidationDecision = async (targetType: string, targetId: number, decision: string) => {
    setBusy(true);
    setBanner(null);
    try {
      await apiRequest(`/info/admin/validations/${targetType}/${targetId}`, {
        method: 'POST',
        body: JSON.stringify({ decision, reason: `Decisão administrativa: ${decision}` }),
      });
      setBanner({ type: 'ok', text: `Registo ${targetType} #${targetId} marcado como ${decision}.` });
      await loadAll();
    } catch (err) {
      setBanner({ type: 'err', text: err instanceof Error ? err.message : 'Erro na validação.' });
    } finally {
      setBusy(false);
    }
  };

  const handleCreateStop = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setBanner(null);
    try {
      await apiRequest('/info/admin/stops', {
        method: 'POST',
        body: JSON.stringify(stopForm),
      });
      setStopForm({ ...stopForm, name: '', landmark: '' });
      setBanner({ type: 'ok', text: 'Nova paragem validada e adicionada ao mapa de Luanda.' });
      await loadAll();
    } catch (err) {
      setBanner({ type: 'err', text: err instanceof Error ? err.message : 'Erro ao criar paragem.' });
    } finally {
      setBusy(false);
    }
  };

  const handleSaveConfig = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setBanner(null);
    try {
      await apiRequest('/info/admin/config', {
        method: 'PUT',
        body: JSON.stringify({ updates: configDraft }),
      });
      setBanner({ type: 'ok', text: 'Limites de procura/oferta e janelas de expiração actualizados.' });
      await loadAll();
    } catch (err) {
      setBanner({ type: 'err', text: err instanceof Error ? err.message : 'Erro ao guardar configurações.' });
    } finally {
      setBusy(false);
    }
  };

  const mapMarkers: MapMarkerItem[] = useMemo(() => {
    return (geo?.stops ?? []).map((s) => ({
      id: `adm-stop-${s.id}`,
      lat: s.latitude,
      lng: s.longitude,
      label: s.name,
      sublabel: `${s.zone_name} • ${s.is_validated ? 'Paragem Validada' : 'Pendente'}`,
      kind: 'stop',
    }));
  }, [geo]);

  const demandCircles: DemandCircleItem[] = useMemo(() => {
    if (!data) return [];
    const seen = new Set<string>();
    const out: DemandCircleItem[] = [];
    data.routes.forEach((r) => {
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
  }, [data]);

  const k = data?.kpis;
  const maxHour = useMemo(() => {
    if (!data) return 1;
    return Math.max(1, ...data.analytics.demand_by_hour.map((h) => h.passengers));
  }, [data]);

  return (
    <div className="min-h-screen bg-slate-50 pb-16">
      <TopBar />

      <main className="mx-auto max-w-7xl space-y-5 px-4 py-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap gap-1.5 rounded-2xl bg-white p-1.5 shadow-xs ring-1 ring-slate-200">
            {[
              { id: 'dashboard', label: 'Dashboard', icon: Activity },
              { id: 'map', label: 'Mapa Operacional', icon: MapIcon },
              { id: 'field', label: 'Recolha de Campo', icon: ClipboardCheck },
              { id: 'quality', label: 'Qualidade dos Dados', icon: ShieldCheck },
              { id: 'geo', label: 'Paragens & Vias', icon: MapPin },
              { id: 'reports', label: 'Relatórios Históricos', icon: BarChart3 },
              { id: 'config', label: 'Configurações', icon: Settings },
            ].map((item) => {
              const Icon = item.icon;
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => setTab(item.id as typeof tab)}
                  className={`inline-flex items-center gap-1.5 rounded-xl px-3 py-2 text-xs font-bold transition ${
                    tab === item.id ? 'bg-slate-900 text-white' : 'text-slate-600 hover:bg-slate-100'
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
            className="inline-flex items-center gap-1.5 rounded-xl bg-emerald-700 px-3.5 py-2 text-xs font-bold text-white hover:bg-emerald-800"
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

        {/* Section 8 KPIs */}
        {k && (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <div className="rounded-2xl border border-slate-200 bg-white p-4">
              <div className="flex items-center justify-between text-xs font-semibold text-slate-500">
                <span>Utilizadores Activos</span>
                <Users className="h-4 w-4 text-emerald-700" />
              </div>
              <p className="mt-1.5 text-2xl font-extrabold text-slate-900">
                {k.active_passengers} pass. • {k.active_drivers} mot.
              </p>
              <p className="mt-1 text-xs text-slate-500">
                Motoristas disponíveis agora: <strong>{k.available_drivers}</strong>
              </p>
            </div>

            <div className="rounded-2xl border border-slate-200 bg-white p-4">
              <div className="flex items-center justify-between text-xs font-semibold text-slate-500">
                <span>Procura em Curso</span>
                <Activity className="h-4 w-4 text-amber-600" />
              </div>
              <p className="mt-1.5 text-2xl font-extrabold text-slate-900">
                {k.active_intentions_count} intenções ({k.declared_waiting_passengers} p.)
              </p>
              <p className="mt-1 text-xs text-emerald-700">
                Confirmados na paragem: <strong>{k.confirmed_passengers}</strong>
              </p>
            </div>

            <div className="rounded-2xl border border-slate-200 bg-white p-4">
              <div className="flex items-center justify-between text-xs font-semibold text-slate-500">
                <span>Qualidade & Validação</span>
                <ShieldCheck className="h-4 w-4 text-emerald-700" />
              </div>
              <p className="mt-1.5 text-2xl font-extrabold text-emerald-700">{k.validated_data_pct}% validados</p>
              <p className="mt-1 text-xs text-slate-500">
                Pendentes de validação: <strong>{k.pending_validations}</strong>
              </p>
            </div>

            <div className="rounded-2xl border border-slate-200 bg-white p-4">
              <div className="flex items-center justify-between text-xs font-semibold text-slate-500">
                <span>Actualidade dos Dados</span>
                <Clock className="h-4 w-4 text-amber-600" />
              </div>
              <p className="mt-1.5 text-2xl font-extrabold text-amber-700">
                {k.stale_or_expired_pct}% desact./exp.
              </p>
              <p className="mt-1 text-xs text-slate-500">Registos suspeitos: {k.suspicious_records}</p>
            </div>
          </div>
        )}

        {/* TAB 1: DASHBOARD */}
        {tab === 'dashboard' && data && (
          <div className="grid gap-5 lg:grid-cols-12">
            <div className="rounded-2xl border border-slate-200 bg-white p-5 lg:col-span-7">
              <h2 className="mb-3 text-sm font-bold text-slate-900">
                Estado em Tempo Real das Vias de Luanda
              </h2>
              <div className="divide-y divide-slate-100">
                {data.routes.map((r) => (
                  <div key={r.route_name} className="flex flex-wrap items-center justify-between gap-2 py-2.5 text-xs">
                    <div>
                      <p className="font-bold text-slate-900">{r.route_name}</p>
                      <p className="text-[11px] text-slate-500">
                        {r.has_sufficient_data
                          ? `Procura: ${r.estimated_demand} (${r.confirmed_demand} conf.) • Oferta: ${r.total_supply} (${r.observed_supply} obs.)`
                          : r.status_message}
                      </p>
                    </div>
                    <div className="text-right">
                      <span className="rounded-full bg-slate-100 px-2.5 py-0.5 text-[10px] font-bold text-slate-700">
                        {r.demand_level} • {r.freshness_status}
                      </span>
                      <p className="mt-0.5 text-[10px] text-slate-400">
                        {formatLuandaTime(r.last_updated_at)}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="rounded-2xl border border-slate-200 bg-white p-5 lg:col-span-5">
              <h2 className="mb-3 text-sm font-bold text-slate-900">Registo de Auditoria</h2>
              <div className="max-h-96 divide-y divide-slate-100 overflow-y-auto pr-1">
                {data.audit_logs.map((l) => (
                  <div key={l.id} className="py-2 text-xs">
                    <div className="flex justify-between">
                      <span className="font-mono-code font-bold text-slate-900">{l.action}</span>
                      <span className="text-[10px] text-slate-400">{formatLuandaTime(l.created_at)}</span>
                    </div>
                    <p className="font-mono-code text-[11px] text-slate-500">{l.details_json}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* TAB 2: OPERATIONAL MAP */}
        {tab === 'map' && (
          <div className="rounded-2xl border border-slate-200 bg-white p-4">
            <h2 className="mb-3 text-sm font-bold text-slate-900">
              Mapa Operacional de Procura e Oferta em Luanda
            </h2>
            <LuandaMap heightClass="h-[460px]" zoom={12} markers={mapMarkers} demandCircles={demandCircles} />
          </div>
        )}

        {/* TAB 3: FIELD OBSERVATIONS */}
        {tab === 'field' && (
          <div className="grid gap-5 lg:grid-cols-12">
            <form
              onSubmit={handleRecordObservation}
              className="space-y-3 rounded-2xl border border-slate-200 bg-white p-5 lg:col-span-5"
            >
              <h2 className="text-sm font-bold text-slate-900">
                Registar Observação Presencial em Paragem
              </h2>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="mb-1 block text-xs font-semibold text-slate-600">Paragem / Origem</label>
                  <select
                    value={obsForm.origin_zone}
                    onChange={(e) => setObsForm({ ...obsForm, origin_zone: e.target.value })}
                    className="w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-xs font-semibold"
                  >
                    {geo?.zones.map((z) => (
                      <option key={z.id} value={z.name}>{z.name}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="mb-1 block text-xs font-semibold text-slate-600">Destino da Via</label>
                  <select
                    value={obsForm.destination_zone}
                    onChange={(e) => setObsForm({ ...obsForm, destination_zone: e.target.value })}
                    className="w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-xs font-semibold"
                  >
                    {geo?.zones.map((z) => (
                      <option key={z.id} value={z.name}>{z.name}</option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-3 gap-2">
                <div>
                  <label className="mb-1 block text-xs font-semibold text-slate-600">Táxis Obs.</label>
                  <input
                    type="number"
                    min={0}
                    value={obsForm.observed_taxis_count}
                    onChange={(e) => setObsForm({ ...obsForm, observed_taxis_count: Number(e.target.value) })}
                    className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm font-bold"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-semibold text-slate-600">Pass. à Espera</label>
                  <input
                    type="number"
                    min={0}
                    value={obsForm.observed_passengers_count}
                    onChange={(e) => setObsForm({ ...obsForm, observed_passengers_count: Number(e.target.value) })}
                    className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm font-bold"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-semibold text-slate-600">Espera (min)</label>
                  <input
                    type="number"
                    min={0}
                    value={obsForm.estimated_wait_min}
                    onChange={(e) => setObsForm({ ...obsForm, estimated_wait_min: Number(e.target.value) })}
                    className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm font-bold"
                  />
                </div>
              </div>

              <select
                value={obsForm.road_condition}
                onChange={(e) => setObsForm({ ...obsForm, road_condition: e.target.value })}
                className="w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-xs font-semibold"
              >
                <option value="NORMAL">Condição da Via: Circulação Normal</option>
                <option value="MODERATE_TRAFFIC">Trânsito Moderado</option>
                <option value="HEAVY_TRAFFIC">Trânsito Intenso</option>
                <option value="DISRUPTED">Via Condicionada</option>
              </select>

              <input
                type="text"
                value={obsForm.notes}
                onChange={(e) => setObsForm({ ...obsForm, notes: e.target.value })}
                placeholder="Notas operacionais da paragem..."
                className="w-full rounded-xl border border-slate-300 px-3 py-2 text-xs"
              />

              <button
                type="submit"
                disabled={busy}
                className="w-full rounded-xl bg-emerald-700 py-2.5 text-xs font-bold text-white hover:bg-emerald-800"
              >
                Registar Observação de Campo
              </button>
            </form>

            <div className="rounded-2xl border border-slate-200 bg-white p-5 lg:col-span-7">
              <h2 className="mb-3 text-sm font-bold text-slate-900">Observações Recentes de Procura (Campo)</h2>
              <div className="divide-y divide-slate-100">
                {data?.demand_observations.map((o) => (
                  <div key={o.id} className="flex flex-wrap items-center justify-between gap-2 py-2.5 text-xs">
                    <div>
                      <p className="font-bold text-slate-900">
                        {o.origin_zone} → {o.destination_zone}: {o.observed_passengers_count} pass. à espera
                      </p>
                      <p className="text-[11px] text-slate-500">
                        {formatLuandaTime(o.observed_at)} • {o.validation_status} • {o.freshness_status}
                        {o.notes ? ` • ${o.notes}` : ''}
                      </p>
                    </div>
                    {user?.role === 'ADMIN' && o.validation_status === 'PENDING' && (
                      <div className="flex gap-1.5">
                        <button
                          type="button"
                          onClick={() => handleValidationDecision('DEMAND_OBS', o.id, 'VALIDATED')}
                          className="inline-flex items-center gap-1 rounded-lg bg-emerald-700 px-2.5 py-1 text-[11px] font-bold text-white"
                        >
                          <CheckCircle2 className="h-3.5 w-3.5" /> Validar
                        </button>
                        <button
                          type="button"
                          onClick={() => handleValidationDecision('DEMAND_OBS', o.id, 'REJECTED')}
                          className="inline-flex items-center gap-1 rounded-lg bg-red-50 px-2.5 py-1 text-[11px] font-bold text-red-700"
                        >
                          <XCircle className="h-3.5 w-3.5" /> Rejeitar
                        </button>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* TAB 4: DATA QUALITY */}
        {tab === 'quality' && data && (
          <div className="rounded-2xl border border-slate-200 bg-white p-5">
            <h2 className="mb-3 text-sm font-bold text-slate-900">
              Controlo de Qualidade, Expiração e Detecção de Anomalias
            </h2>
            <div className="divide-y divide-slate-100">
              {data.active_intentions.map((it) => (
                <div key={it.id} className="flex flex-wrap items-center justify-between gap-2 py-2.5 text-xs">
                  <div>
                    <p className="font-bold text-slate-900">
                      Intenção #{it.id}: {it.origin_zone} → {it.destination_zone} ({it.passenger_count} pass.)
                    </p>
                    <p className="text-[11px] text-slate-500">
                      Estado: {it.status} • Validação: {it.validation_status} • Frescura: {it.freshness_status} (
                      {it.age_minutes} min)
                    </p>
                  </div>
                  {user?.role === 'ADMIN' && (
                    <div className="flex gap-1.5">
                      <button
                        type="button"
                        onClick={() => handleValidationDecision('INTENTION', it.id, 'VALIDATED')}
                        className="rounded-lg bg-emerald-50 px-2.5 py-1 text-[11px] font-bold text-emerald-800"
                      >
                        Confirmar
                      </button>
                      <button
                        type="button"
                        onClick={() => handleValidationDecision('INTENTION', it.id, 'FLAGGED_SUSPICIOUS')}
                        className="rounded-lg bg-red-50 px-2.5 py-1 text-[11px] font-bold text-red-700"
                      >
                        Marcar Suspeito
                      </button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* TAB 5: GEOGRAPHY & STOPS */}
        {tab === 'geo' && geo && (
          <div className="grid gap-5 lg:grid-cols-12">
            {user?.role === 'ADMIN' && (
              <form
                onSubmit={handleCreateStop}
                className="space-y-3 rounded-2xl border border-slate-200 bg-white p-5 lg:col-span-4"
              >
                <div className="flex items-center gap-2">
                  <Plus className="h-4 w-4 text-emerald-700" />
                  <h2 className="text-sm font-bold text-slate-900">Cadastrar Paragem Real</h2>
                </div>
                <select
                  value={stopForm.zone_id}
                  onChange={(e) => setStopForm({ ...stopForm, zone_id: Number(e.target.value) })}
                  className="w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-xs font-semibold"
                >
                  {geo.zones.map((z) => (
                    <option key={z.id} value={z.id}>{z.name} ({z.municipality})</option>
                  ))}
                </select>
                <input
                  required
                  placeholder="Nome oficial da paragem"
                  value={stopForm.name}
                  onChange={(e) => setStopForm({ ...stopForm, name: e.target.value })}
                  className="w-full rounded-xl border border-slate-300 px-3 py-2 text-xs"
                />
                <input
                  placeholder="Ponto de referência"
                  value={stopForm.landmark}
                  onChange={(e) => setStopForm({ ...stopForm, landmark: e.target.value })}
                  className="w-full rounded-xl border border-slate-300 px-3 py-2 text-xs"
                />
                <div className="grid grid-cols-2 gap-2">
                  <input
                    type="number"
                    step="0.0001"
                    value={stopForm.latitude}
                    onChange={(e) => setStopForm({ ...stopForm, latitude: Number(e.target.value) })}
                    className="rounded-xl border border-slate-300 px-2.5 py-2 text-xs font-mono-code"
                  />
                  <input
                    type="number"
                    step="0.0001"
                    value={stopForm.longitude}
                    onChange={(e) => setStopForm({ ...stopForm, longitude: Number(e.target.value) })}
                    className="rounded-xl border border-slate-300 px-2.5 py-2 text-xs font-mono-code"
                  />
                </div>
                <button
                  type="submit"
                  disabled={busy}
                  className="w-full rounded-xl bg-slate-900 py-2.5 text-xs font-bold text-white"
                >
                  Guardar Paragem Validada
                </button>
              </form>
            )}

            <div className="rounded-2xl border border-slate-200 bg-white p-5 lg:col-span-8">
              <h2 className="mb-3 text-sm font-bold text-slate-900">
                Paragens e Vias Registadas em Luanda ({geo.stops.length} paragens • {geo.routes.length} vias)
              </h2>
              <div className="divide-y divide-slate-100">
                {geo.stops.map((s) => (
                  <div key={s.id} className="flex items-center justify-between py-2.5 text-xs">
                    <div>
                      <p className="font-bold text-slate-900">{s.name}</p>
                      <p className="text-[11px] text-slate-500">
                        Zona: {s.zone_name} • {s.landmark ?? '—'} • ({s.latitude.toFixed(4)}, {s.longitude.toFixed(4)})
                      </p>
                    </div>
                    <span className="rounded-full bg-emerald-50 px-2.5 py-0.5 text-[10px] font-bold text-emerald-800">
                      {s.is_validated ? 'Validada' : 'Pendente'}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* TAB 6: HISTORICAL REPORTS */}
        {tab === 'reports' && data && (
          <div className="space-y-5">
            <div className="rounded-2xl border border-emerald-200 bg-emerald-50/70 p-4 text-xs text-emerald-950">
              {data.analytics.predictive_model_note}
            </div>
            <div className="grid gap-5 lg:grid-cols-2">
              <div className="rounded-2xl border border-slate-200 bg-white p-5">
                <h2 className="mb-3 text-sm font-bold text-slate-900">Procura por Hora (Africa/Luanda)</h2>
                <div className="flex h-40 items-end gap-1 border-b border-slate-200 pb-2">
                  {data.analytics.demand_by_hour.map((h) => {
                    const pct = Math.max(6, Math.round((h.passengers / maxHour) * 100));
                    return (
                      <div key={h.hour} className="flex flex-1 flex-col items-center gap-1">
                        <div
                          className={`w-full rounded-t ${h.passengers > 0 ? 'bg-emerald-600' : 'bg-slate-200'}`}
                          style={{ height: `${h.passengers > 0 ? pct : 6}%` }}
                          title={`${h.hour}: ${h.passengers}`}
                        />
                        <span className="text-[8px] text-slate-400">{h.hour.replace('h', '')}</span>
                      </div>
                    );
                  })}
                </div>
              </div>

              <div className="rounded-2xl border border-slate-200 bg-white p-5">
                <h2 className="mb-3 text-sm font-bold text-slate-900">
                  Procura por Município e Destino
                </h2>
                <div className="grid grid-cols-2 gap-4 text-xs">
                  <div>
                    <p className="mb-1.5 font-bold text-slate-500">Municípios</p>
                    {data.analytics.demand_by_municipality.map((m) => (
                      <div key={m.name} className="flex justify-between py-1 border-b border-slate-100">
                        <span>{m.name}</span>
                        <strong>{m.passengers}</strong>
                      </div>
                    ))}
                  </div>
                  <div>
                    <p className="mb-1.5 font-bold text-slate-500">Destinos</p>
                    {data.analytics.demand_by_destination.map((d) => (
                      <div key={d.name} className="flex justify-between py-1 border-b border-slate-100">
                        <span>{d.name}</span>
                        <strong>{d.passengers}</strong>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* TAB 7: CONFIGURABLE THRESHOLDS */}
        {tab === 'config' && data && (
          <form
            onSubmit={handleSaveConfig}
            className="mx-auto max-w-3xl space-y-4 rounded-2xl border border-slate-200 bg-white p-6"
          >
            <h2 className="text-base font-bold text-slate-900">
              Limites Configuráveis de Procura, Oferta e Expiração
            </h2>
            <div className="space-y-3">
              {data.configs.map((c) => (
                <div key={c.key} className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 pb-3 text-xs">
                  <div>
                    <p className="font-mono-code font-bold text-slate-900">{c.key}</p>
                    <p className="text-slate-500">{c.description}</p>
                  </div>
                  <input
                    type="text"
                    value={configDraft[c.key] ?? c.value}
                    onChange={(e) => setConfigDraft({ ...configDraft, [c.key]: e.target.value })}
                    className="w-24 rounded-xl border border-slate-300 px-3 py-1.5 text-center font-mono-code font-bold"
                  />
                </div>
              ))}
            </div>
            {user?.role === 'ADMIN' && (
              <button
                type="submit"
                disabled={busy}
                className="rounded-xl bg-emerald-700 px-5 py-2.5 text-xs font-bold text-white hover:bg-emerald-800"
              >
                Guardar Limites Configuráveis
              </button>
            )}
          </form>
        )}
      </main>
    </div>
  );
};
