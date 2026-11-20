import { Power, Loader2 } from 'lucide-react';

// Abrir/fechar a loja em cada delivery conectado (Keeta, iFood), no topo do PDV.
const DOT = { keeta: 'bg-[#ffd100] border-[#e6bc00]', ifood: 'bg-[#ea1d2c] border-[#c81624]' };

function untilText(iso) {
  if (!iso) return '';
  const date = new Date(iso);
  if (isNaN(date)) return '';
  return ` até ${date.toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })}`;
}

export default function StoreStatusControls({ platforms, loadingKey, onToggle }) {
  const linked = platforms.filter(platform => platform.linked);
  if (linked.length === 0) {
    return <span className="text-xs font-bold text-slate-400 px-3 py-2 rounded-full border border-dashed border-slate-300">Nenhum delivery conectado</span>;
  }
  return (
    <div className="flex items-center gap-2" role="group" aria-label="Loja aberta ou fechada em cada delivery">
      {linked.map(platform => {
        const busy = loadingKey === platform.key;
        const unknown = platform.isOpen === undefined || platform.isOpen === null;
        const open = platform.isOpen === true;
        const title = unknown
          ? (platform.error || `Não foi possível ler o status no ${platform.name}. Clique para tentar abrir.`)
          : open ? `Aberta no ${platform.name}. Clique para fechar.`
            : `Fechada no ${platform.name}${untilText(platform.closedUntil)}. Clique para abrir.`;
        return (
          <button key={platform.key} type="button" onClick={() => onToggle(platform)} disabled={Boolean(loadingKey)} title={title}
            aria-label={`${platform.name}: ${unknown ? 'status desconhecido' : open ? 'aberta' : 'fechada'}`}
            className={`flex items-center gap-2 pl-3 pr-4 py-2 rounded-full font-bold text-sm transition-all shadow-sm border disabled:cursor-not-allowed ${busy ? 'opacity-70' : 'active:scale-95'} ${
              unknown ? 'bg-slate-50 text-slate-500 border-slate-200 hover:bg-slate-100'
                : open ? 'bg-green-50 text-green-700 border-green-200 hover:bg-green-100'
                  : 'bg-red-50 text-red-700 border-red-200 hover:bg-red-100'}`}>
            <span className={`w-2.5 h-2.5 rounded-full border ${DOT[platform.key]}`} aria-hidden="true" />
            {platform.name}
            <span className="flex items-center gap-1 text-xs">
              {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Power className="w-3.5 h-3.5" />}
              {busy ? '…' : unknown ? '?' : open ? 'ABERTA' : 'FECHADA'}
            </span>
          </button>
        );
      })}
    </div>
  );
}
