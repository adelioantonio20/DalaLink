import React, { useState } from 'react';
import { QRCodeSVG } from 'qrcode.react';
import { Check, Copy, CreditCard, ShieldAlert, Wifi } from 'lucide-react';
import { formatAOA } from '../services/api';
import { TransportCardDTO } from '../types';

interface Props {
  card: TransportCardDTO;
  compact?: boolean;
}

export const MobilityCardVisual: React.FC<Props> = ({ card, compact = false }) => {
  const [copied, setCopied] = useState(false);

  const copyToken = async () => {
    try {
      await navigator.clipboard.writeText(card.qr_token);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      // ignore clipboard errors
    }
  };

  const isActive = card.status === 'ACTIVE';

  return (
    <div className="overflow-hidden rounded-2xl bg-slate-900 text-white shadow-lg">
      <div className="flex flex-col gap-5 p-5 sm:flex-row sm:items-center sm:justify-between">
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <CreditCard className="h-5 w-5 text-emerald-400" />
            <span className="text-xs font-semibold uppercase tracking-widest text-emerald-300">
              Cartão de Mobilidade DalaLink
            </span>
          </div>

          <div>
            <p className="text-xs text-slate-400">Saldo Disponível (Servidor)</p>
            <p className="text-3xl font-extrabold tracking-tight text-white">
              {formatAOA(card.balance_aoa)}
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-3 pt-1">
            <span className="font-mono-code rounded-lg bg-slate-800 px-3 py-1 text-sm font-semibold tracking-wider text-emerald-300">
              {card.card_code}
            </span>
            <span
              className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-semibold ${
                isActive ? 'bg-emerald-500/20 text-emerald-300' : 'bg-red-500/20 text-red-300'
              }`}
            >
              {!isActive && <ShieldAlert className="h-3.5 w-3.5" />}
              {isActive ? 'ATIVO' : card.status}
            </span>
            <span className="inline-flex items-center gap-1 text-xs text-slate-300">
              <Wifi className="h-3.5 w-3.5 rotate-90 text-emerald-400" />
              {card.nfc_uid ? `${card.card_technology} • ${card.nfc_uid}` : 'QR • NFC Ready'}
            </span>
          </div>

          <div className="pt-1 text-xs text-slate-300">
            Titular: <span className="font-semibold text-white">{card.passenger_name}</span>
          </div>

          {!compact && (
            <button
              type="button"
              onClick={copyToken}
              className="inline-flex items-center gap-1.5 rounded-lg bg-slate-800 px-3 py-1.5 text-xs font-medium text-slate-200 transition hover:bg-slate-700"
            >
              {copied ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
              {copied ? 'Credencial QR copiada' : 'Copiar credencial QR assinada'}
            </button>
          )}
        </div>

        <div className="flex flex-col items-center rounded-xl bg-white p-3 text-slate-900 shadow-inner">
          <QRCodeSVG value={card.qr_token} size={compact ? 104 : 132} level="M" />
          <span className="font-mono-code mt-1.5 text-[10px] font-semibold text-slate-600">
            {card.card_code}
          </span>
        </div>
      </div>
      <div className="border-t border-slate-800 bg-slate-950/60 px-5 py-2 text-[11px] text-slate-400">
        Credencial segura de acesso à carteira digital. O saldo nunca é armazenado no cartão ou dispositivo.
      </div>
    </div>
  );
};
