import { useState } from 'react';
import {
  Plus, Search, Edit3, Copy, Trash2, ArrowUp, ArrowDown, Utensils, Loader2, FolderPlus, PackageOpen, Eye, EyeOff,
} from 'lucide-react';
import { formatCurrency } from '../../utils/formatters';
import { isProduct } from './menuUtils';
import { PlatformBadge } from './PlatformFields';

// Botão Disponível / Esgotado usado nas listas do cardápio.
export function StatusToggle({ available, busy, onClick, labelOn = 'Disponível', labelOff = 'Esgotado', title }) {
  return (
    <button type="button" onClick={onClick} disabled={busy} aria-pressed={!available}
      title={title || (available ? 'Clique para marcar como esgotado' : 'Clique para voltar a vender')}
      className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-bold border transition-colors disabled:opacity-60 shrink-0 ${available ? 'bg-green-50 text-green-700 border-green-200 hover:bg-green-100' : 'bg-red-50 text-red-600 border-red-200 hover:bg-red-100'}`}>
      {busy ? <Loader2 className="w-3 h-3 animate-spin" /> : <span className={`w-2 h-2 rounded-full ${available ? 'bg-green-500' : 'bg-red-500'}`} />}
      {available ? labelOn : labelOff}
    </button>
  );
}

function IconButton({ title, onClick, disabled, danger, children }) {
  return (
    <button type="button" onClick={onClick} disabled={disabled} title={title} aria-label={title}
      className={`p-2 rounded-lg text-slate-400 disabled:opacity-30 ${danger ? 'hover:text-red-600 hover:bg-red-50' : 'hover:text-indigo-600 hover:bg-indigo-50'}`}>
      {children}
    </button>
  );
}

// Aba "Produtos": cada categoria é um bloco com seus produtos, como no
// gestor de cardápio do iFood e dos PDVs de delivery.
export default function ProductsTab({
  categories, items, optionGroups, loading, busyId, reordering, sameMenu = true,
  onNewCategory, onEditCategory, onDeleteCategory, onToggleCategory, onMoveCategory,
  onNewProduct, onEditProduct, onDuplicateProduct, onDeleteProduct, onToggleProduct, onMoveProduct,
}) {
  const [search, setSearch] = useState('');
  const term = search.trim().toLowerCase();
  const groupName = Object.fromEntries(optionGroups.map(group => [group.id, group.name]));
  const productsOf = (categoryId) => items
    .filter(item => isProduct(item) && item.categoryId === categoryId)
    .sort((a, b) => (a.index ?? 0) - (b.index ?? 0));
  const matches = (item) => !term || [item.name, item.description, item.externalCode].some(value => (value || '').toLowerCase().includes(term));

  if (loading) {
    return <div className="flex items-center justify-center py-20 text-slate-400"><Loader2 className="w-8 h-8 animate-spin mr-3" />Carregando cardápio…</div>;
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[220px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <input type="search" value={search} onChange={e => setSearch(e.target.value)} placeholder="Buscar produto pelo nome"
            aria-label="Buscar produto" className="w-full pl-9 pr-3 py-2.5 bg-white border border-slate-200 rounded-xl text-sm focus:ring-2 focus:ring-indigo-400 focus:outline-none" />
        </div>
        <button type="button" onClick={onNewCategory}
          className="flex items-center gap-2 px-4 py-2.5 rounded-xl font-bold text-sm bg-white border border-slate-200 text-slate-700 hover:bg-slate-50 shadow-sm">
          <FolderPlus className="w-4 h-4" />Nova categoria
        </button>
      </div>

      {categories.length === 0 && (
        <div className="bg-white rounded-2xl border border-dashed border-slate-300 p-10 text-center text-slate-500">
          <PackageOpen className="w-12 h-12 mx-auto mb-3 text-slate-300" />
          <p className="font-bold text-slate-700">Seu cardápio está vazio</p>
          <p className="text-sm mt-1">Comece criando uma categoria (ex.: Hambúrgueres, Bebidas) e depois adicione os produtos dela.</p>
          <button type="button" onClick={onNewCategory} className="mt-4 px-4 py-2 rounded-xl font-bold text-sm bg-indigo-600 text-white hover:bg-indigo-700">Criar primeira categoria</button>
        </div>
      )}

      {categories.map((category, position) => {
        const products = productsOf(category.id);
        const visible = products.filter(matches);
        if (term && visible.length === 0) return null;
        const paused = category.status !== 'AVAILABLE';
        return (
          <section key={category.id} className={`bg-white rounded-2xl border shadow-sm overflow-hidden ${paused ? 'border-red-200' : 'border-slate-200'}`} aria-label={`Categoria ${category.name}`}>
            <header className="flex flex-wrap items-center gap-3 px-5 py-3 bg-slate-50 border-b border-slate-200">
              <div className="flex-1 min-w-[180px]">
                <div className="flex items-center gap-2">
                  <h3 className="font-bold text-lg text-slate-800">{category.name}</h3>
                  <span className="text-xs font-bold text-slate-400">{products.length} {products.length === 1 ? 'produto' : 'produtos'}</span>
                  {paused && <span className="text-[10px] px-2 py-0.5 rounded-full bg-red-100 text-red-700 font-bold">Categoria pausada</span>}
                  {!sameMenu && <PlatformBadge entity={category} />}
                </div>
                {category.description && <p className="text-xs text-slate-500">{category.description}</p>}
              </div>
              <button type="button" onClick={() => onToggleCategory(category)} disabled={busyId === `cat-${category.id}`}
                title={paused ? 'Voltar a mostrar a categoria nas plataformas' : 'Esconder na hora todos os produtos desta categoria nas plataformas'}
                className="flex items-center gap-1.5 text-xs font-bold px-3 py-1.5 rounded-lg border border-slate-200 bg-white text-slate-600 hover:bg-slate-100 disabled:opacity-50">
                {paused ? <Eye className="w-3.5 h-3.5" /> : <EyeOff className="w-3.5 h-3.5" />}{paused ? 'Mostrar categoria' : 'Pausar categoria'}
              </button>
              <div className="flex items-center">
                <IconButton title="Mover categoria para cima" onClick={() => onMoveCategory(position, -1)} disabled={position === 0 || reordering || Boolean(term)}><ArrowUp className="w-4 h-4" /></IconButton>
                <IconButton title="Mover categoria para baixo" onClick={() => onMoveCategory(position, 1)} disabled={position === categories.length - 1 || reordering || Boolean(term)}><ArrowDown className="w-4 h-4" /></IconButton>
                <IconButton title="Editar categoria" onClick={() => onEditCategory(category)}><Edit3 className="w-4 h-4" /></IconButton>
                <IconButton title="Excluir categoria" danger onClick={() => onDeleteCategory(category, products.length)}><Trash2 className="w-4 h-4" /></IconButton>
              </div>
            </header>

            {products.length === 0 && (
              <p className="px-5 py-4 text-sm text-slate-400">Nenhum produto nesta categoria ainda.</p>
            )}
            <ul className="divide-y divide-slate-100">
              {visible.map((item) => {
                const index = products.indexOf(item);
                const available = item.status === 'AVAILABLE';
                const chips = (item.optionGroupsId || []).map(id => groupName[id]).filter(Boolean);
                return (
                  <li key={item.id} className={`flex flex-wrap items-center gap-3 px-5 py-3 ${available ? '' : 'bg-slate-50/70'}`}>
                    <div className={`w-14 h-14 rounded-xl bg-indigo-50 flex items-center justify-center shrink-0 overflow-hidden ${available ? '' : 'grayscale opacity-60'}`}>
                      {item.imageUrl
                        ? <img src={item.imageUrl} alt="" className="w-full h-full object-cover" onError={e => { e.currentTarget.style.display = 'none'; }} />
                        : <Utensils className="w-6 h-6 text-indigo-300" />}
                    </div>
                    <button type="button" onClick={() => onEditProduct(item)} className="flex-1 min-w-[200px] text-left group">
                      <p className={`font-bold group-hover:text-indigo-700 ${available ? 'text-slate-800' : 'text-slate-400'}`}>
                        {item.name}{!sameMenu && <span className="ml-2 align-middle"><PlatformBadge entity={item} /></span>}
                      </p>
                      {item.description && item.description !== item.name && <p className="text-xs text-slate-500 line-clamp-1">{item.description}</p>}
                      {chips.length > 0 && (
                        <div className="flex flex-wrap gap-1 mt-1">
                          {chips.map(name => <span key={name} className="text-[10px] px-2 py-0.5 rounded-full bg-purple-50 text-purple-700 font-bold">+ {name}</span>)}
                        </div>
                      )}
                    </button>
                    <div className="text-right w-24 shrink-0">
                      <span className="font-extrabold text-indigo-600 tabular-nums">{formatCurrency(item.price)}</span>
                      {item.originalPrice > item.price && <span className="block text-xs text-slate-400 line-through">{formatCurrency(item.originalPrice)}</span>}
                      {!sameMenu && item.onKeeta !== false && item.keetaPrice != null && <span className="block text-[11px] text-slate-500 tabular-nums">Keeta {formatCurrency(item.keetaPrice)}</span>}
                      {!sameMenu && item.onIfood !== false && item.ifoodPrice != null && <span className="block text-[11px] text-slate-500 tabular-nums">iFood {formatCurrency(item.ifoodPrice)}</span>}
                    </div>
                    <StatusToggle available={available} busy={busyId === item.id} onClick={() => onToggleProduct(item)} />
                    <div className="flex items-center">
                      <IconButton title="Mover para cima" onClick={() => onMoveProduct(products, index, -1)} disabled={index === 0 || reordering || Boolean(term)}><ArrowUp className="w-4 h-4" /></IconButton>
                      <IconButton title="Mover para baixo" onClick={() => onMoveProduct(products, index, 1)} disabled={index === products.length - 1 || reordering || Boolean(term)}><ArrowDown className="w-4 h-4" /></IconButton>
                      <IconButton title="Editar produto" onClick={() => onEditProduct(item)}><Edit3 className="w-4 h-4" /></IconButton>
                      <IconButton title="Duplicar produto" onClick={() => onDuplicateProduct(item)}><Copy className="w-4 h-4" /></IconButton>
                      <IconButton title="Excluir produto" danger onClick={() => onDeleteProduct(item)}><Trash2 className="w-4 h-4" /></IconButton>
                    </div>
                  </li>
                );
              })}
            </ul>
            {!term && (
              <button type="button" onClick={() => onNewProduct(category.id)}
                className="w-full flex items-center justify-center gap-2 px-5 py-3 text-sm font-bold text-indigo-600 hover:bg-indigo-50 border-t border-slate-100">
                <Plus className="w-4 h-4" />Adicionar produto em {category.name}
              </button>
            )}
          </section>
        );
      })}

      {term && categories.every(category => productsOf(category.id).filter(matches).length === 0) && (
        <div className="text-center py-12 text-slate-400">
          <p className="font-bold text-slate-500">Nenhum produto encontrado para “{search.trim()}”.</p>
          <button type="button" onClick={() => setSearch('')} className="mt-2 text-sm font-bold text-indigo-600 hover:underline">Limpar busca</button>
        </div>
      )}
    </div>
  );
}
