import { useEffect, useRef, useState } from 'react';
import { CheckCircle, AlertCircle, X, Utensils, ListPlus, Save, Loader2 } from 'lucide-react';
import { categoryService, menuService, optionGroupService, availabilityService, menuPublishService } from '../services/api';
import ProductsTab from '../components/menu/ProductsTab';
import ComplementsTab from '../components/menu/ComplementsTab';
import ProductEditor from '../components/menu/ProductEditor';
import GroupEditor from '../components/menu/GroupEditor';
import PublishPanel from '../components/menu/PublishPanel';
import PlatformFields from '../components/menu/PlatformFields';
import { platformForm, platformPayload } from '../components/menu/platforms';
import { inputClass, labelClass, getErrorMessage, isProduct } from '../components/menu/menuUtils';

// Tela de Cardápio organizada como nos gestores de cardápio de delivery
// (iFood, Saipos, Omie…): aba Produtos (categorias com seus produtos) e aba
// Complementos (grupos de opções reutilizáveis).
export default function MenuPage() {
  const [tab, setTab] = useState('products');
  const [categories, setCategories] = useState([]);
  const [items, setItems] = useState([]);
  const [optionGroups, setOptionGroups] = useState([]);
  const [availabilities, setAvailabilities] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState(null);
  const [reordering, setReordering] = useState(false);
  const [publishStatus, setPublishStatus] = useState(null);
  const [publishing, setPublishing] = useState(null); // 'keeta' | 'ifood'
  const [savingMode, setSavingMode] = useState(false);
  const [message, setMessage] = useState(null);
  // Modais
  const [productEditor, setProductEditor] = useState(null); // { id } | { draft }
  const [groupEditor, setGroupEditor] = useState(null);     // { group, presetProductIds }
  const [categoryEditor, setCategoryEditor] = useState(null); // { category } | {}
  const [categoryForm, setCategoryForm] = useState({ name: '', description: '', ...platformForm() });
  const [categorySaving, setCategorySaving] = useState(false);

  const timer = useRef(null);
  const showMessage = (type, text) => {
    clearTimeout(timer.current);
    setMessage({ type, text });
    if (type === 'success') timer.current = setTimeout(() => setMessage(null), 3500);
  };

  // Alterações não publicadas em cada plataforma (não trava a tela se falhar)
  const loadPublishStatus = async () => {
    try { const { data } = await menuPublishService.status(); setPublishStatus(data); } catch { /* mostra "Carregando…" */ }
  };

  const refresh = async () => {
    loadPublishStatus();
    try {
      const [cats, menu, groups, avails] = await Promise.all([
        categoryService.getAll(), menuService.getAll(), optionGroupService.getAll(), availabilityService.getAll(),
      ]);
      setCategories((cats.data || []).sort((a, b) => (a.index ?? 0) - (b.index ?? 0)));
      setItems(menu.data || []);
      setOptionGroups(groups.data || []);
      setAvailabilities(avails.data || []);
    } catch (error) {
      showMessage('error', getErrorMessage(error, 'Não foi possível carregar o cardápio.'));
    } finally {
      setLoading(false);
    }
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { refresh(); }, []);

  // ===== Publicação =====
  const sameMenu = publishStatus?.sameMenu !== false;
  const handlePublish = async (platform) => {
    setPublishing(platform);
    try {
      if (platform === 'keeta') {
        const { data } = await menuPublishService.publishKeeta();
        showMessage('success', data?.message || 'Cardápio publicado na Keeta.');
      } else {
        const { data, status } = await menuPublishService.publishIfood();
        if (status === 207) {
          const details = (data.errors || []).map(error => `• ${error}`).join('\n');
          showMessage('error', `Publicado em parte no iFood: ${data.sent + (data.unchanged || 0)} de ${data.total} produtos em dia.\n${details}`);
        } else {
          const parts = [];
          if (data.sent) parts.push(`${data.sent} ${data.sent === 1 ? 'produto enviado' : 'produtos enviados'}`);
          if (data.unchanged) parts.push(`${data.unchanged} sem mudança`);
          if (data.paused) parts.push(`${data.paused} pausado${data.paused > 1 ? 's' : ''} por ter saído do cardápio`);
          showMessage('success', `Cardápio publicado no iFood${parts.length ? ` (${parts.join(', ')})` : ''}.`);
        }
      }
    } catch (error) {
      showMessage('error', getErrorMessage(error, `Não foi possível publicar ${platform === 'keeta' ? 'na Keeta' : 'no iFood'}.`));
    } finally {
      setPublishing(null);
      loadPublishStatus();
    }
  };
  const toggleSameMenu = async (value) => {
    if (!value && !confirm('Usar um cardápio diferente em cada plataforma?\n\nTudo continua aparecendo nas duas até você mudar. Em cada categoria, produto e complemento vai aparecer onde ele é vendido e o preço em cada plataforma.')) return;
    if (value && !confirm('Voltar a usar o mesmo cardápio nas duas plataformas?\n\nTudo que você escondeu de uma plataforma volta a aparecer nela, com o preço normal (os ajustes ficam guardados se quiser voltar depois).')) return;
    setSavingMode(true);
    try {
      await menuPublishService.setSameMenu(value);
      await loadPublishStatus();
      showMessage('success', value ? 'Agora as duas plataformas usam o mesmo cardápio. Publique para aplicar.' : 'Agora cada plataforma tem seu cardápio. Publique para aplicar.');
    } catch (error) {
      showMessage('error', getErrorMessage(error, 'Não foi possível mudar o modo do cardápio.'));
    } finally { setSavingMode(false); }
  };

  // ===== Categorias =====
  const openCategory = (category) => {
    setCategoryForm({ name: category?.name || '', description: category?.description || '', ...platformForm(category || {}) });
    setCategoryEditor({ category });
  };
  const saveCategory = async (e) => {
    e.preventDefault();
    if (!categoryForm.name.trim()) { showMessage('error', 'Dê um nome à categoria.'); return; }
    setCategorySaving(true);
    try {
      const payload = { name: categoryForm.name.trim(), description: categoryForm.description.trim(), ...(sameMenu ? {} : platformPayload(categoryForm, false)) };
      if (categoryEditor.category) await categoryService.update(categoryEditor.category.id, payload);
      else await categoryService.create(payload);
      await refresh();
      setCategoryEditor(null);
      showMessage('success', categoryEditor.category ? 'Categoria atualizada.' : 'Categoria criada. Agora adicione os produtos dela.');
    } catch (error) {
      showMessage('error', getErrorMessage(error, 'Não foi possível salvar a categoria.'));
    } finally { setCategorySaving(false); }
  };
  const deleteCategory = async (category, count) => {
    const text = count > 0
      ? `Excluir a categoria "${category.name}"?\n\nOs ${count} ${count === 1 ? 'produto' : 'produtos'} dela também serão excluídos. Não dá para desfazer.`
      : `Excluir a categoria "${category.name}"?`;
    if (!confirm(text)) return;
    try { await categoryService.delete(category.id); await refresh(); showMessage('success', 'Categoria excluída.'); }
    catch (error) { showMessage('error', getErrorMessage(error, 'Não foi possível excluir a categoria.')); }
  };
  const toggleCategory = async (category) => {
    const status = category.status === 'AVAILABLE' ? 'UNAVAILABLE' : 'AVAILABLE';
    setBusyId(`cat-${category.id}`);
    try {
      await categoryService.update(category.id, { status });
      await refresh();
      showMessage('success', status === 'AVAILABLE' ? `"${category.name}" voltou para o cardápio.` : `"${category.name}" pausada: os produtos dela saem das plataformas.`);
    } catch (error) { showMessage('error', getErrorMessage(error, 'Não foi possível alterar a categoria.')); }
    finally { setBusyId(null); }
  };

  // Troca a posição com o vizinho e salva a nova ordem (index = posição na lista).
  const move = async (list, position, direction, update) => {
    const target = position + direction;
    if (target < 0 || target >= list.length) return;
    const reordered = [...list];
    [reordered[position], reordered[target]] = [reordered[target], reordered[position]];
    setReordering(true);
    try {
      await Promise.all(reordered.map((entry, index) => (entry.index !== index ? update(entry.id, { index }) : null)));
      await refresh();
    } catch (error) {
      showMessage('error', getErrorMessage(error, 'Não foi possível salvar a nova ordem.'));
    } finally { setReordering(false); }
  };

  // ===== Produtos =====
  const toggleItem = async (item) => {
    const status = item.status === 'AVAILABLE' ? 'UNAVAILABLE' : 'AVAILABLE';
    setBusyId(item.id);
    setItems(prev => prev.map(entry => (entry.id === item.id ? { ...entry, status } : entry)));
    try {
      await menuService.update(item.id, { status });
      showMessage('success', status === 'AVAILABLE' ? `"${item.name}" disponível novamente.` : `"${item.name}" marcado como esgotado.`);
    } catch (error) {
      setItems(prev => prev.map(entry => (entry.id === item.id ? { ...entry, status: item.status } : entry)));
      showMessage('error', getErrorMessage(error, 'Não foi possível alterar o status.'));
    } finally { setBusyId(null); }
  };
  const deleteItem = async (item) => {
    if (!confirm(`Excluir "${item.name}"? Não dá para desfazer.`)) return;
    try { await menuService.delete(item.id); await refresh(); showMessage('success', 'Produto excluído.'); }
    catch (error) { showMessage('error', getErrorMessage(error, 'Não foi possível excluir o produto.')); }
  };
  const duplicateItem = (item) => setProductEditor({
    draft: { ...item, name: `${item.name} (cópia)`, externalCode: '' },
  });

  // ===== Grupos =====
  const deleteGroup = async (group, used) => {
    const text = used > 0 ? `Excluir o grupo "${group.name}"? Ele sai de ${used} ${used === 1 ? 'produto' : 'produtos'}.` : `Excluir o grupo "${group.name}"?`;
    if (!confirm(text)) return;
    try { await optionGroupService.delete(group.id); await refresh(); showMessage('success', 'Grupo excluído.'); }
    catch (error) { showMessage('error', getErrorMessage(error, 'Não foi possível excluir o grupo.')); }
  };

  const products = items.filter(isProduct);
  const soldOut = products.filter(item => item.status !== 'AVAILABLE').length;
  const editingProduct = productEditor?.id ? items.find(item => item.id === productEditor.id) || null : null;

  return (
    <div className="max-w-5xl mx-auto space-y-5 pb-10">
      {message && (
        <div role="status" className={`fixed top-4 right-4 z-[70] max-w-md p-4 rounded-xl flex items-start gap-2 font-bold shadow-lg border ${message.type === 'success' ? 'bg-green-50 text-green-700 border-green-200' : 'bg-red-50 text-red-700 border-red-200'}`}>
          {message.type === 'success' ? <CheckCircle className="w-5 h-5 shrink-0" /> : <AlertCircle className="w-5 h-5 shrink-0" />}
          <span className="flex-1 whitespace-pre-line">{message.text}</span>
          <button onClick={() => setMessage(null)} className="p-0.5 rounded hover:bg-black/5" aria-label="Fechar aviso"><X className="w-4 h-4" /></button>
        </div>
      )}

      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold text-slate-800">Cardápio</h2>
          <p className="text-slate-500 text-sm">
            {products.length} produtos em {categories.length} categorias · {optionGroups.length} grupos de complementos
            {soldOut > 0 && <span className="ml-2 font-bold text-red-600">· {soldOut} esgotado{soldOut > 1 ? 's' : ''}</span>}
          </p>
        </div>
      </div>

      <PublishPanel status={publishStatus} publishing={publishing} savingMode={savingMode}
        onPublish={handlePublish} onToggleSameMenu={toggleSameMenu} />

      <div className="flex gap-1 p-1 bg-slate-200/70 rounded-xl w-fit" role="tablist">
        {[
          ['products', 'Produtos', <Utensils key="i" className="w-4 h-4" />, products.length],
          ['complements', 'Complementos', <ListPlus key="i" className="w-4 h-4" />, optionGroups.length],
        ].map(([key, label, icon, count]) => (
          <button key={key} role="tab" aria-selected={tab === key} onClick={() => setTab(key)}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-bold transition-colors ${tab === key ? 'bg-white text-slate-800 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}>
            {icon}{label}<span className="text-xs text-slate-400">{count}</span>
          </button>
        ))}
      </div>

      {tab === 'products' ? (
        <ProductsTab
          categories={categories} items={items} optionGroups={optionGroups} loading={loading} busyId={busyId} reordering={reordering} sameMenu={sameMenu}
          onNewCategory={() => openCategory(null)} onEditCategory={openCategory} onDeleteCategory={deleteCategory}
          onToggleCategory={toggleCategory} onMoveCategory={(position, direction) => move(categories, position, direction, categoryService.update)}
          onNewProduct={(categoryId) => setProductEditor({ draft: { categoryId } })} onEditProduct={(item) => setProductEditor({ id: item.id })}
          onDuplicateProduct={duplicateItem} onDeleteProduct={deleteItem} onToggleProduct={toggleItem}
          onMoveProduct={(list, position, direction) => move(list, position, direction, menuService.update)}
        />
      ) : (
        <ComplementsTab
          optionGroups={optionGroups} items={items} loading={loading} busyId={busyId} sameMenu={sameMenu}
          onNewGroup={() => setGroupEditor({ group: null })} onEditGroup={(group) => setGroupEditor({ group })}
          onDeleteGroup={deleteGroup} onToggleItem={toggleItem}
        />
      )}

      {productEditor && (
        <ProductEditor
          key={productEditor.id || 'novo'}
          product={editingProduct} draft={productEditor.draft} categories={categories} optionGroups={optionGroups} availabilities={availabilities}
          onClose={() => setProductEditor(null)} onChanged={refresh} onCreated={(id) => setProductEditor({ id })}
          onCreateGroup={(product) => setGroupEditor({ group: null, presetProductIds: product ? [product.id] : [] })}
          showMessage={showMessage} sameMenu={sameMenu}
        />
      )}
      {groupEditor && (
        <GroupEditor
          group={groupEditor.group} items={items} categories={categories} presetProductIds={groupEditor.presetProductIds}
          onClose={() => setGroupEditor(null)} onChanged={refresh} showMessage={showMessage} sameMenu={sameMenu}
        />
      )}
      {categoryEditor && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4" role="dialog" aria-modal="true" aria-label="Categoria">
          <form onSubmit={saveCategory} className="bg-white rounded-2xl shadow-2xl w-full max-w-md p-6 space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="font-bold text-lg text-slate-800">{categoryEditor.category ? 'Editar categoria' : 'Nova categoria'}</h3>
              <button type="button" onClick={() => setCategoryEditor(null)} className="p-2 rounded-lg hover:bg-slate-100 text-slate-400" aria-label="Fechar"><X className="w-5 h-5" /></button>
            </div>
            <div><label className={labelClass} htmlFor="category-name">Nome *</label>
              <input id="category-name" className={inputClass} maxLength={150} value={categoryForm.name} onChange={e => setCategoryForm({ ...categoryForm, name: e.target.value })} placeholder="Ex.: Hambúrgueres" autoFocus /></div>
            <div><label className={labelClass} htmlFor="category-description">Descrição</label>
              <input id="category-description" className={inputClass} maxLength={500} value={categoryForm.description} onChange={e => setCategoryForm({ ...categoryForm, description: e.target.value })} placeholder="Ex.: Hambúrgueres artesanais da casa" /></div>
            {!sameMenu && (
              <div><p className={labelClass}>Onde a categoria aparece</p>
                <PlatformFields form={categoryForm} onChange={changes => setCategoryForm(prev => ({ ...prev, ...changes }))} withPrices={false} idPrefix="category" /></div>
            )}
            <div className="flex gap-3 pt-1">
              <button type="button" onClick={() => setCategoryEditor(null)} className="flex-1 py-2.5 font-bold rounded-xl border border-slate-200 text-slate-600 hover:bg-slate-50">Cancelar</button>
              <button type="submit" disabled={categorySaving} className={`flex-1 py-2.5 font-bold rounded-xl flex items-center justify-center gap-2 ${categorySaving ? 'bg-slate-300' : 'bg-indigo-600 hover:bg-indigo-700 text-white'}`}>
                {categorySaving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}{categoryEditor.category ? 'Salvar' : 'Criar categoria'}
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
