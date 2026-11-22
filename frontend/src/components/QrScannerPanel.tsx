import React, { useEffect, useRef, useState } from 'react';
import { Html5Qrcode } from 'html5-qrcode';
import { Camera, CameraOff, QrCode, ShieldCheck } from 'lucide-react';

interface QrScannerPanelProps {
  onValidate: (cardIdentifier: string) => Promise<void>;
  busy?: boolean;
  suggestedCards?: string[];
}

export const QrScannerPanel: React.FC<QrScannerPanelProps> = ({
  onValidate,
  busy = false,
  suggestedCards = ['MOB-000001', 'MOB-000002', 'MOB-000003', 'MOB-000004'],
}) => {
  const [manualInput, setManualInput] = useState('MOB-000001');
  const [cameraOn, setCameraOn] = useState(false);
  const [cameraError, setCameraError] = useState<string | null>(null);
  const scannerRef = useRef<Html5Qrcode | null>(null);
  const regionId = 'dalalink-qr-reader';

  const stopCamera = async () => {
    if (scannerRef.current) {
      try {
        await scannerRef.current.stop();
        scannerRef.current.clear();
      } catch {
        // ignore stop errors
      }
      scannerRef.current = null;
    }
    setCameraOn(false);
  };

  useEffect(() => {
    return () => {
      stopCamera();
    };
  }, []);

  const startCamera = async () => {
    setCameraError(null);
    try {
      setCameraOn(true);
      await new Promise((r) => setTimeout(r, 120));
      const qr = new Html5Qrcode(regionId);
      scannerRef.current = qr;
      await qr.start(
        { facingMode: 'environment' },
        { fps: 8, qrbox: { width: 220, height: 220 } },
        async (decodedText) => {
          await stopCamera();
          setManualInput(decodedText);
          await onValidate(decodedText);
        },
        () => {
          // ignore per-frame scan miss
        }
      );
    } catch {
      setCameraOn(false);
      setCameraError(
        'Câmara indisponível neste dispositivo. Utilize o código do cartão ou a leitura rápida abaixo.'
      );
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!manualInput.trim()) return;
    await onValidate(manualInput.trim());
  };

  return (
    <div className="space-y-4 rounded-2xl border border-slate-700 bg-slate-800/80 p-4">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <QrCode className="h-5 w-5 text-emerald-400" />
          <h3 className="text-sm font-bold text-white">Validação de Cartão QR</h3>
        </div>
        <button
          type="button"
          onClick={cameraOn ? stopCamera : startCamera}
          className="inline-flex items-center gap-1.5 rounded-xl bg-slate-700 px-3 py-2 text-xs font-semibold text-white transition hover:bg-slate-600"
        >
          {cameraOn ? <CameraOff className="h-4 w-4" /> : <Camera className="h-4 w-4" />}
          {cameraOn ? 'Fechar Câmara' : 'Ler com Câmara'}
        </button>
      </div>

      {cameraOn && (
        <div
          id={regionId}
          className="overflow-hidden rounded-xl border border-emerald-500/40 bg-black"
        />
      )}

      {cameraError && (
        <p className="rounded-lg bg-amber-500/15 px-3 py-2 text-xs text-amber-200">{cameraError}</p>
      )}

      <form onSubmit={handleSubmit} className="flex flex-col gap-2 sm:flex-row">
        <input
          id="driver-qr-input"
          type="text"
          value={manualInput}
          onChange={(e) => setManualInput(e.target.value)}
          placeholder="Código (ex: MOB-000001) ou token QR..."
          className="font-mono-code flex-1 rounded-xl border border-slate-600 bg-slate-900 px-3.5 py-3 text-sm text-white placeholder-slate-400 focus:border-emerald-400 focus:outline-none"
        />
        <button
          id="driver-validate-qr-btn"
          type="submit"
          disabled={busy || !manualInput.trim()}
          className="inline-flex items-center justify-center gap-2 rounded-xl bg-emerald-600 px-5 py-3 text-sm font-bold text-white transition hover:bg-emerald-500 disabled:opacity-50"
        >
          <ShieldCheck className="h-5 w-5" />
          {busy ? 'A validar...' : 'Validar Embarque'}
        </button>
      </form>

      <div className="space-y-1.5">
        <p className="text-[11px] font-medium uppercase tracking-wider text-slate-400">
          Cartões de demonstração rápida (Luanda)
        </p>
        <div className="flex flex-wrap gap-2">
          {suggestedCards.map((code) => (
            <button
              key={code}
              type="button"
              onClick={() => setManualInput(code)}
              className={`font-mono-code rounded-lg px-2.5 py-1.5 text-xs font-semibold transition ${
                manualInput === code
                  ? 'bg-emerald-600 text-white'
                  : 'bg-slate-900 text-slate-300 hover:bg-slate-700'
              }`}
            >
              {code}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
};
