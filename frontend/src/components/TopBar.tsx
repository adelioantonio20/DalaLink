import React, { useState } from 'react';
import {
  Car,
  ClipboardCheck,
  LayoutDashboard,
  LogOut,
  Navigation,
  Radio,
  Repeat,
  User as UserIcon,
} from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';

interface TopBarProps {
  dark?: boolean;
}

const DEMO_SWITCH_ACCOUNTS = [
  { label: 'Passageiro (Consultar Vias)', email: 'passageiro@dalalink.ao', icon: UserIcon },
  { label: 'Motorista (Mapa de Procura)', email: 'motorista@dalalink.ao', icon: Car },
  { label: 'Recolha de Campo (Paragens)', email: 'campo@dalalink.ao', icon: ClipboardCheck },
  { label: 'Administração (Controlo & Dados)', email: 'admin@dalalink.ao', icon: LayoutDashboard },
];

export const TopBar: React.FC<TopBarProps> = ({ dark = false }) => {
  const { user, wsConnected, login, logout } = useAuth();
  const [switcherOpen, setSwitcherOpen] = useState(false);
  const [switching, setSwitching] = useState(false);

  const handleQuickSwitch = async (email: string) => {
    setSwitching(true);
    try {
      await login(email, 'dalalink123');
      setSwitcherOpen(false);
    } finally {
      setSwitching(false);
    }
  };

  return (
    <header
      className={`sticky top-0 z-30 border-b backdrop-blur-md ${
        dark
          ? 'border-slate-800 bg-slate-950/95 text-white'
          : 'border-slate-200 bg-white/95 text-slate-900'
      }`}
    >
      <div className="mx-auto flex max-w-7xl items-center justify-between gap-3 px-4 py-3">
        <div className="flex items-center gap-2.5">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-emerald-700 text-white shadow-sm">
            <Navigation className="h-5 w-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-base font-extrabold tracking-tight">DalaLink</span>
              <span
                className={`hidden rounded-md px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider sm:inline-block ${
                  dark ? 'bg-slate-800 text-emerald-400' : 'bg-emerald-50 text-emerald-800'
                }`}
              >
                Inteligência • Luanda
              </span>
            </div>
            <p className={`text-[11px] ${dark ? 'text-slate-400' : 'text-slate-500'}`}>
              {user?.full_name} • {user?.role}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <div
            className={`hidden items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium sm:inline-flex ${
              wsConnected
                ? dark
                  ? 'bg-emerald-500/15 text-emerald-300'
                  : 'bg-emerald-50 text-emerald-700'
                : dark
                  ? 'bg-slate-800 text-slate-400'
                  : 'bg-slate-100 text-slate-500'
            }`}
          >
            <Radio className="h-3.5 w-3.5" />
            {wsConnected ? 'Actualização Activa' : 'A sincronizar'}
          </div>

          <div className="relative">
            <button
              type="button"
              onClick={() => setSwitcherOpen((o) => !o)}
              className={`inline-flex items-center gap-1.5 rounded-xl border px-3 py-1.5 text-xs font-semibold transition ${
                dark
                  ? 'border-slate-700 bg-slate-800 text-slate-200 hover:bg-slate-700'
                  : 'border-slate-200 bg-slate-50 text-slate-700 hover:bg-slate-100'
              }`}
            >
              <Repeat className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">Trocar Perfil</span>
            </button>

            {switcherOpen && (
              <div className="absolute right-0 mt-2 w-64 rounded-2xl border border-slate-200 bg-white p-2 text-slate-900 shadow-xl">
                <p className="px-2.5 py-1.5 text-[11px] font-bold uppercase tracking-wider text-slate-400">
                  Perfis da Plataforma (Luanda)
                </p>
                {DEMO_SWITCH_ACCOUNTS.map((acc) => {
                  const Icon = acc.icon;
                  const active = user?.email === acc.email;
                  return (
                    <button
                      key={acc.email}
                      type="button"
                      disabled={switching}
                      onClick={() => handleQuickSwitch(acc.email)}
                      className={`flex w-full items-center gap-2.5 rounded-xl px-2.5 py-2 text-left text-xs font-medium transition ${
                        active
                          ? 'bg-emerald-50 font-bold text-emerald-800'
                          : 'text-slate-700 hover:bg-slate-50'
                      }`}
                    >
                      <Icon className="h-4 w-4 text-emerald-700" />
                      <span>{acc.label}</span>
                    </button>
                  );
                })}
              </div>
            )}
          </div>

          <button
            type="button"
            onClick={logout}
            title="Terminar sessão"
            className={`inline-flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-semibold transition ${
              dark
                ? 'bg-slate-800 text-slate-300 hover:bg-red-900/60 hover:text-red-200'
                : 'bg-slate-100 text-slate-700 hover:bg-red-50 hover:text-red-700'
            }`}
          >
            <LogOut className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">Sair</span>
          </button>
        </div>
      </div>
    </header>
  );
};
