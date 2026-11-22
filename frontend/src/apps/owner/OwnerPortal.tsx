import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Car,
  CheckCircle2,
  MapPin,
  Plus,
  RefreshCw,
  Shield,
  TrendingUp,
  Wallet,
} from 'lucide-react';
import { LuandaMap, MapMarkerItem } from '../../components/LuandaMap';
import { TopBar } from '../../components/TopBar';
import { apiRequest, formatAOA } from '../../services/api';

interface OwnerVehicleRow {
  id: number;
  make: string;
  model: string;
  year: number;
  color: string;
  license_plate: string;
  vehicle_type: string;
  capacity: number;
  is_active: boolean;
  driver: {
    id: number;
    full_name: string;
    phone?: string;
    verification_status: string;
    rating_avg: number;
  } | null;
  operational_status: string;
  latitude: number;
  longitude: number;
  current_zone: string;
  performance: {
    completed_trips: number;
    gross_revenue_aoa: number;
    platform_fee_aoa: number;
    net_revenue_aoa: number;
  };
}

interface OwnerDashboardDTO {
  owner: {
    id: number;
    company_name: string;
    tax_id?: string;
    payout_iban?: string;
  };
  summary: {
    total_vehicles: number;
    active_vehicles: number;
    available_vehicles: number;
    busy_vehicles: number;
    total_completed_trips: number;
    gross_revenue_aoa: number;
    platform_fee_aoa: number;
    net_revenue_aoa: number;
  };
  vehicles: OwnerVehicleRow[];
  available_drivers: {
    id: number;
    full_name: string;
    verification_status: string;
    rating_avg: number;
  }[];
}

export const OwnerPortal: React.FC = () => {
  const [data, setData] = useState<OwnerDashboardDTO | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState({
    make: 'Hyundai',
    model: 'i10',
    year: 2024,
    color: 'Branco',
    license_plate: '',
    vehicle_type: 'TAXI_SEDAN',
    capacity: 4,
  });
  const [busy, setBusy] = useState(false);
  const [banner, setBanner] = useState<{ type: 'ok' | 'err'; text: string } | null>(null);

  const loadData = useCallback(async () => {
    try {
      const res = await apiRequest<OwnerDashboardDTO>('/owner/dashboard');
      setData(res);
    } catch {
      // ignore transient error
    }
  }, []);

  useEffect(() => {
    loadData();
    const timer = window.setInterval(loadData, 7000);
    return () => window.clearInterval(timer);
  }, [loadData]);

  const handleRegisterVehicle = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setBanner(null);
    try {
      await apiRequest('/owner/vehicles', {
        method: 'POST',
        body: JSON.stringify(form),
      });
      setShowAdd(false);
      setForm({
        make: 'Hyundai',
        model: 'i10',
        year: 2024,
        color: 'Branco',
        license_plate: '',
        vehicle_type: 'TAXI_SEDAN',
        capacity: 4,
      });
      setBanner({ type: 'ok', text: 'Veículo adicionado à sua frota com sucesso!' });
      await loadData();
    } catch (err) {
      setBanner({ type: 'err', text: err instanceof Error ? err.message : 'Erro ao registar veículo.' });
    } finally {
      setBusy(false);
    }
  };

  const handleAssignDriver = async (vehicleId: number, driverId: number | null) => {
    setBusy(true);
    setBanner(null);
    try {
      await apiRequest(`/owner/vehicles/${vehicleId}/assign-driver`, {
        method: 'PUT',
        body: JSON.stringify({ driver_id: driverId }),
      });
      setBanner({ type: 'ok', text: 'Motorista associado ao veículo com sucesso.' });
      await loadData();
    } catch (err) {
      setBanner({ type: 'err', text: err instanceof Error ? err.message : 'Erro ao atribuir motorista.' });
    } finally {
      setBusy(false);
    }
  };

  const handleToggleActive = async (v: OwnerVehicleRow) => {
    setBusy(true);
    try {
      await apiRequest(`/owner/vehicles/${v.id}/assign-driver`, {
        method: 'PUT',
        body: JSON.stringify({ is_active: !v.is_active }),
      });
      await loadData();
    } finally {
      setBusy(false);
    }
  };

  const mapMarkers: MapMarkerItem[] = useMemo(() => {
    if (!data) return [];
    return data.vehicles.map((v) => ({
      id: `own-veh-${v.id}`,
      lat: v.latitude,
      lng: v.longitude,
      label: `${v.make} ${v.model} (${v.license_plate})`,
      sublabel: `${v.driver?.full_name ?? 'Sem motorista'} • ${v.operational_status} • ${v.current_zone}`,
      kind: v.operational_status === 'AVAILABLE' ? 'vehicle_available' : 'vehicle_busy',
    }));
  }, [data]);

  const s = data?.summary;

  return (
    <div className="min-h-screen bg-slate-50 pb-16">
      <TopBar />

      <main className="mx-auto max-w-6xl space-y-5 px-4 py-5">
        <div className="flex flex-col gap-4 rounded-2xl border border-slate-200 bg-white p-5 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-3.5">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-slate-900 text-emerald-400">
              <Car className="h-6 w-6" />
            </div>
            <div>
              <h1 className="text-xl font-extrabold text-slate-900">
                {data?.owner.company_name ?? 'Portal do Proprietário & Frota'}
              </h1>
              <p className="text-xs text-slate-500">
                NIF: <strong className="font-mono-code">{data?.owner.tax_id ?? '—'}</strong> • IBAN Liquidação:{' '}
                <strong className="font-mono-code">{data?.owner.payout_iban ?? '—'}</strong>
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setShowAdd((x) => !x)}
              className="inline-flex items-center gap-1.5 rounded-xl bg-emerald-700 px-4 py-2.5 text-xs font-bold text-white hover:bg-emerald-800"
            >
              <Plus className="h-4 w-4" /> Adicionar Veículo
            </button>
            <button
              type="button"
              onClick={loadData}
              className="rounded-xl border border-slate-200 bg-white p-2.5 text-slate-600 hover:bg-slate-50"
            >
              <RefreshCw className="h-4 w-4" />
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

        {showAdd && (
          <form
            onSubmit={handleRegisterVehicle}
            className="grid gap-3 rounded-2xl border border-emerald-200 bg-white p-5 sm:grid-cols-6"
          >
            <input
              required
              placeholder="Marca"
              value={form.make}
              onChange={(e) => setForm({ ...form, make: e.target.value })}
              className="rounded-xl border border-slate-300 px-3 py-2 text-xs"
            />
            <input
              required
              placeholder="Modelo"
              value={form.model}
              onChange={(e) => setForm({ ...form, model: e.target.value })}
              className="rounded-xl border border-slate-300 px-3 py-2 text-xs"
            />
            <input
              required
              placeholder="Matrícula (ex: LD-55-22-AA)"
              value={form.license_plate}
              onChange={(e) => setForm({ ...form, license_plate: e.target.value })}
              className="font-mono-code rounded-xl border border-slate-300 px-3 py-2 text-xs uppercase"
            />
            <input
              placeholder="Cor"
              value={form.color}
              onChange={(e) => setForm({ ...form, color: e.target.value })}
              className="rounded-xl border border-slate-300 px-3 py-2 text-xs"
            />
            <input
              type="number"
              min={1}
              max={60}
              value={form.capacity}
              onChange={(e) => setForm({ ...form, capacity: Number(e.target.value) })}
              className="rounded-xl border border-slate-300 px-3 py-2 text-xs"
            />
            <button
              type="submit"
              disabled={busy}
              className="rounded-xl bg-emerald-700 py-2 text-xs font-bold text-white hover:bg-emerald-800"
            >
              Guardar Viatura
            </button>
          </form>
        )}

        {/* Fleet KPIs */}
        {s && (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <div className="rounded-2xl border border-slate-200 bg-white p-4">
              <div className="flex items-center justify-between text-xs font-semibold text-slate-500">
                <span>Frota Ativa</span>
                <Car className="h-4 w-4 text-emerald-700" />
              </div>
              <p className="mt-2 text-2xl font-extrabold text-slate-900">
                {s.active_vehicles}/{s.total_vehicles} viaturas
              </p>
              <p className="mt-1 text-xs text-slate-500">
                {s.available_vehicles} livres • {s.busy_vehicles} em operação
              </p>
            </div>

            <div className="rounded-2xl border border-slate-200 bg-white p-4">
              <div className="flex items-center justify-between text-xs font-semibold text-slate-500">
                <span>Receita Bruta da Frota</span>
                <TrendingUp className="h-4 w-4 text-amber-600" />
              </div>
              <p className="mt-2 text-2xl font-extrabold text-slate-900">{formatAOA(s.gross_revenue_aoa)}</p>
              <p className="mt-1 text-xs text-slate-500">{s.total_completed_trips} viagens concluídas</p>
            </div>

            <div className="rounded-2xl border border-slate-200 bg-white p-4">
              <div className="flex items-center justify-between text-xs font-semibold text-slate-500">
                <span>Receita Líquida (Frota/Motoristas)</span>
                <Wallet className="h-4 w-4 text-emerald-700" />
              </div>
              <p className="mt-2 text-2xl font-extrabold text-emerald-700">{formatAOA(s.net_revenue_aoa)}</p>
              <p className="mt-1 text-xs text-slate-500">
                Comissões DalaLink: {formatAOA(s.platform_fee_aoa)}
              </p>
            </div>

            <div className="rounded-2xl border border-slate-200 bg-white p-4">
              <div className="flex items-center justify-between text-xs font-semibold text-slate-500">
                <span>Conformidade Operacional</span>
                <Shield className="h-4 w-4 text-slate-700" />
              </div>
              <p className="mt-2 text-2xl font-extrabold text-slate-900">100% Rastreável</p>
              <p className="mt-1 text-xs text-slate-500">GPS + Bilhética QR/NFC no servidor</p>
            </div>
          </div>
        )}

        <div className="grid gap-5 lg:grid-cols-12">
          <div className="lg:col-span-5">
            <div className="rounded-2xl border border-slate-200 bg-white p-4">
              <div className="mb-3 flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-slate-500">
                <MapPin className="h-4 w-4 text-emerald-700" /> Localização em Tempo Real da Frota
              </div>
              <LuandaMap heightClass="h-96" zoom={12} markers={mapMarkers} />
            </div>
          </div>

          <div className="lg:col-span-7">
            <div className="rounded-2xl border border-slate-200 bg-white p-5">
              <h2 className="mb-4 text-base font-bold text-slate-900">
                Desempenho e Rentabilidade por Viatura
              </h2>
              <div className="space-y-3">
                {data?.vehicles.map((v) => (
                  <div
                    key={v.id}
                    className="rounded-2xl border border-slate-200 bg-slate-50/70 p-4 text-xs"
                  >
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-extrabold text-slate-900">
                            {v.make} {v.model} ({v.year})
                          </span>
                          <span className="font-mono-code rounded-md bg-slate-900 px-2 py-0.5 text-[11px] font-bold text-amber-300">
                            {v.license_plate}
                          </span>
                          <span
                            className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${
                              v.operational_status === 'AVAILABLE'
                                ? 'bg-emerald-100 text-emerald-800'
                                : v.operational_status === 'BUSY'
                                  ? 'bg-amber-100 text-amber-800'
                                  : 'bg-slate-200 text-slate-600'
                            }`}
                          >
                            {v.operational_status}
                          </span>
                        </div>
                        <p className="mt-1 text-slate-500">
                          {v.color} • {v.capacity} lugares • Zona atual: <strong>{v.current_zone}</strong>
                        </p>
                      </div>

                      <div className="text-right">
                        <p className="text-sm font-extrabold text-emerald-700">
                          {formatAOA(v.performance.net_revenue_aoa)} líquido
                        </p>
                        <p className="text-[11px] text-slate-500">
                          Bruto: {formatAOA(v.performance.gross_revenue_aoa)} • {v.performance.completed_trips}{' '}
                          viagem(ns)
                        </p>
                      </div>
                    </div>

                    <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-slate-200 pt-3">
                      <div className="flex items-center gap-2">
                        <span className="text-[11px] font-semibold text-slate-500">Motorista:</span>
                        <select
                          value={v.driver?.id ?? ''}
                          disabled={busy}
                          onChange={(e) =>
                            handleAssignDriver(v.id, e.target.value ? Number(e.target.value) : null)
                          }
                          className="rounded-lg border border-slate-300 bg-white px-2.5 py-1 text-xs font-semibold"
                        >
                          <option value="">Sem motorista</option>
                          {data.available_drivers.map((d) => (
                            <option key={d.id} value={d.id}>
                              {d.full_name} ({d.verification_status})
                            </option>
                          ))}
                        </select>
                      </div>

                      <button
                        type="button"
                        disabled={busy}
                        onClick={() => handleToggleActive(v)}
                        className={`inline-flex items-center gap-1 rounded-lg px-2.5 py-1 text-[11px] font-bold ${
                          v.is_active
                            ? 'bg-emerald-50 text-emerald-800 hover:bg-emerald-100'
                            : 'bg-red-50 text-red-700 hover:bg-red-100'
                        }`}
                      >
                        <CheckCircle2 className="h-3.5 w-3.5" />
                        {v.is_active ? 'Ativa na Plataforma' : 'Inativa'}
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
};
