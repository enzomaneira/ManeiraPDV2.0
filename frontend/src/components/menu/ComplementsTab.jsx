import { Plus, Edit3, Trash2, Loader2, ListPlus } from 'lucide-react';
import { formatCurrency } from '../../utils/formatters';
import { groupRuleText, isProduct } from './menuUtils';
import { StatusToggle } from './ProductsTab';
import { PlatformBadge } from './PlatformFields';

// Aba "Complementos": cada grupo (Molhos, Adicionais, Bebida do Combo…) com a
// regra de escolha, as opções e os produtos que o usam.
export default function ComplementsTab({ optionGroups, items, loading, busyId, onNewGroup, onEditGroup, onDeleteGroup, onToggleItem, sameMenu = true }) {
  const itemById = Object.fromEntries(items.map(item => [item.id, item]));
  const productsUsing = (groupId) => items.filter(item => isProduct(item) && (item.optionGroupsId || []).includes(groupId));

  if (loading) {
    return <div className="flex items-center justify-center py-20 text-slate-400"><Loader2 className="w-8 h-8 animate-spin mr-3" />Carregando complementos…</div>;
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <p className="flex-1 min-w-[240px] text-sm text-slate-500">
          Um grupo reúne as opções que o cliente pode escolher (ex.: <b>Molhos</b>, <b>Adicionais</b>). Crie o grupo uma vez e use em quantos produtos quiser.
        </p>
        <button type="button" onClick={onNewGroup} className="flex items-center gap-2 px-4 py-2.5 rounded-xl font-bold text-sm bg-purple-600 text-white hover:bg-purple-700 shadow-sm">
          <Plus className="w-4 h-4" />Novo grupo de complementos
        </button>
      </div>

      {optionGroups.length === 0 && (
        <div className="bg-white rounded-2xl border border-dashed border-slate-300 p-10 text-center text-slate-500">
          <ListPlus className="w-12 h-12 mx-auto mb-3 text-slate-300" />
          <p className="font-bold text-slate-700">Nenhum grupo de complementos</p>
          <p className="text-sm mt-1">Exemplos: "Escolha o molho" (opcional, até 2) ou "Ponto da carne" (obrigatório, escolha 1).</p>
        </div>
      )}

      {optionGroups.map(group => {
        const used = productsUsing(group.id);
        return (
          <section key={group.id} className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden" aria-label={`Grupo ${group.name}`}>
            <header className="flex flex-wrap items-center gap-3 px-5 py-3 bg-slate-50 border-b border-slate-200">
              <div className="flex-1 min-w-[200px]">
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="font-bold text-lg text-slate-800">{group.name}</h3>
                  <span className={`text-[11px] px-2 py-0.5 rounded-full font-bold ${group.minPermitted > 0 ? 'bg-amber-100 text-amber-800' : 'bg-slate-200 text-slate-700'}`}>{groupRuleText(group)}</span>
                </div>
                {group.description && <p className="text-xs text-slate-500">{group.description}</p>}
              </div>
              <button type="button" onClick={() => onEditGroup(group)} className="flex items-center gap-1.5 text-xs font-bold px-3 py-1.5 rounded-lg border border-slate-200 bg-white text-slate-600 hover:bg-slate-100"><Edit3 className="w-3.5 h-3.5" />Editar</button>
              <button type="button" onClick={() => onDeleteGroup(group, used.length)} className="p-2 rounded-lg text-slate-400 hover:text-red-600 hover:bg-red-50" title="Excluir grupo" aria-label={`Excluir grupo ${group.name}`}><Trash2 className="w-4 h-4" /></button>
            </header>
            <ul className="divide-y divide-slate-100">
              {(group.options || []).length === 0 && <li className="px-5 py-3 text-sm text-red-600">Grupo sem opções: ele não aparece nas plataformas até você adicionar pelo menos uma.</li>}
              {(group.options || []).map(option => {
                const item = itemById[option.itemId];
                const available = (item?.status || 'AVAILABLE') === 'AVAILABLE' && option.status === 'AVAILABLE';
                const shared = item && isProduct(item);
                return (
                  <li key={option.id} className="flex flex-wrap items-center gap-3 px-5 py-2.5">
                    <span className={`flex-1 min-w-[160px] font-medium ${available ? 'text-slate-700' : 'text-slate-400'}`}>
                      {item?.name || option.name}
                      {shared && <span className="ml-2 text-[10px] px-1.5 py-0.5 rounded bg-indigo-50 text-indigo-600 font-bold" title="Este item também é vendido sozinho no cardápio">também é produto</span>}
                      {!sameMenu && <span className="ml-2"><PlatformBadge entity={option} /></span>}
                    </span>
                    {option.maxPermitted > 1 && <span className="text-[10px] px-1.5 py-0.5 rounded bg-purple-50 text-purple-700 font-bold" title="O cliente pode escolher esta opção mais de uma vez">até {option.maxPermitted}x</span>}
                    <span className="w-20 text-right text-sm font-bold tabular-nums text-slate-600">{option.price > 0 ? `+ ${formatCurrency(option.price)}` : 'Grátis'}</span>
                    {item && (
                      <StatusToggle available={available} busy={busyId === item.id} onClick={() => onToggleItem(item)}
                        title={shared ? 'Também pausa/volta o produto no cardápio' : undefined} />
                    )}
                  </li>
                );
              })}
            </ul>
            <div className="px-5 py-2.5 border-t border-slate-100 bg-slate-50/60 text-xs text-slate-500">
              {used.length === 0
                ? <span className="text-amber-700 font-bold">Não está em nenhum produto: clique em Editar para escolher os produtos.</span>
                : <>Usado em {used.length} {used.length === 1 ? 'produto' : 'produtos'}: {used.map(item => item.name).join(', ')}</>}
            </div>
          </section>
        );
      })}
    </div>
  );
}
