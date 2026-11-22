import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Building2,
  CalendarClock,
  CreditCard,
  Download,
  Map as MapIcon,
  Play,
  Plus,
  Repeat,
  Route as RouteIcon,
  Send,
  Users,
} from 'lucide-react';
import { LuandaMap, MapMarkerItem } from '../../components/LuandaMap';
import { TopBar } from '../../components/TopBar';
import { apiRequest, formatAOA, formatLuandaTime } from '../../services/api';
import { TransportRequestDTO, TripDTO } from '../../types';

interface CorporateDashboardDTO {
  company: {
    id: number;
    name: string;
    nif: string;
    contact_email: string;
    contact_phone: string;
    headquarters_zone: string;
  };
  subscription: {
    id: number;
    plan_name: string;
    monthly_fee_aoa: number;
    max_employees: number;
    status: string;
    start_date: string;
    end_date: string;
  } | null;
  employees: {
    id: number;
    full_name: string;
    email: string;
    department: string;
    pickup_zone: string;
    dropoff_zone: string;
    shift_time: string;
    status: string;
  }[];
  routes: {
    id: number;
    name: string;
    origin_zone: string;
    destination_zone: string;
    scheduled_time: string;
    is_active: boolean;
    notes?: string;
  }[];
  recurring_bookings: {
    id: number;
    route_id: number;
    route_name: string;
    origin_zone: string;
    destination_zone: string;
    days_of_week: string;
    shift_time: string;
    vehicle_capacity_hint: number;
    is_active: boolean;
    last_dispatched_at?: string;
  }[];
  requests: TransportRequestDTO[];
  trips: TripDTO[];
  live_vehicles: {
    trip_id: number;
    status: string;
    driver_name: string;
    vehicle_label: string;
    latitude: number;
    longitude: number;
    zone: string;
  }[];
  cost_summary: {
    total_requests: number;
    total_trips: number;
    completed_trips: number;
    total_estimated_cost_aoa: number;
    actual_paid_cost_aoa: number;
    active_employees: number;
    by_route: { corridor: string; requests: number; passengers: number; cost_aoa: number }[];
    by_department: { department: string; active_employees: number; allocated_cost_aoa: number }[];
  };
}

const LUANDA_ZONE_OPTIONS = [
  'Talatona',
  'Gamek',
  'Aeroporto',
  'Maianga',
  'Mutamba',
  'Ingombota',
  'Kilamba',
  'Benfica',
  'Viana',
  'Samba',
];

export const CorporatePortal: React.FC = () => {
  const [tab, setTab] = useState<'ops' | 'employees' | 'routes' | 'reports'>('ops');
  const [data, setData] = useState<CorporateDashboardDTO | null>(null);
  const [empForm, setEmpForm] = useState({
    full_name: '',
    email: '',
    department: 'Operações',
    pickup_zone: 'Talatona',
    dropoff_zone: 'Aeroporto',
    shift_time: '17:00',
  });
  const [routeForm, setRouteForm] = useState({
    name: '',
    origin_zone: 'Talatona',
    destination_zone: 'Mutamba',
    scheduled_time: '17:00',
    notes: '',
  });
  const [recForm, setRecForm] = useState({
    route_id: 0,
    days_of_week: 'SEG,TER,QUA,QUI,SEX',
    shift_time: '17:00',
    vehicle_capacity_hint: 12,
  });
  const [shiftTime, setShiftTime] = useState('17:00');
  const [maxVehicleCap, setMaxVehicleCap] = useState(12);
  const [busy, setBusy] = useState(false);
  const [banner, setBanner] = useState<{ type: 'ok' | 'err'; text: string } | null>(null);

  const loadData = useCallback(async () => {
    try {
      const res = await apiRequest<CorporateDashboardDTO>('/corporate/dashboard');
      setData(res);
      if (res.routes.length > 0 && recForm.route_id === 0) {
        setRecForm((prev) => ({ ...prev, route_id: res.routes[0].id }));
      }
    } catch {
      // ignore transient error
    }
  }, [recForm.route_id]);

  useEffect(() => {
    loadData();
    const timer = window.setInterval(loadData, 8000);
    return () => window.clearInterval(timer);
  }, [loadData]);

  const handleAddEmployee = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setBanner(null);
    try {
      await apiRequest('/corporate/employees', {
        method: 'POST',
        body: JSON.stringify(empForm),
      });
      setEmpForm({
        full_name: '',
        email: '',
        department: 'Operações',
        pickup_zone: 'Talatona',
        dropoff_zone: 'Aeroporto',
        shift_time: '17:00',
      });
      setBanner({ type: 'ok', text: 'Colaborador adicionado e convidado para o plano corporativo.' });
      await loadData();
    } catch (err) {
      setBanner({ type: 'err', text: err instanceof Error ? err.message : 'Erro ao adicionar colaborador.' });
    } finally {
      setBusy(false);
    }
  };

  const handleToggleEmployee = async (empId: number, currentStatus: string) => {
    setBusy(true);
    try {
      await apiRequest(`/corporate/employees/${empId}/status`, {
        method: 'PATCH',
        body: JSON.stringify({ status: currentStatus === 'ACTIVE' ? 'SUSPENDED' : 'ACTIVE' }),
      });
      await loadData();
    } finally {
      setBusy(false);
    }
  };

  const handleCreateRoute = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setBanner(null);
    try {
      await apiRequest('/corporate/routes', {
        method: 'POST',
        body: JSON.stringify(routeForm),
      });
      setRouteForm({
        name: '',
        origin_zone: 'Talatona',
        destination_zone: 'Mutamba',
        scheduled_time: '17:00',
        notes: '',
      });
      setBanner({ type: 'ok', text: 'Rota corporativa criada com sucesso.' });
      await loadData();
    } catch (err) {
      setBanner({ type: 'err', text: err instanceof Error ? err.message : 'Erro ao criar rota.' });
    } finally {
      setBusy(false);
    }
  };

  const handleCreateRecurring = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!recForm.route_id) return;
    setBusy(true);
    setBanner(null);
    try {
      await apiRequest('/corporate/recurring', {
        method: 'POST',
        body: JSON.stringify(recForm),
      });
      setBanner({ type: 'ok', text: 'Viagem recorrente agendada com sucesso!' });
      await loadData();
    } catch (err) {
      setBanner({ type: 'err', text: err instanceof Error ? err.message : 'Erro ao agendar recorrência.' });
    } finally {
      setBusy(false);
    }
  };

  const handleTriggerRecurring = async (id: number) => {
    setBusy(true);
    setBanner(null);
    try {
      const res = await apiRequest<{ dispatched_groups: number; total_employees_scheduled: number }>(
        `/corporate/recurring/${id}/trigger`,
        { method: 'POST' }
      );
      setBanner({
        type: 'ok',
        text: `Recorrência executada: ${res.total_employees_scheduled} colaboradores agrupados em ${res.dispatched_groups} lote(s) enviados aos motoristas.`,
      });
      await loadData();
    } catch (err) {
      setBanner({ type: 'err', text: err instanceof Error ? err.message : 'Erro ao executar recorrência.' });
    } finally {
      setBusy(false);
    }
  };

  const handleDispatchShift = async () => {
    setBusy(true);
    setBanner(null);
    try {
      const res = await apiRequest<{ dispatched_groups: number; total_employees_scheduled: number }>(
        '/corporate/dispatch-shift',
        {
          method: 'POST',
          body: JSON.stringify({
            origin_zone: data?.company.headquarters_zone ?? 'Talatona',
            shift_time: shiftTime,
            max_vehicle_capacity: maxVehicleCap,
          }),
        }
      );
      setBanner({
        type: 'ok',
        text: `Turno ${shiftTime} agrupado automaticamente (máx. ${maxVehicleCap} lug./viatura): ${res.total_employees_scheduled} colaboradores distribuídos em ${res.dispatched_groups} viagem(ns).`,
      });
      await loadData();
    } catch (err) {
      setBanner({ type: 'err', text: err instanceof Error ? err.message : 'Erro ao despachar turno.' });
    } finally {
      setBusy(false);
    }
  };

  const handleDownloadCsv = async () => {
    const token = localStorage.getItem('dalalink_token');
    const res = await fetch('/api/v1/corporate/reports/costs.csv', {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!res.ok) return;
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `dalalink_relatorio_custos_${data?.company.nif ?? 'empresa'}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const mapMarkers: MapMarkerItem[] = useMemo(() => {
    if (!data) return [];
    const items: MapMarkerItem[] = [];
    data.live_vehicles.forEach((v) =>
      items.push({
        id: `corp-v-${v.trip_id}`,
        lat: v.latitude,
        lng: v.longitude,
        label: v.vehicle_label,
        sublabel: `${v.driver_name} • ${v.status} • ${v.zone}`,
        kind: 'vehicle_busy',
      })
    );
    data.requests.slice(0, 10).forEach((r) =>
      items.push({
        id: `corp-r-${r.id}`,
        lat: r.dropoff_lat,
        lng: r.dropoff_lng,
        label: `Destino Corporativo: ${r.dropoff_zone}`,
        sublabel: `${r.passenger_count} colab. • ${r.status}`,
        kind: 'dropoff',
      })
    );
    return items;
  }, [data]);

  return (
    <div className="min-h-screen bg-slate-50 pb-16">
      <TopBar />

      <main className="mx-auto max-w-6xl space-y-5 px-4 py-5">
        {/* Header & Shift Dispatch Bar */}
        <div className="flex flex-col gap-4 rounded-2xl border border-slate-200 bg-white p-5 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-3.5">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-amber-700 text-white">
              <Building2 className="h-6 w-6" />
            </div>
            <div>
              <h1 className="text-xl font-extrabold text-slate-900">
                {data?.company.name ?? 'Portal Empresarial'}
              </h1>
              <p className="text-xs text-slate-500">
                NIF: <strong className="font-mono-code">{data?.company.nif}</strong> • Sede:{' '}
                <strong>{data?.company.headquarters_zone}</strong> • Plano:{' '}
                <strong className="text-emerald-700">{data?.subscription?.plan_name}</strong>
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <input
              type="time"
              value={shiftTime}
              onChange={(e) => setShiftTime(e.target.value)}
              className="rounded-xl border border-slate-300 bg-white px-3 py-2 text-xs font-bold"
            />
            <select
              value={maxVehicleCap}
              onChange={(e) => setMaxVehicleCap(Number(e.target.value))}
              className="rounded-xl border border-slate-300 bg-white px-2.5 py-2 text-xs font-semibold"
              title="Capacidade máxima por viatura"
            >
              <option value={4}>Sedan (4 lug.)</option>
              <option value={12}>Carrinha HiAce (12 lug.)</option>
              <option value={20}>Autocarro (20 lug.)</option>
            </select>
            <button
              type="button"
              disabled={busy}
              onClick={handleDispatchShift}
              className="inline-flex items-center gap-2 rounded-xl bg-emerald-700 px-4 py-2.5 text-xs font-bold text-white shadow-xs transition hover:bg-emerald-800 disabled:opacity-50"
            >
              <Send className="h-4 w-4" /> Agrupar e Despachar ({shiftTime})
            </button>
          </div>
        </div>

        {/* Tab Strip */}
        <div className="flex flex-wrap gap-1.5 rounded-2xl bg-white p-1.5 shadow-xs ring-1 ring-slate-200">
          {[
            { id: 'ops', label: 'Operação & Mapa', icon: MapIcon },
            { id: 'employees', label: 'Colaboradores', icon: Users },
            { id: 'routes', label: 'Rotas & Recorrência', icon: Repeat },
            { id: 'reports', label: 'Relatório de Custos & Contrato', icon: CreditCard },
          ].map((item) => {
            const Icon = item.icon;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => setTab(item.id as typeof tab)}
                className={`inline-flex items-center gap-1.5 rounded-xl px-3.5 py-2 text-xs font-bold transition ${
                  tab === item.id ? 'bg-slate-900 text-white' : 'text-slate-600 hover:bg-slate-100'
                }`}
              >
                <Icon className="h-4 w-4" />
                {item.label}
              </button>
            );
          })}
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

        {/* KPI Cards */}
        <div className="grid gap-3 sm:grid-cols-4">
          <div className="rounded-2xl border border-slate-200 bg-white p-4">
            <p className="text-xs font-semibold text-slate-500">Colaboradores Ativos</p>
            <p className="mt-1.5 text-2xl font-extrabold text-slate-900">
              {data?.cost_summary.active_employees ?? 0}{' '}
              <span className="text-xs font-medium text-slate-400">
                / {data?.subscription?.max_employees ?? 100}
              </span>
            </p>
          </div>
          <div className="rounded-2xl border border-slate-200 bg-white p-4">
            <p className="text-xs font-semibold text-slate-500">Rotas / Recorrências</p>
            <p className="mt-1.5 text-2xl font-extrabold text-slate-900">
              {data?.routes.length ?? 0} / {data?.recurring_bookings.length ?? 0}
            </p>
          </div>
          <div className="rounded-2xl border border-slate-200 bg-white p-4">
            <p className="text-xs font-semibold text-slate-500">Subscrição Mensal</p>
            <p className="mt-1.5 text-2xl font-extrabold text-emerald-700">
              {formatAOA(data?.subscription?.monthly_fee_aoa ?? 0)}
            </p>
          </div>
          <div className="rounded-2xl border border-slate-200 bg-white p-4">
            <p className="text-xs font-semibold text-slate-500">Custo Estimado Viagens</p>
            <p className="mt-1.5 text-2xl font-extrabold text-amber-700">
              {formatAOA(data?.cost_summary.total_estimated_cost_aoa ?? 0)}
            </p>
          </div>
        </div>

        {/* TAB 1: OPERATIONS & LIVE MAP */}
        {tab === 'ops' && (
          <div className="grid gap-5 lg:grid-cols-12">
            <div className="rounded-2xl border border-slate-200 bg-white p-4 lg:col-span-7">
              <h2 className="mb-3 text-sm font-bold text-slate-900">
                Acompanhamento de Viaturas e Destinos Corporativos em Luanda
              </h2>
              <LuandaMap heightClass="h-96" zoom={12} markers={mapMarkers} />
            </div>

            <div className="rounded-2xl border border-slate-200 bg-white p-5 lg:col-span-5">
              <h2 className="mb-3 text-sm font-bold text-slate-900">
                Solicitações Corporativas Despachadas
              </h2>
              {data && data.requests.length > 0 ? (
                <div className="max-h-96 space-y-2 overflow-y-auto pr-1">
                  {data.requests.map((req) => (
                    <div key={req.id} className="rounded-xl bg-slate-50 p-3 text-xs">
                      <div className="flex items-center justify-between">
                        <span className="font-bold text-slate-900">
                          {req.pickup_zone} → {req.dropoff_zone} ({req.passenger_count} colab.)
                        </span>
                        <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-bold text-emerald-800">
                          {req.status}
                        </span>
                      </div>
                      <p className="mt-1 text-[11px] text-slate-500">
                        {formatLuandaTime(req.created_at)} • Estimativa:{' '}
                        <strong>{formatAOA(req.estimated_total_fare_aoa)}</strong>
                      </p>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-slate-500">
                  Clique em <strong>Agrupar e Despachar (17:00)</strong> para agrupar os colaboradores por
                  destino e capacidade de veículo.
                </p>
              )}
            </div>
          </div>
        )}

        {/* TAB 2: EMPLOYEES */}
        {tab === 'employees' && (
          <section className="space-y-4 rounded-2xl border border-slate-200 bg-white p-5">
            <h2 className="text-sm font-bold text-slate-900">Gestão e Convite de Colaboradores</h2>
            <form onSubmit={handleAddEmployee} className="grid gap-2 rounded-xl bg-slate-50 p-3 sm:grid-cols-6">
              <input
                required
                placeholder="Nome completo"
                value={empForm.full_name}
                onChange={(e) => setEmpForm({ ...empForm, full_name: e.target.value })}
                className="rounded-lg border border-slate-300 bg-white px-2.5 py-2 text-xs"
              />
              <input
                required
                type="email"
                placeholder="Email corporativo"
                value={empForm.email}
                onChange={(e) => setEmpForm({ ...empForm, email: e.target.value })}
                className="rounded-lg border border-slate-300 bg-white px-2.5 py-2 text-xs"
              />
              <input
                placeholder="Departamento"
                value={empForm.department}
                onChange={(e) => setEmpForm({ ...empForm, department: e.target.value })}
                className="rounded-lg border border-slate-300 bg-white px-2.5 py-2 text-xs"
              />
              <select
                value={empForm.dropoff_zone}
                onChange={(e) => setEmpForm({ ...empForm, dropoff_zone: e.target.value })}
                className="rounded-lg border border-slate-300 bg-white px-2.5 py-2 text-xs"
              >
                {LUANDA_ZONE_OPTIONS.map((z) => (
                  <option key={z} value={z}>
                    Destino: {z}
                  </option>
                ))}
              </select>
              <input
                type="time"
                value={empForm.shift_time}
                onChange={(e) => setEmpForm({ ...empForm, shift_time: e.target.value })}
                className="rounded-lg border border-slate-300 bg-white px-2.5 py-2 text-xs"
              />
              <button
                type="submit"
                disabled={busy}
                className="inline-flex items-center justify-center gap-1 rounded-lg bg-slate-900 px-3 py-2 text-xs font-bold text-white hover:bg-slate-800"
              >
                <Plus className="h-3.5 w-3.5" /> Convidar
              </button>
            </form>

            <div className="divide-y divide-slate-100">
              {data?.employees.map((e) => (
                <div key={e.id} className="flex flex-wrap items-center justify-between gap-2 py-3 text-xs">
                  <div>
                    <p className="font-bold text-slate-900">{e.full_name}</p>
                    <p className="text-slate-500">
                      {e.department} • {e.email}
                    </p>
                  </div>
                  <div className="flex items-center gap-3">
                    <div className="text-right">
                      <p className="font-semibold text-emerald-700">
                        {e.pickup_zone} → {e.dropoff_zone}
                      </p>
                      <p className="text-[11px] text-slate-400">Turno {e.shift_time}</p>
                    </div>
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => handleToggleEmployee(e.id, e.status)}
                      className={`rounded-lg px-2.5 py-1 text-[11px] font-bold ${
                        e.status === 'ACTIVE'
                          ? 'bg-emerald-50 text-emerald-800 hover:bg-emerald-100'
                          : 'bg-red-50 text-red-700 hover:bg-red-100'
                      }`}
                    >
                      {e.status}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* TAB 3: ROUTES & RECURRING BOOKINGS */}
        {tab === 'routes' && (
          <div className="grid gap-5 lg:grid-cols-2">
            <div className="space-y-3 rounded-2xl border border-slate-200 bg-white p-5">
              <div className="flex items-center gap-2">
                <RouteIcon className="h-5 w-5 text-amber-600" />
                <h2 className="text-sm font-bold text-slate-900">Rotas Corporativas</h2>
              </div>

              <form onSubmit={handleCreateRoute} className="space-y-2 rounded-xl bg-slate-50 p-3">
                <input
                  required
                  placeholder="Nome da rota (ex: Talatona → Benfica)"
                  value={routeForm.name}
                  onChange={(e) => setRouteForm({ ...routeForm, name: e.target.value })}
                  className="w-full rounded-lg border border-slate-300 bg-white px-2.5 py-2 text-xs"
                />
                <div className="grid grid-cols-3 gap-2">
                  <select
                    value={routeForm.origin_zone}
                    onChange={(e) => setRouteForm({ ...routeForm, origin_zone: e.target.value })}
                    className="rounded-lg border border-slate-300 bg-white px-2 py-1.5 text-xs"
                  >
                    {LUANDA_ZONE_OPTIONS.map((z) => (
                      <option key={z} value={z}>{z}</option>
                    ))}
                  </select>
                  <select
                    value={routeForm.destination_zone}
                    onChange={(e) => setRouteForm({ ...routeForm, destination_zone: e.target.value })}
                    className="rounded-lg border border-slate-300 bg-white px-2 py-1.5 text-xs"
                  >
                    {LUANDA_ZONE_OPTIONS.map((z) => (
                      <option key={z} value={z}>{z}</option>
                    ))}
                  </select>
                  <input
                    type="time"
                    value={routeForm.scheduled_time}
                    onChange={(e) => setRouteForm({ ...routeForm, scheduled_time: e.target.value })}
                    className="rounded-lg border border-slate-300 bg-white px-2 py-1.5 text-xs"
                  />
                </div>
                <button
                  type="submit"
                  disabled={busy}
                  className="w-full rounded-lg bg-amber-700 py-2 text-xs font-bold text-white hover:bg-amber-800"
                >
                  Criar Rota Corporativa
                </button>
              </form>

              <div className="space-y-2">
                {data?.routes.map((r) => (
                  <div key={r.id} className="rounded-xl bg-slate-50 p-3 text-xs">
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-slate-900">{r.name}</span>
                      <span className="inline-flex items-center gap-1 font-mono-code text-[11px] font-bold text-emerald-700">
                        <CalendarClock className="h-3.5 w-3.5" /> {r.scheduled_time}
                      </span>
                    </div>
                    <p className="mt-0.5 text-slate-500">{r.origin_zone} → {r.destination_zone}</p>
                  </div>
                ))}
              </div>
            </div>

            <div className="space-y-3 rounded-2xl border border-slate-200 bg-white p-5">
              <div className="flex items-center gap-2">
                <Repeat className="h-5 w-5 text-emerald-700" />
                <h2 className="text-sm font-bold text-slate-900">Viagens Recorrentes Agendadas</h2>
              </div>

              <form onSubmit={handleCreateRecurring} className="space-y-2 rounded-xl bg-slate-50 p-3">
                <select
                  value={recForm.route_id}
                  onChange={(e) => setRecForm({ ...recForm, route_id: Number(e.target.value) })}
                  className="w-full rounded-lg border border-slate-300 bg-white px-2.5 py-2 text-xs"
                >
                  {data?.routes.map((r) => (
                    <option key={r.id} value={r.id}>{r.name}</option>
                  ))}
                </select>
                <div className="grid grid-cols-3 gap-2">
                  <input
                    value={recForm.days_of_week}
                    onChange={(e) => setRecForm({ ...recForm, days_of_week: e.target.value })}
                    placeholder="SEG,TER,QUA,QUI,SEX"
                    className="rounded-lg border border-slate-300 bg-white px-2 py-1.5 text-xs"
                  />
                  <input
                    type="time"
                    value={recForm.shift_time}
                    onChange={(e) => setRecForm({ ...recForm, shift_time: e.target.value })}
                    className="rounded-lg border border-slate-300 bg-white px-2 py-1.5 text-xs"
                  />
                  <input
                    type="number"
                    min={2}
                    max={50}
                    value={recForm.vehicle_capacity_hint}
                    onChange={(e) => setRecForm({ ...recForm, vehicle_capacity_hint: Number(e.target.value) })}
                    className="rounded-lg border border-slate-300 bg-white px-2 py-1.5 text-xs"
                  />
                </div>
                <button
                  type="submit"
                  disabled={busy}
                  className="w-full rounded-lg bg-emerald-700 py-2 text-xs font-bold text-white hover:bg-emerald-800"
                >
                  Agendar Viagem Recorrente
                </button>
              </form>

              <div className="space-y-2">
                {data?.recurring_bookings.map((rb) => (
                  <div key={rb.id} className="flex items-center justify-between gap-3 rounded-xl bg-slate-50 p-3 text-xs">
                    <div>
                      <p className="font-bold text-slate-900">{rb.route_name}</p>
                      <p className="text-[11px] text-slate-500">
                        {rb.days_of_week} • {rb.shift_time} • Máx. {rb.vehicle_capacity_hint} lug./viatura
                      </p>
                      {rb.last_dispatched_at && (
                        <p className="text-[10px] text-emerald-700">
                          Último despacho: {formatLuandaTime(rb.last_dispatched_at)}
                        </p>
                      )}
                    </div>
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => handleTriggerRecurring(rb.id)}
                      className="inline-flex items-center gap-1 rounded-lg bg-slate-900 px-3 py-1.5 text-[11px] font-bold text-white hover:bg-slate-800"
                    >
                      <Play className="h-3 w-3" /> Executar Agora
                    </button>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* TAB 4: COST REPORTS & CONTRACT */}
        {tab === 'reports' && data && (
          <div className="grid gap-5 lg:grid-cols-2">
            <div className="rounded-2xl border border-slate-200 bg-white p-5">
              <div className="mb-4 flex items-center justify-between">
                <h2 className="text-sm font-bold text-slate-900">Custos por Corredor Corporativo</h2>
                <button
                  type="button"
                  onClick={handleDownloadCsv}
                  className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-700 px-3 py-1.5 text-xs font-bold text-white hover:bg-emerald-800"
                >
                  <Download className="h-3.5 w-3.5" /> Exportar CSV
                </button>
              </div>
              {data.cost_summary.by_route.length === 0 ? (
                <p className="text-xs text-slate-500">Despache um turno para gerar custos por rota.</p>
              ) : (
                <div className="divide-y divide-slate-100">
                  {data.cost_summary.by_route.map((r) => (
                    <div key={r.corridor} className="flex items-center justify-between py-2.5 text-xs">
                      <div>
                        <p className="font-bold text-slate-900">{r.corridor}</p>
                        <p className="text-[11px] text-slate-500">
                          {r.requests} pedido(s) • {r.passengers} colaborador(es)
                        </p>
                      </div>
                      <span className="font-mono-code font-extrabold text-emerald-700">
                        {formatAOA(r.cost_aoa)}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="rounded-2xl border border-slate-200 bg-white p-5">
              <h2 className="mb-4 text-sm font-bold text-slate-900">
                Alocação de Custos por Departamento & Contrato
              </h2>
              <div className="divide-y divide-slate-100">
                {data.cost_summary.by_department.map((d) => (
                  <div key={d.department} className="flex items-center justify-between py-2.5 text-xs">
                    <span>
                      <strong className="text-slate-900">{d.department}</strong> ({d.active_employees} colab.)
                    </span>
                    <span className="font-mono-code font-bold text-slate-800">
                      {formatAOA(d.allocated_cost_aoa)}
                    </span>
                  </div>
                ))}
              </div>
              {data.subscription && (
                <div className="mt-4 rounded-xl bg-slate-900 p-4 text-xs text-white">
                  <p className="text-[11px] uppercase tracking-wider text-emerald-400">
                    Contrato Ativo ({data.subscription.status})
                  </p>
                  <p className="mt-1 text-base font-extrabold">{data.subscription.plan_name}</p>
                  <p className="mt-1 text-slate-300">
                    Vigência: {data.subscription.start_date} a {data.subscription.end_date} • Mensalidade:{' '}
                    <strong>{formatAOA(data.subscription.monthly_fee_aoa)}</strong>
                  </p>
                </div>
              )}
            </div>
          </div>
        )}
      </main>
    </div>
  );
};
