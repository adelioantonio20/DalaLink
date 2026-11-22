import React, { useCallback, useEffect, useState } from 'react';
import {
  Building2,
  CalendarClock,
  CreditCard,
  Plus,
  Route as RouteIcon,
  Send,
  Users,
} from 'lucide-react';
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
  requests: TransportRequestDTO[];
  trips: TripDTO[];
  cost_summary: {
    total_requests: number;
    total_trips: number;
    total_estimated_cost_aoa: number;
    active_employees: number;
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
  const [shiftTime, setShiftTime] = useState('17:00');
  const [busy, setBusy] = useState(false);
  const [banner, setBanner] = useState<{ type: 'ok' | 'err'; text: string } | null>(null);

  const loadData = useCallback(async () => {
    try {
      const res = await apiRequest<CorporateDashboardDTO>('/corporate/dashboard');
      setData(res);
    } catch {
      // ignore transient error
    }
  }, []);

  useEffect(() => {
    loadData();
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
          }),
        }
      );
      setBanner({
        type: 'ok',
        text: `Turno ${shiftTime} agrupado com sucesso: ${res.total_employees_scheduled} colaboradores distribuídos em ${res.dispatched_groups} rota(s) enviadas aos motoristas.`,
      });
      await loadData();
    } catch (err) {
      setBanner({ type: 'err', text: err instanceof Error ? err.message : 'Erro ao despachar turno.' });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 pb-16">
      <TopBar />

      <main className="mx-auto max-w-6xl space-y-5 px-4 py-5">
        {/* Company Header */}
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
            <button
              type="button"
              disabled={busy}
              onClick={handleDispatchShift}
              className="inline-flex items-center gap-2 rounded-xl bg-emerald-700 px-4 py-2.5 text-xs font-bold text-white shadow-xs transition hover:bg-emerald-800 disabled:opacity-50"
            >
              <Send className="h-4 w-4" /> Agrupar e Solicitar Transporte ({shiftTime})
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
            <button type="button" onClick={() => setBanner(null)} className="ml-4 text-slate-500">
              ✕
            </button>
          </div>
        )}

        {/* Summary KPIs */}
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
            <p className="text-xs font-semibold text-slate-500">Rotas Corporativas</p>
            <p className="mt-1.5 text-2xl font-extrabold text-slate-900">{data?.routes.length ?? 0}</p>
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

        <div className="grid gap-5 lg:grid-cols-12">
          {/* Employees */}
          <section className="space-y-4 rounded-2xl border border-slate-200 bg-white p-5 lg:col-span-7">
            <div className="flex items-center gap-2">
              <Users className="h-5 w-5 text-emerald-700" />
              <h2 className="text-sm font-bold text-slate-900">Colaboradores e Destinos de Turno</h2>
            </div>

            <form onSubmit={handleAddEmployee} className="grid gap-2 rounded-xl bg-slate-50 p-3 sm:grid-cols-3">
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
                <div key={e.id} className="flex flex-wrap items-center justify-between gap-2 py-2.5 text-xs">
                  <div>
                    <p className="font-bold text-slate-900">{e.full_name}</p>
                    <p className="text-slate-500">
                      {e.department} • {e.email}
                    </p>
                  </div>
                  <div className="text-right">
                    <p className="font-semibold text-emerald-700">
                      {e.pickup_zone} → {e.dropoff_zone}
                    </p>
                    <p className="text-[11px] text-slate-400">Turno {e.shift_time}</p>
                  </div>
                </div>
              ))}
            </div>
          </section>

          {/* Corporate Routes & Dispatched Requests */}
          <section className="space-y-4 lg:col-span-5">
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
                      <option key={z} value={z}>
                        {z}
                      </option>
                    ))}
                  </select>
                  <select
                    value={routeForm.destination_zone}
                    onChange={(e) => setRouteForm({ ...routeForm, destination_zone: e.target.value })}
                    className="rounded-lg border border-slate-300 bg-white px-2 py-1.5 text-xs"
                  >
                    {LUANDA_ZONE_OPTIONS.map((z) => (
                      <option key={z} value={z}>
                        {z}
                      </option>
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
                  Criar Rota Recorrente
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
                    <p className="mt-0.5 text-slate-500">
                      {r.origin_zone} → {r.destination_zone}
                    </p>
                  </div>
                ))}
              </div>
            </div>

            <div className="rounded-2xl border border-slate-200 bg-white p-5">
              <div className="mb-3 flex items-center gap-2">
                <CreditCard className="h-5 w-5 text-emerald-700" />
                <h2 className="text-sm font-bold text-slate-900">Solicitações Corporativas Recentes</h2>
              </div>
              {data && data.requests.length > 0 ? (
                <div className="space-y-2">
                  {data.requests.slice(0, 8).map((req) => (
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
                        {formatLuandaTime(req.created_at)} • Custo estimado:{' '}
                        <strong>{formatAOA(req.estimated_total_fare_aoa)}</strong>
                      </p>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-slate-500">
                  Clique em <strong>Agrupar e Solicitar Transporte (17:00)</strong> acima para despachar os
                  colaboradores agrupados por destino.
                </p>
              )}
            </div>
          </section>
        </div>
      </main>
    </div>
  );
};
