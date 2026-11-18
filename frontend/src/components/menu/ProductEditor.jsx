import { useEffect, useState } from 'react';
import { X, Save, Loader2, ChevronDown, ChevronRight, Plus, Clock, Trash2 } from 'lucide-react';
import PhotoField from './PhotoField';
import { menuService, availabilityService } from '../../services/api';
import { formatCurrency } from '../../utils/formatters';
import {
  inputClass, labelClass, getErrorMessage, groupRuleText, WEEK_DAYS, DAY_CODES, brasiliaRangeToUtcHours, brasiliaLabels,
} from './menuUtils';

const EMPTY_RULE = { name: '', days: [...DAY_CODES], start: '11:00', end: '15:00' };

function Section({ number, title, hint, children }) {
  return (
    <section className="space-y-3">
      <div>
        <h4 className="font-bold text-slate-800 flex items-center gap-2">
          <span className="w-6 h-6 rounded-full bg-indigo-100 text-indigo-700 text-xs flex items-center justify-center">{number}</span>{title}
        </h4>
        {hint && <p className="text-xs text-slate-500 mt-0.5 ml-8">{hint}</p>}
      </div>
      <div className="ml-8 space-y-3">{children}</div>
    </section>
  );
}

// Cadastro/edição de um produto, num formulário só. Produto novo continua aberto
// depois de salvo para escolher complementos e horários.
export default function ProductEditor({
  product, draft, categories, optionGroups, availabilities, onClose, onChanged, onCreated, onCreateGroup, showMessage,
}) {
  const [current, setCurrent] = useState(product);
  const isNew = !current;
  const [form, setForm] = useState(() => {
    const source = product || draft || {};
    return {
      name: source.name || '',
      description: source.description || '',
      categoryId: source.categoryId ?? categories[0]?.id ?? '',
      imageUrl: source.imageUrl || '',
      price: source.price != null ? String(source.price) : '',
      originalPrice: source.originalPrice != null && source.originalPrice > source.price ? String(source.originalPrice) : '',
      externalCode: product ? product.externalCode || '' : '',
    };
  });
  // Grupos escolhidos antes de o produto existir (aplicados ao criar).
  const [pendingGroups, setPendingGroups] = useState(() => (draft?.optionGroupsId || []));
  const [saving, setSaving] = useState(false);
  const [linkingId, setLinkingId] = useState(null);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [rule, setRule] = useState(EMPTY_RULE);
  const [ruleSaving, setRuleSaving] = useState(false);

  // O produto pode ter mudado no backend (vínculos); pega a versão nova.
  useEffect(() => { if (product) setCurrent(product); }, [product]);

  const set = (changes) => setForm(prev => ({ ...prev, ...changes }));
  const linkedGroups = isNew ? pendingGroups : (current.optionGroupsId || []);
  const linkedRules = current?.availabilityId || [];

  const handleSave = async (e) => {
    e.preventDefault();
    const price = parseFloat(String(form.price).replace(',', '.'));
    const original = form.originalPrice === '' ? price : parseFloat(String(form.originalPrice).replace(',', '.'));
    if (!form.name.trim()) { showMessage('error', 'Dê um nome ao produto.'); return; }
    if (!form.categoryId) { showMessage('error', 'Escolha a categoria do produto.'); return; }
    if (isNaN(price) || price < 0) { showMessage('error', 'Informe o preço de venda.'); return; }
    if (isNaN(original) || original < price) { showMessage('error', 'O preço "de" precisa ser maior que o preço de venda (ou fique em branco).'); return; }
    setSaving(true);
    const payload = {
      name: form.name.trim(), description: form.description.trim(), categoryId: Number(form.categoryId),
      imageUrl: form.imageUrl.trim(), price, originalPrice: original, externalCode: form.externalCode.trim(),
    };
    try {
      if (isNew) {
        const { data } = await menuService.create(payload);
        for (const groupId of pendingGroups) await menuService.linkOptionGroup(data.id, groupId);
        // Recarrega antes de trocar para o produto salvo: o editor reabre já com ele.
        await onChanged();
        onCreated(data.id);
        showMessage('success', 'Produto criado. Agora você pode escolher horários e criar grupos para ele.');
      } else {
        await menuService.update(current.id, payload);
        await onChanged();
        showMessage('success', 'Produto atualizado.');
        onClose();
      }
    } catch (error) {
      showMessage('error', getErrorMessage(error, 'Não foi possível salvar o produto.'));
    } finally {
      setSaving(false);
    }
  };

  const toggleGroup = async (groupId) => {
    const linked = linkedGroups.includes(groupId);
    if (isNew) {
      setPendingGroups(prev => (linked ? prev.filter(id => id !== groupId) : [...prev, groupId]));
      return;
    }
    setLinkingId(groupId);
    try {
      if (linked) await menuService.unlinkOptionGroup(current.id, groupId);
      else await menuService.linkOptionGroup(current.id, groupId);
      setCurrent(prev => ({ ...prev, optionGroupsId: linked ? prev.optionGroupsId.filter(id => id !== groupId) : [...prev.optionGroupsId, groupId] }));
      await onChanged();
    } catch (error) {
      showMessage('error', getErrorMessage(error, 'Não foi possível alterar os complementos.'));
    } finally {
      setLinkingId(null);
    }
  };

  const toggleRule = async (ruleId) => {
    const linked = linkedRules.includes(ruleId);
    try {
      if (linked) await menuService.unlinkAvailability(current.id, ruleId);
      else await menuService.linkAvailability(current.id, ruleId);
      setCurrent(prev => ({ ...prev, availabilityId: linked ? prev.availabilityId.filter(id => id !== ruleId) : [...(prev.availabilityId || []), ruleId] }));
      await onChanged();
    } catch (error) {
      showMessage('error', getErrorMessage(error, 'Não foi possível alterar o horário do produto.'));
    }
  };

  const createRule = async () => {
    if (!rule.name.trim()) { showMessage('error', 'Dê um nome ao horário (ex.: "Almoço").'); return; }
    if (rule.days.length === 0) { showMessage('error', 'Escolha pelo menos um dia.'); return; }
    if (rule.start === rule.end) { showMessage('error', 'Início e fim não podem ser iguais.'); return; }
    setRuleSaving(true);
    try {
      const { data } = await availabilityService.create({ name: rule.name.trim(), hours: brasiliaRangeToUtcHours(rule.days, rule.start, rule.end) });
      await menuService.linkAvailability(current.id, data.id);
      setCurrent(prev => ({ ...prev, availabilityId: [...(prev.availabilityId || []), data.id] }));
      setRule(EMPTY_RULE);
      await onChanged();
      showMessage('success', 'Horário criado e aplicado a este produto.');
    } catch (error) {
      showMessage('error', getErrorMessage(error, 'Não foi possível criar o horário.'));
    } finally {
      setRuleSaving(false);
    }
  };

  const deleteRule = async (availability) => {
    if (!confirm(`Excluir o horário "${availability.name}"? Ele sai de todos os produtos que o usam.`)) return;
    try { await availabilityService.delete(availability.id); await onChanged(); setCurrent(prev => ({ ...prev, availabilityId: (prev.availabilityId || []).filter(id => id !== availability.id) })); }
    catch (error) { showMessage('error', getErrorMessage(error, 'Não foi possível excluir o horário.')); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4" role="dialog" aria-modal="true" aria-label={isNew ? 'Novo produto' : `Editar ${current.name}`}>
      <form onSubmit={handleSave} className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[92vh] flex flex-col">
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200">
          <h3 className="font-bold text-lg text-slate-800">{isNew ? 'Novo produto' : `Editar: ${current.name}`}</h3>
          <button type="button" onClick={onClose} className="p-2 rounded-lg hover:bg-slate-100 text-slate-400" aria-label="Fechar"><X className="w-5 h-5" /></button>
        </div>

        <div className="overflow-y-auto px-6 py-5 space-y-7">
          <Section number="1" title="Informações" hint="Como o produto aparece para o cliente.">
            <div><label className={labelClass} htmlFor="product-name">Nome *</label>
              <input id="product-name" className={inputClass} maxLength={150} value={form.name} onChange={e => set({ name: e.target.value })} placeholder="Ex.: X-Burguer" autoFocus /></div>
            <div><label className={labelClass} htmlFor="product-description">Descrição</label>
              <textarea id="product-description" className={inputClass + ' resize-none'} rows={2} maxLength={500} value={form.description} onChange={e => set({ description: e.target.value })} placeholder="Ex.: Pão brioche, blend 160g, cheddar e molho da casa" /></div>
            <div><label className={labelClass} htmlFor="product-category">Categoria *</label>
              <select id="product-category" className={inputClass} value={form.categoryId} onChange={e => set({ categoryId: e.target.value ? Number(e.target.value) : '' })}>
                {categories.map(category => <option key={category.id} value={category.id}>{category.name}</option>)}
              </select></div>
          </Section>

          <Section number="2" title="Foto" hint="Envie a foto do computador (o PDV ajusta e guarda no Cloudflare) ou cole um link.">
            <PhotoField value={form.imageUrl} onChange={imageUrl => set({ imageUrl })} productName={form.name} />
          </Section>

          <Section number="3" title="Preço">
            <div className="grid grid-cols-2 gap-3">
              <div><label className={labelClass} htmlFor="product-price">Preço de venda (R$) *</label>
                <input id="product-price" type="number" step="0.01" min="0" className={inputClass + ' font-bold'} value={form.price} onChange={e => set({ price: e.target.value })} /></div>
              <div><label className={labelClass} htmlFor="product-original">Preço "de" (opcional)</label>
                <input id="product-original" type="number" step="0.01" min="0" className={inputClass} value={form.originalPrice} onChange={e => set({ originalPrice: e.target.value })} placeholder="Sem promoção" /></div>
            </div>
            <p className="text-xs text-slate-500">Preencha o preço "de" só para promoções: o app mostra <span className="line-through">{form.originalPrice ? formatCurrency(Number(form.originalPrice) || 0) : 'R$ 40,00'}</span> por {form.price ? formatCurrency(Number(form.price) || 0) : 'R$ 32,00'}.</p>
          </Section>

          <Section number="4" title="Complementos" hint="Grupos que o cliente escolhe ao pedir este produto (molhos, adicionais, bebida do combo…).">
            {optionGroups.length === 0 && <p className="text-sm text-slate-500">Nenhum grupo de complementos criado ainda.</p>}
            <div className="space-y-2">
              {optionGroups.map(group => {
                const checked = linkedGroups.includes(group.id);
                return (
                  <label key={group.id} className={`flex items-start gap-3 p-3 rounded-xl border cursor-pointer ${checked ? 'border-purple-300 bg-purple-50' : 'border-slate-200 hover:bg-slate-50'}`}>
                    <input type="checkbox" className="mt-1" checked={checked} disabled={linkingId === group.id} onChange={() => toggleGroup(group.id)} />
                    <span className="flex-1">
                      <span className="font-bold text-slate-800">{group.name}</span>
                      <span className="ml-2 text-[11px] px-2 py-0.5 rounded-full bg-white border border-slate-200 text-slate-600 font-bold">{groupRuleText(group)}</span>
                      <span className="block text-xs text-slate-500 mt-0.5">{(group.options || []).map(option => option.name).join(', ') || 'Sem opções ainda'}</span>
                    </span>
                    {linkingId === group.id && <Loader2 className="w-4 h-4 animate-spin text-purple-500" />}
                  </label>
                );
              })}
            </div>
            <button type="button" onClick={() => onCreateGroup(current)} disabled={isNew}
              className="flex items-center gap-1.5 text-sm font-bold text-purple-700 hover:text-purple-900 disabled:text-slate-400">
              <Plus className="w-4 h-4" />Criar novo grupo de complementos{isNew ? ' (salve o produto primeiro)' : ''}
            </button>
          </Section>

          <section>
            <button type="button" onClick={() => setShowAdvanced(value => !value)} className="flex items-center gap-1.5 text-sm font-bold text-slate-500 hover:text-slate-700">
              {showAdvanced ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}Avançado: horários específicos e código do produto
            </button>
            {showAdvanced && (
              <div className="mt-3 ml-6 space-y-4">
                <div>
                  <label className={labelClass} htmlFor="product-code">Código do produto (PDV)</label>
                  <input id="product-code" className={inputClass + ' font-mono'} maxLength={100} value={form.externalCode} onChange={e => set({ externalCode: e.target.value })} placeholder="Gerado automaticamente" />
                  <p className="text-xs text-slate-400 mt-1">É o código que a Keeta usa para reconhecer o produto. Só mude se souber o que está fazendo.</p>
                </div>
                <div>
                  <p className={labelClass + ' flex items-center gap-1.5'}><Clock className="w-4 h-4" />Horários em que o produto aparece (Brasília)</p>
                  <p className="text-xs text-slate-500 mb-2">Sem nenhum horário marcado, o produto segue o horário de funcionamento da loja.</p>
                  {isNew ? <p className="text-xs text-slate-400">Salve o produto para definir horários.</p> : (
                    <>
                      <div className="space-y-2">
                        {availabilities.map(availability => (
                          <div key={availability.id} className="flex items-center gap-2 text-sm">
                            <input type="checkbox" checked={linkedRules.includes(availability.id)} onChange={() => toggleRule(availability.id)} aria-label={`Usar horário ${availability.name}`} />
                            <span className="font-bold text-slate-700">{availability.name}</span>
                            <span className="text-xs text-slate-500">{brasiliaLabels(availability.hours).join(' · ')}</span>
                            <button type="button" onClick={() => deleteRule(availability)} className="ml-auto p-1 text-slate-300 hover:text-red-600" title="Excluir horário" aria-label={`Excluir horário ${availability.name}`}><Trash2 className="w-3.5 h-3.5" /></button>
                          </div>
                        ))}
                      </div>
                      <div className="mt-3 p-3 rounded-xl bg-slate-50 border border-slate-200 space-y-2">
                        <p className="text-xs font-bold text-slate-600">Novo horário</p>
                        <input className={inputClass} placeholder="Nome (ex.: Almoço)" value={rule.name} onChange={e => setRule({ ...rule, name: e.target.value })} aria-label="Nome do horário" />
                        <div className="flex flex-wrap gap-1.5" role="group" aria-label="Dias do horário">
                          {WEEK_DAYS.map(([code, label]) => {
                            const on = rule.days.includes(code);
                            return <button key={code} type="button" aria-pressed={on} onClick={() => setRule(prev => ({ ...prev, days: prev.days.includes(code) ? prev.days.filter(day => day !== code) : DAY_CODES.filter(day => day === code || prev.days.includes(day)) }))}
                              className={`px-2.5 py-1 rounded-lg text-xs font-bold border ${on ? 'bg-teal-600 text-white border-teal-600' : 'bg-white text-slate-500 border-slate-200'}`}>{label}</button>;
                          })}
                        </div>
                        <div className="flex flex-wrap items-center gap-2 text-sm text-slate-600">
                          <label className="flex items-center gap-1.5">Das <input type="time" className="px-2 py-1.5 border border-slate-200 rounded-lg" value={rule.start} onChange={e => setRule({ ...rule, start: e.target.value })} /></label>
                          <label className="flex items-center gap-1.5">às <input type="time" className="px-2 py-1.5 border border-slate-200 rounded-lg" value={rule.end} onChange={e => setRule({ ...rule, end: e.target.value })} /></label>
                          <button type="button" onClick={createRule} disabled={ruleSaving} className="ml-auto px-3 py-1.5 rounded-lg bg-teal-600 text-white text-xs font-bold hover:bg-teal-700 disabled:opacity-50">{ruleSaving ? 'Criando…' : 'Criar e aplicar'}</button>
                        </div>
                      </div>
                    </>
                  )}
                </div>
              </div>
            )}
          </section>
        </div>

        <div className="flex gap-3 px-6 py-4 border-t border-slate-200">
          <button type="button" onClick={onClose} className="flex-1 py-2.5 font-bold rounded-xl border border-slate-200 text-slate-600 hover:bg-slate-50">{isNew ? 'Cancelar' : 'Fechar'}</button>
          <button type="submit" disabled={saving} className={`flex-1 py-2.5 font-bold rounded-xl flex items-center justify-center gap-2 ${saving ? 'bg-slate-300 cursor-not-allowed' : 'bg-indigo-600 hover:bg-indigo-700 text-white shadow-md'}`}>
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}{saving ? 'Salvando…' : isNew ? 'Criar produto' : 'Salvar alterações'}
          </button>
        </div>
      </form>
    </div>
  );
}
