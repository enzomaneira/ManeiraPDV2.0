// Onde o item aparece (Keeta / iFood) e preço próprio em cada plataforma.
// Só aparece quando o cardápio NÃO é o mesmo nas duas plataformas.

import { PLATFORMS } from './platforms';

export function PlatformDot({ platform, className = '' }) {
  return <span className={`inline-block w-2.5 h-2.5 rounded-full border ${platform.dot} ${className}`} aria-hidden="true" />;
}

// Etiquetas "Só no iFood" / "Fora das duas" nas listas
export function PlatformBadge({ entity }) {
  const onKeeta = entity.onKeeta !== false;
  const onIfood = entity.onIfood !== false;
  if (onKeeta && onIfood) return null;
  const text = onKeeta ? 'Só na Keeta' : onIfood ? 'Só no iFood' : 'Fora das plataformas';
  const style = onKeeta ? 'bg-[#fff6c2] text-yellow-900' : onIfood ? 'bg-red-50 text-[#c81624]' : 'bg-slate-100 text-slate-500';
  return <span className={`text-[10px] px-2 py-0.5 rounded-full font-bold ${style}`}>{text}</span>;
}

export default function PlatformFields({ form, onChange, withPrices = true, basePrice, idPrefix = 'platform', compact = false }) {
  return (
    <div className={`grid gap-2 ${compact ? 'grid-cols-1 sm:grid-cols-2' : 'grid-cols-1 sm:grid-cols-2 gap-3'}`}>
      {PLATFORMS.map(platform => {
        const on = form[platform.on];
        return (
          <div key={platform.key} className={`rounded-xl border ${compact ? 'p-2' : 'p-3'} ${on ? platform.active : 'border-slate-200 bg-slate-50'}`}>
            <label className="flex items-center gap-2 text-sm font-bold text-slate-700 cursor-pointer">
              <input type="checkbox" checked={on} onChange={e => onChange({ [platform.on]: e.target.checked })} />
              <PlatformDot platform={platform} />
              {compact ? platform.name : `Vender ${platform.at}`}
            </label>
            {withPrices && on && (
              <label className="mt-2 flex items-center gap-1.5 text-xs text-slate-500" htmlFor={`${idPrefix}-${platform.key}`}>
                {compact ? 'R$' : `Preço ${platform.at} (R$)`}
                <input id={`${idPrefix}-${platform.key}`} type="number" step="0.01" min="0" value={form[platform.price]}
                  onChange={e => onChange({ [platform.price]: e.target.value })}
                  placeholder={basePrice !== undefined && basePrice !== '' ? `${basePrice} (normal)` : 'Preço normal'}
                  className="flex-1 min-w-0 w-24 px-2 py-1.5 border border-slate-200 rounded-lg bg-white text-sm text-slate-700" />
              </label>
            )}
          </div>
        );
      })}
    </div>
  );
}
