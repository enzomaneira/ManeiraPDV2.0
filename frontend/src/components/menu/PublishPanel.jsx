import { Send, Loader2, CheckCircle2, CircleAlert, Link2Off, Layers, Split } from 'lucide-react';
import { PlatformDot } from './PlatformFields';
import { PLATFORMS } from './platforms';

const BUTTON = {
  keeta: 'bg-[#ffd100] hover:bg-[#f5c800] text-slate-900 border-[#e6bc00]',
  ifood: 'bg-[#ea1d2c] hover:bg-[#d11a27] text-white border-[#c81624]',
};

function when(iso) {
  if (!iso) return null;
  const date = new Date(iso);
  if (isNaN(date)) return null;
  return date.toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
}

function PlatformRow({ platform, status, busy, onPublish }) {
  const linked = status?.linked && status?.configured !== false;
  const pending = status?.pending;
  const last = when(status?.publishedAt);
  let state;
  if (!status) state = <span className="text-slate-400">Carregando…</span>;
  else if (!linked) state = <span className="flex items-center gap-1 text-slate-500"><Link2Off className="w-3.5 h-3.5" />Loja não conectada (veja em Configurações)</span>;
  else if (pending) state = <span className="flex items-center gap-1 text-amber-700 font-bold"><CircleAlert className="w-3.5 h-3.5" />{last ? 'Alterações não publicadas' : 'Ainda não publicado'}</span>;
  else state = <span className="flex items-center gap-1 text-green-700 font-bold"><CheckCircle2 className="w-3.5 h-3.5" />Em dia</span>;

  return (
    <div className={`flex flex-wrap items-center gap-3 p-3 rounded-xl border ${linked && pending ? 'border-amber-200 bg-amber-50/60' : 'border-slate-200 bg-white'}`}>
      <div className="flex-1 min-w-[170px]">
        <p className="font-bold text-slate-800 flex items-center gap-2"><PlatformDot platform={platform} />{platform.name}</p>
        <div className="text-xs mt-0.5">{state}</div>
        {last && <p className="text-[11px] text-slate-400 mt-0.5">Última publicação: {last}</p>}
      </div>
      <button type="button" onClick={onPublish} disabled={!linked || busy}
        className={`flex items-center gap-2 px-4 py-2 rounded-xl font-bold text-sm border shadow-sm disabled:opacity-40 disabled:cursor-not-allowed ${BUTTON[platform.key]}`}>
        {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
        {busy ? 'Publicando…' : `Publicar ${platform.at}`}
      </button>
    </div>
  );
}

// Topo da tela de Cardápio: modo (mesmo cardápio ou por plataforma) e
// publicação manual em cada plataforma.
export default function PublishPanel({ status, publishing, savingMode, onPublish, onToggleSameMenu }) {
  const sameMenu = status?.sameMenu !== false;
  return (
    <section className="bg-white rounded-2xl border border-slate-200 shadow-sm p-4 space-y-3" aria-label="Publicação do cardápio">
      <div className="flex flex-wrap items-start gap-3">
        <div className="flex-1 min-w-[240px]">
          <p className="font-bold text-slate-800">Publicar o cardápio</p>
          <p className="text-xs text-slate-500 mt-0.5">
            As edições ficam guardadas aqui até você publicar. Esgotar, voltar a vender e pausar categoria ou complemento vão na hora.
          </p>
        </div>
        <div className="flex p-1 bg-slate-100 rounded-xl" role="radiogroup" aria-label="Cardápio das plataformas">
          {[[true, 'Mesmo cardápio', <Layers key="i" className="w-4 h-4" />], [false, 'Um para cada', <Split key="i" className="w-4 h-4" />]].map(([value, label, icon]) => (
            <button key={label} type="button" role="radio" aria-checked={sameMenu === value} disabled={savingMode || !status}
              onClick={() => sameMenu !== value && onToggleSameMenu(value)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition-colors disabled:opacity-60 ${sameMenu === value ? 'bg-white text-slate-800 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}>
              {icon}{label}
            </button>
          ))}
        </div>
      </div>
      <p className="text-xs text-slate-600 bg-slate-50 border border-slate-100 rounded-lg px-3 py-2">
        {sameMenu
          ? 'Keeta e iFood recebem o mesmo cardápio, com os mesmos preços.'
          : 'Em cada categoria, produto e complemento você escolhe se aparece na Keeta, no iFood ou nos dois, e pode dar um preço diferente para cada um.'}
      </p>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {PLATFORMS.map(platform => (
          <PlatformRow key={platform.key} platform={platform} status={status?.[platform.key]}
            busy={publishing === platform.key} onPublish={() => onPublish(platform.key)} />
        ))}
      </div>
    </section>
  );
}
