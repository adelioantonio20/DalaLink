import React, { useState } from 'react';
import {
  ArrowRight,
  Car,
  ClipboardCheck,
  Clock,
  LayoutDashboard,
  MapPin,
  Navigation,
  ShieldCheck,
  User as UserIcon,
} from 'lucide-react';
import { useAuth } from '../../contexts/AuthContext';

const PORTAL_CARDS = [
  {
    title: 'Ambiente do Passageiro',
    subtitle: 'Saiba como está a sua via antes de sair de casa.',
    detail: 'Consulte Gamek → Maianga, compare paragens próximas, declare intenção de viajar e confirme presença.',
    email: 'passageiro@dalalink.ao',
    icon: UserIcon,
    accent: 'bg-emerald-700',
  },
  {
    title: 'Ambiente do Motorista',
    subtitle: 'Saiba onde existe procura antes de escolher a sua próxima via.',
    detail: 'Consulte vias e destinos mais procurados, mapa de calor de procura e declare a sua disponibilidade.',
    email: 'motorista@dalalink.ao',
    icon: Car,
    accent: 'bg-slate-900',
  },
  {
    title: 'Recolha de Campo (Operacional)',
    subtitle: 'Observação presencial nas paragens de Luanda.',
    detail: 'Registe táxis observados, passageiros à espera e estado do trânsito em tempo real.',
    email: 'campo@dalalink.ao',
    icon: ClipboardCheck,
    accent: 'bg-amber-700',
  },
  {
    title: 'Painel Administrativo',
    subtitle: 'Gestão geográfica, qualidade de dados e analítica.',
    detail: 'Valide observações, configure limites de procura/expiração, gira paragens/vias e consulte históricos.',
    email: 'admin@dalalink.ao',
    icon: LayoutDashboard,
    accent: 'bg-teal-800',
  },
];

export const AuthPortal: React.FC = () => {
  const { login, register } = useAuth();
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [email, setEmail] = useState('passageiro@dalalink.ao');
  const [password, setPassword] = useState('dalalink123');
  const [fullName, setFullName] = useState('');
  const [phone, setPhone] = useState('+244923');
  const [role, setRole] = useState<'PASSENGER' | 'DRIVER'>('PASSENGER');
  const [licenseNumber, setLicenseNumber] = useState('');
  const [nationalId, setNationalId] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const handleQuickDemo = async (demoEmail: string) => {
    setError(null);
    setSubmitting(true);
    try {
      await login(demoEmail, 'dalalink123');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao iniciar sessão.');
    } finally {
      setSubmitting(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      if (mode === 'login') {
        await login(email, password);
      } else {
        await register({
          full_name: fullName,
          email,
          phone,
          password,
          role,
          license_number: role === 'DRIVER' ? licenseNumber : undefined,
          national_id: role === 'DRIVER' ? nationalId : undefined,
        });
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ocorreu um erro na autenticação.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50">
      <div className="mx-auto max-w-6xl px-4 py-8 sm:py-12">
        <div className="mb-10 flex flex-col justify-between gap-4 border-b border-slate-200 pb-6 sm:flex-row sm:items-end">
          <div>
            <div className="mb-3 inline-flex items-center gap-2.5">
              <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-emerald-700 text-white shadow-sm">
                <Navigation className="h-6 w-6" />
              </div>
              <div>
                <h1 className="text-2xl font-extrabold tracking-tight text-slate-900 sm:text-3xl">
                  DalaLink
                </h1>
                <p className="text-xs font-semibold uppercase tracking-widest text-emerald-700">
                  Inteligência e Intermediação de Informação • Luanda
                </p>
              </div>
            </div>
            <p className="max-w-2xl text-sm text-slate-600">
              Mais informação, melhores decisões e uma distribuição mais eficiente entre passageiros e
              táxis em Luanda — com dados geograficamente contextualizados, origem transparente e controlo
              de actualidade em tempo real.
            </p>
          </div>
          <div className="flex flex-wrap gap-2.5 text-xs font-medium text-slate-600">
            <span className="inline-flex items-center gap-1.5 rounded-lg bg-white px-3 py-1.5 shadow-xs ring-1 ring-slate-200">
              <MapPin className="h-3.5 w-3.5 text-emerald-700" /> Luanda, Angola
            </span>
            <span className="inline-flex items-center gap-1.5 rounded-lg bg-white px-3 py-1.5 shadow-xs ring-1 ring-slate-200">
              <Clock className="h-3.5 w-3.5 text-amber-600" /> Validade Temporal
            </span>
            <span className="inline-flex items-center gap-1.5 rounded-lg bg-white px-3 py-1.5 shadow-xs ring-1 ring-slate-200">
              <ShieldCheck className="h-3.5 w-3.5 text-emerald-700" /> Dados Auditáveis
            </span>
          </div>
        </div>

        <div className="grid gap-8 lg:grid-cols-12">
          <section className="space-y-4 lg:col-span-7">
            <div>
              <h2 className="text-lg font-bold text-slate-900">
                Aceder aos Ambientes da Plataforma
              </h2>
              <p className="mt-1 text-xs text-slate-500">
                Cenário em destaque: consultar disponibilidade na via <strong>Gamek → Maianga</strong>,
                comparar com a paragem alternativa <strong>Rocha Gamek</strong> e validar observações de campo.
              </p>
            </div>

            <div className="grid gap-3.5 sm:grid-cols-2">
              {PORTAL_CARDS.map((card) => {
                const Icon = card.icon;
                return (
                  <button
                    key={card.email}
                    type="button"
                    disabled={submitting}
                    onClick={() => handleQuickDemo(card.email)}
                    className="group flex flex-col justify-between rounded-2xl border border-slate-200 bg-white p-5 text-left shadow-xs transition hover:-translate-y-0.5 hover:border-emerald-600 hover:shadow-md disabled:opacity-60"
                  >
                    <div>
                      <div className="mb-3 flex items-center justify-between">
                        <div
                          className={`flex h-10 w-10 items-center justify-center rounded-xl text-white ${card.accent}`}
                        >
                          <Icon className="h-5 w-5" />
                        </div>
                        <ArrowRight className="h-4 w-4 text-slate-400 transition group-hover:translate-x-0.5 group-hover:text-emerald-700" />
                      </div>
                      <h3 className="text-base font-bold text-slate-900">{card.title}</h3>
                      <p className="mt-1 text-xs font-semibold text-emerald-700">{card.subtitle}</p>
                      <p className="mt-2 text-xs leading-relaxed text-slate-500">{card.detail}</p>
                    </div>
                    <div className="mt-4 border-t border-slate-100 pt-2.5 text-[11px] font-medium text-slate-400">
                      Entrar imediatamente →
                    </div>
                  </button>
                );
              })}
            </div>

            <div className="rounded-2xl border border-emerald-200 bg-emerald-50/70 p-4 text-xs text-emerald-950">
              <strong>Transparência dos dados:</strong> A plataforma distingue sempre informação{' '}
              <em>Declarada por utilizadores</em>, <em>Confirmada na paragem</em> e{' '}
              <em>Observada em campo</em>, sinalizando dados desactualizados e exibindo claramente quando
              existe informação insuficiente.
            </div>
          </section>

          <section className="lg:col-span-5">
            <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
              <div className="mb-5 grid grid-cols-2 rounded-xl bg-slate-100 p-1">
                <button
                  type="button"
                  onClick={() => {
                    setMode('login');
                    setError(null);
                  }}
                  className={`rounded-lg py-2 text-xs font-bold transition ${
                    mode === 'login' ? 'bg-white text-slate-900 shadow-xs' : 'text-slate-600'
                  }`}
                >
                  Iniciar Sessão
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setMode('register');
                    setError(null);
                  }}
                  className={`rounded-lg py-2 text-xs font-bold transition ${
                    mode === 'register' ? 'bg-white text-slate-900 shadow-xs' : 'text-slate-600'
                  }`}
                >
                  Criar Conta
                </button>
              </div>

              {error && (
                <div className="mb-4 rounded-xl border border-red-200 bg-red-50 px-3.5 py-2.5 text-xs font-medium text-red-700">
                  {error}
                </div>
              )}

              <form onSubmit={handleSubmit} className="space-y-3.5">
                {mode === 'register' && (
                  <>
                    <div>
                      <label className="mb-1 block text-xs font-semibold text-slate-700">Perfil</label>
                      <select
                        value={role}
                        onChange={(e) => setRole(e.target.value as 'PASSENGER' | 'DRIVER')}
                        className="w-full rounded-xl border border-slate-300 bg-white px-3 py-2.5 text-sm focus:border-emerald-600 focus:outline-none"
                      >
                        <option value="PASSENGER">Passageiro</option>
                        <option value="DRIVER">Motorista / Taxista</option>
                      </select>
                    </div>
                    <div>
                      <label className="mb-1 block text-xs font-semibold text-slate-700">Nome Completo</label>
                      <input
                        type="text"
                        required
                        value={fullName}
                        onChange={(e) => setFullName(e.target.value)}
                        placeholder="Ex.: António Manuel"
                        className="w-full rounded-xl border border-slate-300 px-3 py-2.5 text-sm"
                      />
                    </div>
                    <div>
                      <label className="mb-1 block text-xs font-semibold text-slate-700">Telefone (+244)</label>
                      <input
                        type="text"
                        required
                        value={phone}
                        onChange={(e) => setPhone(e.target.value)}
                        placeholder="+244923000999"
                        className="w-full rounded-xl border border-slate-300 px-3 py-2.5 text-sm"
                      />
                    </div>
                  </>
                )}

                <div>
                  <label className="mb-1 block text-xs font-semibold text-slate-700">Email</label>
                  <input
                    type="email"
                    required
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className="w-full rounded-xl border border-slate-300 px-3 py-2.5 text-sm"
                  />
                </div>

                <div>
                  <label className="mb-1 block text-xs font-semibold text-slate-700">Palavra-passe</label>
                  <input
                    type="password"
                    required
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="w-full rounded-xl border border-slate-300 px-3 py-2.5 text-sm"
                  />
                </div>

                {mode === 'register' && role === 'DRIVER' && (
                  <div className="grid grid-cols-2 gap-2">
                    <input
                      type="text"
                      required
                      value={licenseNumber}
                      onChange={(e) => setLicenseNumber(e.target.value)}
                      placeholder="Carta Condução"
                      className="rounded-xl border border-slate-300 px-3 py-2 text-xs"
                    />
                    <input
                      type="text"
                      required
                      value={nationalId}
                      onChange={(e) => setNationalId(e.target.value)}
                      placeholder="Nº Bilhete Identidade"
                      className="rounded-xl border border-slate-300 px-3 py-2 text-xs"
                    />
                  </div>
                )}

                <button
                  type="submit"
                  disabled={submitting}
                  className="w-full rounded-xl bg-emerald-700 py-3 text-sm font-bold text-white shadow-sm transition hover:bg-emerald-800 disabled:opacity-50"
                >
                  {submitting ? 'A processar...' : mode === 'login' ? 'Entrar' : 'Registar e Entrar'}
                </button>
              </form>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
};
