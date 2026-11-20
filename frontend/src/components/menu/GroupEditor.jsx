import { useState } from 'react';
import { X, Save, Loader2, Plus, Trash2, ArrowUp, ArrowDown } from 'lucide-react';
import { optionGroupService } from '../../services/api';
import { formatCurrency } from '../../utils/formatters';
import { inputClass, labelClass, getErrorMessage, groupRuleText, isProduct } from './menuUtils';
import PlatformFields from './PlatformFields';
import { platformForm, platformPayload } from './platforms';

let draftKey = 0;
const newKey = () => `novo-${++draftKey}`;

// Cria/edita um grupo de complementos: regra de escolha, opções (cada uma com
// o preço cobrado NESTE grupo) e os produtos que usam o grupo. Salva tudo e
// a publicação nas plataformas fica para o botão Publicar.
export default function GroupEditor({ group, items, categories, presetProductIds = [], onClose, onChanged, showMessage, sameMenu = true }) {
  const isNew = !group;
  const itemById = Object.fromEntries(items.map(item => [item.id, item]));
  const [form, setForm] = useState({
    name: group?.name || '',
    description: group?.description || '',
    required: (group?.minPermitted || 0) > 0,
    min: Math.max(group?.minPermitted || 1, 1),
    max: group?.maxPermitted || 1,
  });
  const [options, setOptions] = useState(() => (group?.options || []).map(option => ({
    key: `op-${option.id}`, id: option.id, itemId: option.itemId, name: itemById[option.itemId]?.name || option.name, price: String(option.price ?? 0),
    maxQty: String(option.maxPermitted || 1), ...platformForm(option),
  })));
  const [productIds, setProductIds] = useState(() => new Set(
    group ? items.filter(item => isProduct(item) && (item.optionGroupsId || []).includes(group.id)).map(item => item.id) : presetProductIds,
  ));
  const [newOption, setNewOption] = useState({ mode: 'new', name: '', price: '', itemId: '' });
  const [saving, setSaving] = useState(false);

  const set = (changes) => setForm(prev => ({ ...prev, ...changes }));
  const minPermitted = form.required ? Number(form.min) || 1 : 0;
  const maxPermitted = Math.max(Number(form.max) || 1, minPermitted, 1);
  // Quantas vezes cada opção pode ser escolhida (1 = não repete). O cliente só
  // consegue escolher, no total, a soma desses limites.
  const optionLimit = (option) => Math.max(1, Math.floor(Number(option.maxQty) || 1));
  const reachable = options.reduce((sum, option) => sum + optionLimit(option), 0);
  const allowsRepeat = options.some(option => optionLimit(option) > 1);
  const usedItemIds = new Set(options.map(option => option.itemId).filter(Boolean));
  const pickable = [...items].filter(item => !usedItemIds.has(item.id))
    .sort((a, b) => Number(b.isOptionItem) - Number(a.isOptionItem) || a.name.localeCompare(b.name));

  const addOption = () => {
    if (newOption.mode === 'existing') {
      const item = itemById[Number(newOption.itemId)];
      if (!item) { showMessage('error', 'Escolha o item.'); return; }
      setOptions(prev => [...prev, { key: newKey(), itemId: item.id, name: item.name, price: newOption.price || '0', maxQty: '1', ...platformForm() }]);
    } else {
      if (!newOption.name.trim()) { showMessage('error', 'Digite o nome da opção (ex.: Bacon extra).'); return; }
      setOptions(prev => [...prev, { key: newKey(), itemId: null, name: newOption.name.trim(), price: newOption.price || '0', maxQty: '1', ...platformForm() }]);
    }
    setNewOption({ mode: newOption.mode, name: '', price: '', itemId: '' });
  };
  const updateOption = (key, changes) => setOptions(prev => prev.map(option => (option.key === key ? { ...option, ...changes } : option)));
  const moveOption = (index, direction) => setOptions(prev => {
    const next = [...prev]; [next[index], next[index + direction]] = [next[index + direction], next[index]]; return next;
  });
  const toggleProduct = (id) => setProductIds(prev => { const next = new Set(prev); next.has(id) ? next.delete(id) : next.add(id); return next; });

  const handleSave = async (e) => {
    e.preventDefault();
    if (!form.name.trim()) { showMessage('error', 'Dê um nome ao grupo (ex.: Molhos).'); return; }
    if (options.length === 0) { showMessage('error', 'Adicione pelo menos uma opção ao grupo.'); return; }
    if (minPermitted > reachable) { showMessage('error', `O cliente precisa escolher ${minPermitted}, mas as opções só somam ${reachable} escolha${reachable === 1 ? '' : 's'}. Aumente o "até" de alguma opção ou o número de opções.`); return; }
    if (options.some(option => optionLimit(option) > maxPermitted)) { showMessage('error', `Uma opção não pode ser escolhida mais vezes que o máximo do grupo (${maxPermitted}).`); return; }
    const prices = options.map(option => parseFloat(String(option.price).replace(',', '.')));
    if (prices.some(price => isNaN(price) || price < 0)) { showMessage('error', 'Confira os preços das opções.'); return; }
    let platforms;
    try { platforms = options.map(option => (sameMenu ? {} : platformPayload(option, true))); }
    catch (error) { showMessage('error', `${error.message} Veja as opções do grupo.`); return; }
    setSaving(true);
    try {
      const payload = { name: form.name.trim(), description: form.description.trim(), minPermitted, maxPermitted, status: 'AVAILABLE' };
      const groupId = isNew
        ? (await optionGroupService.create(payload, { sync: false })).data.id
        : (await optionGroupService.update(group.id, payload, { sync: false }), group.id);

      const keep = new Set(options.filter(option => option.id).map(option => option.id));
      for (const old of group?.options || []) {
        if (!keep.has(old.id)) await optionGroupService.deleteOption(groupId, old.id, { sync: false });
      }
      for (const [index, option] of options.entries()) {
        const body = { name: option.name, price: prices[index], index, status: 'AVAILABLE', maxPermitted: optionLimit(option), ...platforms[index] };
        if (option.id) await optionGroupService.updateOption(groupId, option.id, body, { sync: false });
        else await optionGroupService.createOption(groupId, { ...body, itemId: option.itemId }, { sync: false });
      }
      // Última chamada: vincula os produtos ao grupo.
      await optionGroupService.setItems(groupId, [...productIds]);
      await onChanged();
      showMessage('success', isNew ? 'Grupo criado.' : 'Grupo atualizado.');
      onClose();
    } catch (error) {
      showMessage('error', getErrorMessage(error, 'Não foi possível salvar o grupo.'));
      await onChanged();
    } finally {
      setSaving(false);
    }
  };

  const productsByCategory = categories.map(category => ({
    category, products: items.filter(item => isProduct(item) && item.categoryId === category.id).sort((a, b) => (a.index ?? 0) - (b.index ?? 0)),
  })).filter(entry => entry.products.length > 0);

  return (
    <div className="fixed inset-0 z-[55] flex items-center justify-center bg-black/40 backdrop-blur-sm p-4" role="dialog" aria-modal="true" aria-label={isNew ? 'Novo grupo de complementos' : `Editar grupo ${group.name}`}>
      <form onSubmit={handleSave} className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[92vh] flex flex-col">
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200">
          <h3 className="font-bold text-lg text-slate-800">{isNew ? 'Novo grupo de complementos' : `Editar grupo: ${group.name}`}</h3>
          <button type="button" onClick={onClose} className="p-2 rounded-lg hover:bg-slate-100 text-slate-400" aria-label="Fechar"><X className="w-5 h-5" /></button>
        </div>
        <div className="overflow-y-auto px-6 py-5 space-y-6">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div><label className={labelClass} htmlFor="group-name">Nome do grupo *</label>
              <input id="group-name" className={inputClass} maxLength={150} value={form.name} onChange={e => set({ name: e.target.value })} placeholder="Ex.: Molhos" autoFocus /></div>
            <div><label className={labelClass} htmlFor="group-description">Texto para o cliente</label>
              <input id="group-description" className={inputClass} maxLength={500} value={form.description} onChange={e => set({ description: e.target.value })} placeholder="Ex.: Escolha até 2 molhos" /></div>
          </div>

          <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 space-y-3">
            <p className="font-bold text-slate-700 text-sm">O cliente precisa escolher?</p>
            <div className="flex flex-wrap gap-2">
              <button type="button" aria-pressed={!form.required} onClick={() => set({ required: false })} className={`px-3 py-1.5 rounded-lg text-sm font-bold border ${!form.required ? 'bg-purple-600 text-white border-purple-600' : 'bg-white text-slate-600 border-slate-200'}`}>Não, é opcional</button>
              <button type="button" aria-pressed={form.required} onClick={() => set({ required: true })} className={`px-3 py-1.5 rounded-lg text-sm font-bold border ${form.required ? 'bg-purple-600 text-white border-purple-600' : 'bg-white text-slate-600 border-slate-200'}`}>Sim, é obrigatório</button>
            </div>
            <div className="flex flex-wrap items-center gap-2 text-sm text-slate-600">
              {form.required && <label className="flex items-center gap-1.5">Escolher no mínimo <input type="number" min="1" className="w-16 px-2 py-1.5 border border-slate-200 rounded-lg" value={form.min} onChange={e => set({ min: e.target.value })} /></label>}
              <label className="flex items-center gap-1.5">{form.required ? 'e no máximo' : 'Pode escolher até'} <input type="number" min="1" className="w-16 px-2 py-1.5 border border-slate-200 rounded-lg" value={form.max} onChange={e => set({ max: e.target.value })} /></label>
              <span className="text-xs font-bold px-2 py-0.5 rounded-full bg-white border border-slate-200">{groupRuleText({ minPermitted, maxPermitted })}{allowsRepeat ? ' · pode repetir' : ''}</span>
            </div>
            {options.length > 0 && maxPermitted > reachable && (
              <p className="text-xs text-amber-700">
                Com as opções de agora o cliente só consegue escolher {reachable}. Para deixar repetir a mesma opção, aumente o “até” dela abaixo.
              </p>
            )}
          </div>

          <div className="space-y-2">
            <p className={labelClass}>Opções do grupo</p>
            {options.length === 0 && <p className="text-sm text-slate-400">Nenhuma opção ainda. Adicione abaixo.</p>}
            {options.map((option, index) => {
              const item = option.itemId ? itemById[option.itemId] : null;
              return (
                <div key={option.key} className="flex flex-wrap items-center gap-2 p-2 rounded-xl border border-slate-200">
                  <div className="flex flex-col">
                    <button type="button" onClick={() => moveOption(index, -1)} disabled={index === 0} className="p-0.5 text-slate-300 hover:text-indigo-600 disabled:opacity-30" aria-label="Subir opção"><ArrowUp className="w-3.5 h-3.5" /></button>
                    <button type="button" onClick={() => moveOption(index, 1)} disabled={index === options.length - 1} className="p-0.5 text-slate-300 hover:text-indigo-600 disabled:opacity-30" aria-label="Descer opção"><ArrowDown className="w-3.5 h-3.5" /></button>
                  </div>
                  <input className={inputClass + ' flex-1 min-w-[160px]'} value={option.name} onChange={e => updateOption(option.key, { name: e.target.value })} disabled={Boolean(item && isProduct(item))} aria-label="Nome da opção" />
                  <label className="flex items-center gap-1 text-sm text-slate-500">+ R$
                    <input type="number" step="0.01" min="0" className="w-24 px-2 py-2 border border-slate-200 rounded-lg" value={option.price} onChange={e => updateOption(option.key, { price: e.target.value })} aria-label={`Preço de ${option.name}`} />
                  </label>
                  <label className="flex items-center gap-1 text-sm text-slate-500" title="Quantas vezes o cliente pode escolher esta mesma opção">até
                    <input type="number" min="1" max={maxPermitted} step="1" className="w-14 px-2 py-2 border border-slate-200 rounded-lg" value={option.maxQty}
                      onChange={e => updateOption(option.key, { maxQty: e.target.value })} aria-label={`Quantas vezes ${option.name} pode ser escolhida`} />
                    x
                  </label>
                  {item && isProduct(item) && <span className="text-[10px] px-1.5 py-0.5 rounded bg-indigo-50 text-indigo-600 font-bold" title={`Vendido sozinho por ${formatCurrency(item.price)}`}>produto do cardápio</span>}
                  <button type="button" onClick={() => setOptions(prev => prev.filter(entry => entry.key !== option.key))} className="p-2 text-slate-300 hover:text-red-600" aria-label={`Remover ${option.name}`}><Trash2 className="w-4 h-4" /></button>
                  {!sameMenu && (
                    <div className="basis-full pl-6">
                      <PlatformFields form={option} onChange={changes => updateOption(option.key, changes)} basePrice={option.price} idPrefix={`option-${option.key}`} compact />
                    </div>
                  )}
                </div>
              );
            })}
            <div className="p-3 rounded-xl bg-purple-50 border border-purple-200 space-y-2">
              <div className="flex flex-wrap gap-3 text-xs font-bold text-purple-800">
                <label className="flex items-center gap-1.5"><input type="radio" checked={newOption.mode === 'new'} onChange={() => setNewOption({ ...newOption, mode: 'new' })} />Nova opção</label>
                <label className="flex items-center gap-1.5"><input type="radio" checked={newOption.mode === 'existing'} onChange={() => setNewOption({ ...newOption, mode: 'existing' })} />Usar item que já existe (ex.: uma bebida do cardápio)</label>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                {newOption.mode === 'new'
                  ? <input className={inputClass + ' flex-1 min-w-[160px]'} placeholder="Nome (ex.: Bacon extra)" value={newOption.name} onChange={e => setNewOption({ ...newOption, name: e.target.value })} aria-label="Nome da nova opção" />
                  : <select className={inputClass + ' flex-1 min-w-[160px]'} value={newOption.itemId} onChange={e => setNewOption({ ...newOption, itemId: e.target.value })} aria-label="Item existente">
                      <option value="">Escolha o item…</option>
                      {pickable.map(item => <option key={item.id} value={item.id}>{item.isOptionItem ? 'Complemento' : 'Produto'}: {item.name}</option>)}
                    </select>}
                <label className="flex items-center gap-1 text-sm text-slate-600">+ R$
                  <input type="number" step="0.01" min="0" className="w-24 px-2 py-2 border border-slate-200 rounded-lg bg-white" placeholder="0,00" value={newOption.price} onChange={e => setNewOption({ ...newOption, price: e.target.value })} aria-label="Preço da nova opção" />
                </label>
                <button type="button" onClick={addOption} className="flex items-center gap-1 px-3 py-2 rounded-lg bg-purple-600 text-white text-sm font-bold hover:bg-purple-700"><Plus className="w-4 h-4" />Adicionar</button>
              </div>
              <p className="text-[11px] text-purple-800/80">O preço aqui é o valor somado ao produto. Deixe 0 para opções grátis.</p>
            </div>
          </div>

          <div>
            <p className={labelClass}>Em quais produtos este grupo aparece?</p>
            {productsByCategory.length === 0 && <p className="text-sm text-slate-400">Cadastre produtos primeiro.</p>}
            <div className="space-y-3">
              {productsByCategory.map(({ category, products }) => (
                <div key={category.id}>
                  <p className="text-xs font-bold text-slate-400 uppercase tracking-wide mb-1">{category.name}</p>
                  <div className="flex flex-wrap gap-2">
                    {products.map(item => {
                      const on = productIds.has(item.id);
                      return (
                        <button key={item.id} type="button" aria-pressed={on} onClick={() => toggleProduct(item.id)}
                          className={`px-3 py-1.5 rounded-full text-xs font-bold border ${on ? 'bg-indigo-600 text-white border-indigo-600' : 'bg-white text-slate-600 border-slate-200 hover:border-indigo-300'}`}>
                          {on ? '✓ ' : ''}{item.name}
                        </button>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
        <div className="flex gap-3 px-6 py-4 border-t border-slate-200">
          <button type="button" onClick={onClose} className="flex-1 py-2.5 font-bold rounded-xl border border-slate-200 text-slate-600 hover:bg-slate-50">Cancelar</button>
          <button type="submit" disabled={saving} className={`flex-1 py-2.5 font-bold rounded-xl flex items-center justify-center gap-2 ${saving ? 'bg-slate-300 cursor-not-allowed' : 'bg-purple-600 hover:bg-purple-700 text-white shadow-md'}`}>
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}{saving ? 'Salvando…' : 'Salvar grupo'}
          </button>
        </div>
      </form>
    </div>
  );
}
