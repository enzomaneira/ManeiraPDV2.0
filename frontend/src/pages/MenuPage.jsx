import { useState, useEffect } from 'react';
import { categoryService, menuService, optionGroupService, availabilityService, keetaSyncService } from '../services/api';
import {
  Plus, Trash2, Utensils, Loader2, AlertCircle, CheckCircle,
  PackageOpen, FolderPlus, Edit3, ChevronRight, Tag, Image, Layers,
  X, Save, FolderOpen, Clock, ListPlus, CalendarDays, RefreshCw, Send, Link, Unlink
} from 'lucide-react';
import { formatCurrency } from '../utils/formatters';

export default function MenuPage() {
  const [categories, setCategories] = useState([]);
  const [items, setItems] = useState([]);
  const [optionGroups, setOptionGroups] = useState([]);
  const [availabilities, setAvailabilities] = useState([]);
  const [selectedCategoryId, setSelectedCategoryId] = useState(null);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState(null);
  const [syncingMenu, setSyncingMenu] = useState(false);

  // --- Modal de categoria ---
  const [showCatModal, setShowCatModal] = useState(false);
  const [catForm, setCatForm] = useState({ name: '', description: '', externalCode: '' });
  const [catSaving, setCatSaving] = useState(false);
  const [editingCategory, setEditingCategory] = useState(null);

  // --- Modal de item (com abas) ---
  const [showItemModal, setShowItemModal] = useState(false);
  const [itemTab, setItemTab] = useState('info'); // 'info' | 'options' | 'availability'
  const [itemForm, setItemForm] = useState({
    name: '', description: '', externalCode: '', price: '', originalPrice: '',
    status: 'AVAILABLE', imageUrl: ''
  });
  const [itemSaving, setItemSaving] = useState(false);
  const [editingItem, setEditingItem] = useState(null);

  // --- OptionGroup inline (dentro do modal de item) ---
  const [ogInlineForm, setOgInlineForm] = useState({ name: '', description: '', externalCode: '', minPermitted: 0, maxPermitted: 1, priceMethod: 'SUM', status: 'AVAILABLE' });
  const [ogInlineSaving, setOgInlineSaving] = useState(false);
  const [ogInlineEditing, setOgInlineEditing] = useState(null); // null=criando, number=editando grupo
  // --- Option inline na aba ---
  const [optInlineTarget, setOptInlineTarget] = useState(null); // {groupId, optionId} ou null
  const [optInlineForm, setOptInlineForm] = useState({ name: '', description: '', externalCode: '', price: '0', status: 'AVAILABLE' });
  const [optInlineSaving, setOptInlineSaving] = useState(false);
  // --- Expansão de grupos na aba ---
  const [expandedOGs, setExpandedOGs] = useState({});
  // --- Availability rápido ---
  const [availForm, setAvailForm] = useState({ name: '', startDate: '', endDate: '', hours: [{ dayOfWeek: 'MONDAY', startTime: '00:00:00.000Z', endTime: '23:59:00.000Z' }] });
  const [availSaving, setAvailSaving] = useState(false);

  const [deletingId, setDeletingId] = useState(null);

  // --- Modal gerenciador de OptionGroups (independente) ---
  const [showOGManager, setShowOGManager] = useState(false);
  const [ogEditingId, setOgEditingId] = useState(null);  // null = novo, number = editando
  const [ogManagerForm, setOgManagerForm] = useState({
    name: '', description: '', externalCode: '', minPermitted: 0, maxPermitted: 1, priceMethod: 'SUM', status: 'AVAILABLE'
  });
  const [ogManagerSaving, setOgManagerSaving] = useState(false);
  // Options dentro do gerenciador
  const [optionEditTarget, setOptionEditTarget] = useState(null);  // {groupId, optionId} ou null=novo
  const [optionManagerForm, setOptionManagerForm] = useState({ name: '', description: '', externalCode: '', price: '0', status: 'AVAILABLE' });
  const [optionManagerSaving, setOptionManagerSaving] = useState(false);

  // ===== Carrega dados =====
  const fetchData = async () => {
    setLoading(true);
    try {
      const [catRes, itemRes, ogRes, avRes] = await Promise.all([
        categoryService.getAll(),
        menuService.getAll(selectedCategoryId || undefined),
        optionGroupService.getAll(),
        availabilityService.getAll(),
      ]);
      setCategories(catRes.data || []);
      setItems(itemRes.data || []);
      setOptionGroups(ogRes.data || []);
      setAvailabilities(avRes.data || []);
    } catch (error) {
      console.error('Erro ao carregar cardápio:', error);
      setMessage({ type: 'error', text: 'Erro ao carregar dados.' });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchData(); }, []);
  useEffect(() => { if (!loading) fetchData(); }, [selectedCategoryId]);

  // ===== Sync Keeta =====
  const handleSyncMenu = async () => {
    setSyncingMenu(true); setMessage(null);
    try {
      const res = await keetaSyncService.syncMenu();
      setMessage({ type: 'success', text: res.data?.message || 'Menu enviado para sincronização!' });
    } catch (error) {
      setMessage({ type: 'error', text: error.response?.data?.error || 'Erro ao sincronizar com a Keeta.' });
    } finally { setSyncingMenu(false); setTimeout(() => setMessage(null), 5000); }
  };

  // ===== Categoria =====
  const openNewCategory = () => { setEditingCategory(null); setCatForm({ name: '', description: '', externalCode: '' }); setShowCatModal(true); };
  const openEditCategory = (cat) => { setEditingCategory(cat); setCatForm({ name: cat.name, description: cat.description || '', externalCode: cat.externalCode }); setShowCatModal(true); };
  const handleSaveCategory = async (e) => {
    e.preventDefault(); const name = catForm.name.trim(); if (!name) return;
    setCatSaving(true);
    try {
      const payload = { name, description: catForm.description.trim(), externalCode: catForm.externalCode.trim() || `cat-${Date.now()}` };
      if (editingCategory) await categoryService.update(editingCategory.id, payload);
      else await categoryService.create(payload);
      setShowCatModal(false); fetchData();
    } catch { setMessage({ type: 'error', text: 'Erro ao salvar categoria.' }); }
    finally { setCatSaving(false); }
  };
  const handleDeleteCategory = async (cat) => {
    if (!confirm(`Remover "${cat.name}"?`)) return;
    setDeletingId(cat.id);
    try { await categoryService.delete(cat.id); if (selectedCategoryId === cat.id) setSelectedCategoryId(null); fetchData(); }
    catch { setMessage({ type: 'error', text: 'Erro ao remover.' }); }
    finally { setDeletingId(null); }
  };

  // ===== Item =====
  const openNewItem = () => {
    if (!selectedCategoryId) { setMessage({ type: 'error', text: 'Selecione uma categoria primeiro.' }); setTimeout(() => setMessage(null), 3000); return; }
    setEditingItem(null); setItemTab('info');
    setItemForm({ name: '', description: '', externalCode: '', price: '', originalPrice: '', status: 'AVAILABLE', imageUrl: '' });
    setShowItemModal(true);
  };
  const openEditItem = (item) => {
    setEditingItem(item); setItemTab('info');
    setItemForm({ name: item.name, description: item.description || '', externalCode: item.externalCode, price: String(item.price || ''), originalPrice: String(item.originalPrice || item.price || ''), status: item.status || 'AVAILABLE', imageUrl: item.imageUrl || '' });
    setShowItemModal(true);
    // Garante que a categoria está selecionada
    if (item.categoryId && !selectedCategoryId) setSelectedCategoryId(item.categoryId);
  };
  const handleSaveItem = async (e) => {
    e.preventDefault(); const name = itemForm.name.trim(); const price = parseFloat(itemForm.price);
    if (!name || isNaN(price) || price < 0) { setMessage({ type: 'error', text: 'Nome e preço são obrigatórios.' }); return; }
    setItemSaving(true);
    const payload = { name, description: itemForm.description.trim(), externalCode: itemForm.externalCode.trim() || String(Date.now()), price, originalPrice: parseFloat(itemForm.originalPrice) || price, status: itemForm.status, imageUrl: itemForm.imageUrl.trim(), categoryId: selectedCategoryId };
    try {
      if (editingItem) await menuService.update(editingItem.id, payload);
      else await menuService.create(payload);
      setShowItemModal(false); fetchData();
    } catch { setMessage({ type: 'error', text: 'Erro ao salvar item.' }); }
    finally { setItemSaving(false); }
  };
  const handleDeleteItem = async (item) => {
    if (!confirm(`Remover "${item.name}"?`)) return;
    setDeletingId(item.id);
    try { await menuService.delete(item.id); fetchData(); }
    catch { setMessage({ type: 'error', text: 'Erro ao remover.' }); }
    finally { setDeletingId(null); }
  };

  // ===== OptionGroup (inline no modal de item) =====
  const handleCreateOrUpdateOGInline = async (e) => {
    e.preventDefault(); if (!ogInlineForm.name.trim()) return;
    setOgInlineSaving(true);
    try {
      const payload = {
        name: ogInlineForm.name.trim(),
        description: ogInlineForm.description.trim(),
        externalCode: ogInlineForm.externalCode.trim() || `og-${Date.now()}`,
        minPermitted: parseInt(ogInlineForm.minPermitted) || 0,
        maxPermitted: parseInt(ogInlineForm.maxPermitted) || 1,
        priceMethod: ogInlineForm.priceMethod, status: ogInlineForm.status,
      };
      let groupId;
      if (ogInlineEditing) {
        await optionGroupService.update(ogInlineEditing, payload);
        groupId = ogInlineEditing;
      } else {
        const res = await optionGroupService.create(payload);
        groupId = res.data.id;
        if (editingItem) await menuService.linkOptionGroup(editingItem.id, groupId);
      }
      await fetchData();
      setOgInlineEditing(null);
      setOgInlineForm({ name: '', description: '', externalCode: '', minPermitted: 0, maxPermitted: 1, priceMethod: 'SUM', status: 'AVAILABLE' });
    } catch { setMessage({ type: 'error', text: 'Erro ao salvar grupo.' }); setTimeout(() => setMessage(null), 3000); }
    finally { setOgInlineSaving(false); }
  };

  const startEditOGInline = (og) => {
    setOgInlineEditing(og.id);
    setOgInlineForm({
      name: og.name, description: og.description || '', externalCode: og.externalCode || '',
      minPermitted: og.minPermitted ?? 0, maxPermitted: og.maxPermitted ?? 1,
      priceMethod: og.priceMethod || 'SUM', status: og.status || 'AVAILABLE'
    });
  };

  const handleDeleteOGInline = async (og) => {
    if (!confirm(`Remover "${og.name}" e suas opções?`)) return;
    try { await optionGroupService.delete(og.id); await fetchData(); }
    catch { setMessage({ type: 'error', text: 'Erro ao remover.' }); setTimeout(() => setMessage(null), 3000); }
  };

  // --- Options inline ---
  const startNewOptionInline = (groupId) => {
    setOptInlineTarget({ groupId, optionId: null });
    setOptInlineForm({ name: '', description: '', externalCode: '', price: '0', status: 'AVAILABLE' });
  };
  const startEditOptionInline = (groupId, opt) => {
    setOptInlineTarget({ groupId, optionId: opt.id });
    setOptInlineForm({
      name: opt.name, description: opt.description || '', externalCode: opt.externalCode || '',
      price: String(opt.price || 0), status: opt.status || 'AVAILABLE'
    });
  };
  const handleSaveOptionInline = async (e) => {
    e.preventDefault();
    if (!optInlineTarget || !optInlineForm.name.trim()) return;
    setOptInlineSaving(true);
    try {
      const payload = {
        name: optInlineForm.name.trim(), description: optInlineForm.description.trim(),
        externalCode: optInlineForm.externalCode.trim() || `opt-${Date.now()}`,
        price: parseFloat(optInlineForm.price) || 0, status: optInlineForm.status,
      };
      if (optInlineTarget.optionId)
        await optionGroupService.updateOption(optInlineTarget.groupId, optInlineTarget.optionId, payload);
      else
        await optionGroupService.createOption(optInlineTarget.groupId, payload);
      setOptInlineTarget(null); await fetchData();
    } catch { setMessage({ type: 'error', text: 'Erro ao salvar opção.' }); setTimeout(() => setMessage(null), 3000); }
    finally { setOptInlineSaving(false); }
  };
  const handleDeleteOptionInline = async (groupId, optionId, name) => {
    if (!confirm(`Remover "${name}"?`)) return;
    try { await optionGroupService.deleteOption(groupId, optionId); await fetchData(); }
    catch { setMessage({ type: 'error', text: 'Erro.' }); setTimeout(() => setMessage(null), 3000); }
  };

  const toggleExpandOG = (ogId) => setExpandedOGs(prev => ({ ...prev, [ogId]: !prev[ogId] }));

  const handleLinkExistingOG = async (groupId) => {
    if (!editingItem) return;
    try { await menuService.linkOptionGroup(editingItem.id, groupId); fetchData(); }
    catch { setMessage({ type: 'error', text: 'Erro ao vincular.' }); setTimeout(() => setMessage(null), 3000); }
  };

  const handleUnlinkOG = async (groupId) => {
    if (!editingItem) return;
    try { await menuService.unlinkOptionGroup(editingItem.id, groupId); fetchData(); }
    catch { setMessage({ type: 'error', text: 'Erro ao desvincular.' }); setTimeout(() => setMessage(null), 3000); }
  };

  // ===== Availability (contextual ao item) =====
  const handleCreateAvailabilityInline = async (e) => {
    e.preventDefault(); if (!availForm.name.trim() || !editingItem) return;
    setAvailSaving(true);
    try {
      const res = await availabilityService.create(availForm);
      await menuService.linkAvailability(editingItem.id, res.data.id);
      setAvailForm({ name: '', startDate: '', endDate: '', hours: [{ dayOfWeek: 'MONDAY', startTime: '00:00:00.000Z', endTime: '23:59:00.000Z' }] }); fetchData();
      setMessage({ type: 'success', text: 'Disponibilidade criada e vinculada!' });
    } catch { setMessage({ type: 'error', text: 'Erro ao criar disponibilidade.' }); }
    finally { setAvailSaving(false); setTimeout(() => setMessage(null), 3000); }
  };

  const handleLinkExistingAvail = async (availId) => {
    if (!editingItem) return;
    try { await menuService.linkAvailability(editingItem.id, availId); fetchData(); }
    catch { setMessage({ type: 'error', text: 'Erro ao vincular.' }); setTimeout(() => setMessage(null), 3000); }
  };

  const handleUnlinkAvail = async (availId) => {
    if (!editingItem) return;
    try { await menuService.unlinkAvailability(editingItem.id, availId); fetchData(); }
    catch { setMessage({ type: 'error', text: 'Erro ao desvincular.' }); setTimeout(() => setMessage(null), 3000); }
  };

  // ===== Helpers =====
  const avgPrice = items.length > 0 ? items.reduce((s, i) => s + i.price, 0) / items.length : 0;
  const selectedCategory = categories.find(c => c.id === selectedCategoryId);

  // ===== Gerenciador de OptionGroups (modal independente) =====
  const openOGManager = () => {
    setOgEditingId(null);
    setOgManagerForm({ name: '', description: '', externalCode: '', minPermitted: 0, maxPermitted: 1, priceMethod: 'SUM', status: 'AVAILABLE' });
    setOptionEditTarget(null);
    setShowOGManager(true);
  };

  const openEditOG = (og) => {
    setOgEditingId(og.id);
    setOgManagerForm({
      name: og.name, description: og.description || '', externalCode: og.externalCode || '',
      minPermitted: og.minPermitted ?? 0, maxPermitted: og.maxPermitted ?? 1,
      priceMethod: og.priceMethod || 'SUM', status: og.status || 'AVAILABLE'
    });
    setOptionEditTarget(null);
    setShowOGManager(true);
  };

  const handleSaveOG = async (e) => {
    e.preventDefault();
    const name = ogManagerForm.name.trim();
    if (!name) { setMessage({ type: 'error', text: 'Nome do grupo é obrigatório.' }); setTimeout(() => setMessage(null), 3000); return; }
    setOgManagerSaving(true);
    try {
      const payload = {
        name, description: ogManagerForm.description.trim(),
        externalCode: ogManagerForm.externalCode.trim() || `og-${Date.now()}`,
        minPermitted: parseInt(ogManagerForm.minPermitted) || 0,
        maxPermitted: parseInt(ogManagerForm.maxPermitted) || 1,
        priceMethod: ogManagerForm.priceMethod, status: ogManagerForm.status,
      };
      if (ogEditingId) await optionGroupService.update(ogEditingId, payload);
      else await optionGroupService.create(payload);
      setOgEditingId(null);
      setOgManagerForm({ name: '', description: '', externalCode: '', minPermitted: 0, maxPermitted: 1, priceMethod: 'SUM', status: 'AVAILABLE' });
      await fetchData();
      setMessage({ type: 'success', text: ogEditingId ? 'Grupo atualizado!' : 'Grupo criado!' });
      setTimeout(() => setMessage(null), 3000);
    } catch (err) {
      setMessage({ type: 'error', text: 'Erro ao salvar grupo de opções.' });
      setTimeout(() => setMessage(null), 3000);
    } finally { setOgManagerSaving(false); }
  };

  const handleDeleteOG = async (og) => {
    if (!confirm(`Remover grupo "${og.name}" e todas as suas ${og.optionCount || 0} opções?`)) return;
    try { await optionGroupService.delete(og.id); await fetchData(); setMessage({ type: 'success', text: 'Grupo removido.' }); }
    catch { setMessage({ type: 'error', text: 'Erro ao remover grupo.' }); }
    setTimeout(() => setMessage(null), 3000);
  };

  // --- Options no gerenciador ---
  const openNewOption = (groupId) => {
    setOptionEditTarget({ groupId, optionId: null });
    setOptionManagerForm({ name: '', description: '', externalCode: '', price: '0', status: 'AVAILABLE' });
  };

  const openEditOption = (groupId, opt) => {
    setOptionEditTarget({ groupId, optionId: opt.id });
    setOptionManagerForm({
      name: opt.name, description: opt.description || '', externalCode: opt.externalCode || '',
      price: String(opt.price || 0), status: opt.status || 'AVAILABLE'
    });
  };

  const handleSaveOption = async (e) => {
    e.preventDefault();
    if (!optionEditTarget || !optionManagerForm.name.trim()) {
      setMessage({ type: 'error', text: 'Nome da opção é obrigatório.' }); setTimeout(() => setMessage(null), 3000); return;
    }
    setOptionManagerSaving(true);
    try {
      const payload = {
        name: optionManagerForm.name.trim(), description: optionManagerForm.description.trim(),
        externalCode: optionManagerForm.externalCode.trim() || `opt-${Date.now()}`,
        price: parseFloat(optionManagerForm.price) || 0,
        status: optionManagerForm.status,
      };
      if (optionEditTarget.optionId) {
        await optionGroupService.updateOption(optionEditTarget.groupId, optionEditTarget.optionId, payload);
      } else {
        await optionGroupService.createOption(optionEditTarget.groupId, payload);
      }
      setOptionEditTarget(null);
      await fetchData();
      setMessage({ type: 'success', text: optionEditTarget.optionId ? 'Opção atualizada!' : 'Opção adicionada!' });
      setTimeout(() => setMessage(null), 3000);
    } catch {
      setMessage({ type: 'error', text: 'Erro ao salvar opção.' });
      setTimeout(() => setMessage(null), 3000);
    } finally { setOptionManagerSaving(false); }
  };

  const handleDeleteOption = async (groupId, optionId, optionName) => {
    if (!confirm(`Remover opção "${optionName}"?`)) return;
    try { await optionGroupService.deleteOption(groupId, optionId); await fetchData(); }
    catch { setMessage({ type: 'error', text: 'Erro ao remover opção.' }); }
  };

  // eslint-disable-next-line no-unused-vars
  const getLinkedOGs = (item) => optionGroups.filter(og =>
    (item.optionGroupsId || item.optionGroups?.map(g => g.id) || []).includes(og.id)
  );
  // eslint-disable-next-line no-unused-vars
  const getLinkedAvails = (item) => availabilities.filter(av =>
    (item.availabilityId || []).includes(av.id)
  );

  return (
    <div className="max-w-6xl mx-auto animate-in fade-in slide-in-from-bottom-4 space-y-6 pb-10">

      {/* ===== CABEÇALHO ===== */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-slate-800">Cardápio da Loja</h2>
          <p className="text-slate-500">Categorias → Itens → Grupos de Opções/Disponibilidade</p>
        </div>
        <div className="flex items-center gap-4 text-sm font-bold text-slate-500">
          <span className="px-3 py-1.5 bg-white rounded-lg border border-slate-200 shadow-sm">{categories.length} categorias</span>
          <span className="px-3 py-1.5 bg-white rounded-lg border border-slate-200 shadow-sm">{items.length} itens</span>
          {items.length > 0 && <span className="px-3 py-1.5 bg-white rounded-lg border border-slate-200 shadow-sm text-indigo-600">Média {formatCurrency(avgPrice)}</span>}
          <button onClick={openOGManager} className="px-3 py-1.5 bg-purple-50 rounded-lg border border-purple-200 shadow-sm text-purple-700 flex items-center gap-1.5 hover:bg-purple-100 transition-colors">
            <ListPlus className="w-4 h-4" />Grupos ({optionGroups.length})
          </button>
          <button onClick={handleSyncMenu} disabled={syncingMenu}
            className={`flex items-center gap-2 px-4 py-2 rounded-xl font-bold text-sm transition-all shadow-sm border ${syncingMenu ? 'bg-slate-200 text-slate-500 cursor-not-allowed' : 'bg-yellow-400 hover:bg-yellow-500 text-yellow-900 border-yellow-300 shadow-yellow-100 active:scale-[0.98]'}`}>
            {syncingMenu ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
            {syncingMenu ? 'Sincronizando...' : 'Enviar para Keeta'}
          </button>
        </div>
      </div>

      {message && (
        <div className={`p-4 rounded-xl flex items-center gap-2 font-bold ${message.type === 'success' ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}`}>
          {message.type === 'success' ? <CheckCircle className="w-5 h-5" /> : <AlertCircle className="w-5 h-5" />}{message.text}
        </div>
      )}

      {/* ===== LAYOUT: Sidebar + Área de Itens ===== */}
      <div className="flex gap-6">
        {/* ---- Sidebar: Categorias ---- */}
        <div className="w-64 shrink-0 space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="font-bold text-sm text-slate-500 uppercase tracking-wider"><Layers className="w-4 h-4 inline mr-1" />Categorias</h3>
            <button onClick={openNewCategory} className="p-1.5 rounded-lg text-indigo-500 hover:bg-indigo-50"><FolderPlus className="w-4 h-4" /></button>
          </div>
          <button onClick={() => setSelectedCategoryId(null)} className={`w-full text-left px-3 py-2.5 rounded-xl font-medium text-sm flex items-center gap-2 ${selectedCategoryId === null ? 'bg-indigo-50 text-indigo-700 border border-indigo-200' : 'text-slate-600 hover:bg-slate-100 border border-transparent'}`}>
            <FolderOpen className="w-4 h-4 shrink-0" /><span className="truncate">Todas ({items.length})</span>
          </button>
          <div className="space-y-1 max-h-[50vh] overflow-y-auto pr-1">
            {loading ? <div className="flex items-center justify-center py-8 text-slate-400"><Loader2 className="w-5 h-5 animate-spin" /></div>
              : categories.length === 0 ? <p className="text-xs text-slate-400 py-4 text-center">Nenhuma categoria.<br/>Clique em + para criar.</p>
              : categories.map(cat => (
                <div key={cat.id} className="group relative">
                  <button onClick={() => setSelectedCategoryId(cat.id)} className={`w-full text-left px-3 py-2.5 rounded-xl font-medium text-sm flex items-center gap-2 ${selectedCategoryId === cat.id ? 'bg-indigo-50 text-indigo-700 border border-indigo-200' : 'text-slate-600 hover:bg-slate-100 border border-transparent'}`}>
                    <ChevronRight className={`w-3.5 h-3.5 shrink-0 transition-transform ${selectedCategoryId === cat.id ? 'rotate-90' : ''}`} />
                    <span className="truncate flex-1">{cat.name}</span>
                    <span className="text-xs text-slate-400 shrink-0">{cat.itemCount || 0}</span>
                  </button>
                  <div className="absolute right-1 top-1/2 -translate-y-1/2 hidden group-hover:flex items-center gap-0.5 bg-white rounded-lg shadow-sm border border-slate-200 px-1 py-0.5">
                    <button onClick={(e) => { e.stopPropagation(); openEditCategory(cat); }} className="p-1 rounded text-slate-400 hover:text-indigo-600 hover:bg-indigo-50"><Edit3 className="w-3.5 h-3.5" /></button>
                    <button onClick={(e) => { e.stopPropagation(); handleDeleteCategory(cat); }} disabled={deletingId === cat.id} className="p-1 rounded text-slate-400 hover:text-red-600 hover:bg-red-50 disabled:opacity-50">
                      {deletingId === cat.id ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Trash2 className="w-3.5 h-3.5" />}</button>
                  </div>
                </div>
              ))}
          </div>
        </div>

        {/* ---- Área Principal: Itens ---- */}
        <div className="flex-1 min-w-0">
          <div className="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden">
            <div className="px-6 py-4 border-b border-slate-100 bg-slate-50/50 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className={`p-2 rounded-lg ${selectedCategory ? 'bg-amber-100 text-amber-700' : 'bg-indigo-100 text-indigo-700'}`}>{selectedCategory ? <Layers className="w-5 h-5" /> : <Utensils className="w-5 h-5" />}</div>
                <div>
                  <h3 className="font-bold text-lg text-slate-800">{selectedCategory ? selectedCategory.name : 'Todos os Itens'}</h3>
                  <p className="text-xs text-slate-400">{selectedCategory ? `Código: ${selectedCategory.externalCode} · ${selectedCategory.description || 'Sem descrição'}` : 'Itens de todas as categorias'}</p>
                </div>
              </div>
              <button onClick={openNewItem} className="flex items-center gap-2 px-4 py-2 rounded-xl font-bold text-sm bg-indigo-600 hover:bg-indigo-700 text-white shadow-md transition-all">
                <Plus className="w-4 h-4" />Novo Item
              </button>
            </div>

            {loading ? <div className="flex items-center justify-center py-20 text-slate-400"><Loader2 className="w-8 h-8 animate-spin mr-3" /><span>Carregando...</span></div>
              : items.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-20 text-slate-400">
                  <PackageOpen className="w-16 h-16 mb-4 text-slate-300" />
                  <p className="font-bold text-lg text-slate-500 mb-1">{selectedCategory ? 'Categoria vazia' : 'Cardápio vazio'}</p>
                  <p className="text-sm mb-6">{selectedCategory ? 'Clique em "Novo Item" para adicionar.' : 'Selecione uma categoria e adicione itens.'}</p>
                </div>
              ) : (
                <div className="divide-y divide-slate-100">
                  {items.map(item => (
                    <div key={item.id} className="flex items-center justify-between px-6 py-4 hover:bg-slate-50 transition-colors group">
                      <div className="flex items-center gap-4 min-w-0 flex-1">
                        <div className="w-12 h-12 rounded-xl bg-indigo-50 flex items-center justify-center shrink-0 overflow-hidden">
                          {item.imageUrl ? <img src={item.imageUrl} alt="" className="w-full h-full object-cover" /> : <Utensils className="w-6 h-6 text-indigo-400" />}
                        </div>
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2">
                            <p className="font-bold text-slate-800 truncate">{item.name}</p>
                            {item.status !== 'AVAILABLE' && <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-red-100 text-red-600 font-bold shrink-0">{item.status}</span>}
                          </div>
                          <div className="flex items-center gap-3 text-xs text-slate-400 mt-0.5">
                            {item.description && <span className="truncate max-w-[200px]">{item.description}</span>}
                            <span className="flex items-center gap-1"><Tag className="w-3 h-3" />{item.externalCode}</span>
                            {item.categoryName && <span className="flex items-center gap-1 text-indigo-500"><Layers className="w-3 h-3" />{item.categoryName}</span>}
                          </div>
                        </div>
                      </div>
                      <div className="flex items-center gap-4 shrink-0 ml-4">
                        <div className="text-right">
                          <span className="text-lg font-extrabold text-indigo-600 tabular-nums">{formatCurrency(item.price)}</span>
                          {item.originalPrice && item.originalPrice !== item.price && <span className="block text-xs text-slate-400 line-through">{formatCurrency(item.originalPrice)}</span>}
                        </div>
                        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-all">
                          <button onClick={() => openEditItem(item)} className="p-2 rounded-xl text-slate-300 hover:text-indigo-600 hover:bg-indigo-50" title="Editar item"><Edit3 className="w-4 h-4" /></button>
                          <button onClick={() => handleDeleteItem(item)} disabled={deletingId === item.id} className="p-2 rounded-xl text-slate-300 hover:text-red-600 hover:bg-red-50 disabled:opacity-50" title="Remover item">
                            {deletingId === item.id ? <Loader2 className="w-4 h-4 animate-spin text-red-400" /> : <Trash2 className="w-4 h-4" />}</button>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
          </div>
        </div>
      </div>

      {/* ===== MODAL: Categoria ===== */}
      {showCatModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md p-6">
            <div className="flex items-center justify-between mb-5"><h3 className="font-bold text-lg text-slate-800">{editingCategory ? 'Editar Categoria' : 'Nova Categoria'}</h3><button onClick={() => setShowCatModal(false)} className="p-2 rounded-lg hover:bg-slate-100 text-slate-400"><X className="w-5 h-5" /></button></div>
            <form onSubmit={handleSaveCategory} className="space-y-4">
              <div><label className="block text-sm font-bold text-slate-600 mb-1.5">Nome *</label><input type="text" value={catForm.name} onChange={e => setCatForm({ ...catForm, name: e.target.value })} placeholder="Ex: Pizzas" className="w-full px-4 py-2.5 bg-slate-50 border border-slate-200 rounded-xl focus:ring-2 focus:ring-indigo-400 focus:outline-none font-medium text-slate-700" autoFocus /></div>
              <div><label className="block text-sm font-bold text-slate-600 mb-1.5">Descrição</label><input type="text" value={catForm.description} onChange={e => setCatForm({ ...catForm, description: e.target.value })} placeholder="Breve descrição" className="w-full px-4 py-2.5 bg-slate-50 border border-slate-200 rounded-xl focus:ring-2 focus:ring-indigo-400 focus:outline-none font-medium text-slate-700" /></div>
              <div><label className="block text-sm font-bold text-slate-600 mb-1.5"><Tag className="w-3.5 h-3.5 inline mr-1" />Código Externo</label><input type="text" value={catForm.externalCode} onChange={e => setCatForm({ ...catForm, externalCode: e.target.value })} placeholder="PDV Code" className="w-full px-4 py-2.5 bg-slate-50 border border-slate-200 rounded-xl focus:ring-2 focus:ring-indigo-400 focus:outline-none font-mono text-sm text-slate-700" /></div>
              <div className="flex gap-3 pt-2">
                <button type="button" onClick={() => setShowCatModal(false)} className="flex-1 py-2.5 font-bold rounded-xl border border-slate-200 text-slate-600 hover:bg-slate-50">Cancelar</button>
                <button type="submit" disabled={catSaving} className={`flex-1 py-2.5 font-bold rounded-xl flex items-center justify-center gap-2 ${catSaving ? 'bg-slate-300 cursor-not-allowed' : 'bg-indigo-600 hover:bg-indigo-700 text-white shadow-md'}`}>
                  {catSaving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}{catSaving ? 'Salvando...' : editingCategory ? 'Atualizar' : 'Criar'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ===== MODAL: Item com Abas ===== */}
      {showItemModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl p-0 max-h-[90vh] overflow-y-auto">
            {/* Cabeçalho + Abas */}
            <div className="sticky top-0 bg-white z-10 border-b border-slate-200 rounded-t-2xl">
              <div className="flex items-center justify-between px-6 pt-5 pb-2">
                <h3 className="font-bold text-lg text-slate-800">
                  {editingItem ? `Editar: ${editingItem.name}` : 'Novo Item'}
                  <span className="text-sm font-normal text-slate-400 ml-2">· {selectedCategory?.name || 'Sem categoria'}</span>
                </h3>
                <button onClick={() => setShowItemModal(false)} className="p-2 rounded-lg hover:bg-slate-100 text-slate-400"><X className="w-5 h-5" /></button>
              </div>
              {/* Abas */}
              <div className="flex gap-1 px-6 pb-2">
                {['info', 'options', 'availability'].map(tab => (
                  <button key={tab} onClick={() => setItemTab(tab)}
                    className={`px-4 py-2 rounded-lg font-bold text-sm transition-all ${itemTab === tab ? 'bg-indigo-100 text-indigo-700' : 'text-slate-500 hover:bg-slate-100'}`}>
                    {tab === 'info' && <><Utensils className="w-4 h-4 inline mr-1" />Informações</>}
                    {tab === 'options' && <><ListPlus className="w-4 h-4 inline mr-1" />Grupos de Opções</>}
                    {tab === 'availability' && <><CalendarDays className="w-4 h-4 inline mr-1" />Disponibilidade</>}
                  </button>
                ))}
              </div>
            </div>

            <div className="p-6">
              {/* ===== Aba: Informações ===== */}
              {itemTab === 'info' && (
                <form onSubmit={handleSaveItem} className="space-y-4">
                  <div><label className="block text-sm font-bold text-slate-600 mb-1.5">Nome *</label><input type="text" value={itemForm.name} onChange={e => setItemForm({ ...itemForm, name: e.target.value })} className="w-full px-4 py-2.5 bg-slate-50 border border-slate-200 rounded-xl focus:ring-2 focus:ring-indigo-400 focus:outline-none font-medium" placeholder="Nome do produto" autoFocus /></div>
                  <div><label className="block text-sm font-bold text-slate-600 mb-1.5">Descrição</label><textarea value={itemForm.description} onChange={e => setItemForm({ ...itemForm, description: e.target.value })} rows={2} className="w-full px-4 py-2.5 bg-slate-50 border border-slate-200 rounded-xl focus:ring-2 focus:ring-indigo-400 focus:outline-none resize-none" /></div>
                  <div className="grid grid-cols-2 gap-3">
                    <div><label className="block text-sm font-bold text-slate-600 mb-1.5"><Tag className="w-3.5 h-3.5 inline mr-1" />Código Externo</label><input type="text" value={itemForm.externalCode} onChange={e => setItemForm({ ...itemForm, externalCode: e.target.value })} className="w-full px-4 py-2.5 bg-slate-50 border border-slate-200 rounded-xl font-mono text-sm" /></div>
                    <div><label className="block text-sm font-bold text-slate-600 mb-1.5">Status</label><select value={itemForm.status} onChange={e => setItemForm({ ...itemForm, status: e.target.value })} className="w-full px-4 py-2.5 bg-slate-50 border border-slate-200 rounded-xl font-medium"><option value="AVAILABLE">Disponível</option><option value="UNAVAILABLE">Indisponível</option></select></div>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div><label className="block text-sm font-bold text-slate-600 mb-1.5">Preço (R$) *</label><input type="number" step="0.01" min="0" value={itemForm.price} onChange={e => setItemForm({ ...itemForm, price: e.target.value })} className="w-full px-4 py-2.5 bg-slate-50 border border-slate-200 rounded-xl font-bold" /></div>
                    <div><label className="block text-sm font-bold text-slate-600 mb-1.5">Preço Original</label><input type="number" step="0.01" min="0" value={itemForm.originalPrice} onChange={e => setItemForm({ ...itemForm, originalPrice: e.target.value })} className="w-full px-4 py-2.5 bg-slate-50 border border-slate-200 rounded-xl font-bold" /></div>
                  </div>
                  <div><label className="block text-sm font-bold text-slate-600 mb-1.5"><Image className="w-3.5 h-3.5 inline mr-1" />URL da Imagem</label><input type="url" value={itemForm.imageUrl} onChange={e => setItemForm({ ...itemForm, imageUrl: e.target.value })} className="w-full px-4 py-2.5 bg-slate-50 border border-slate-200 rounded-xl font-mono text-sm" /></div>
                  <div className="flex gap-3 pt-2">
                    <button type="button" onClick={() => setShowItemModal(false)} className="flex-1 py-2.5 font-bold rounded-xl border border-slate-200 text-slate-600 hover:bg-slate-50">Cancelar</button>
                    <button type="submit" disabled={itemSaving} className={`flex-1 py-2.5 font-bold rounded-xl flex items-center justify-center gap-2 ${itemSaving ? 'bg-slate-300 cursor-not-allowed' : 'bg-indigo-600 hover:bg-indigo-700 text-white shadow-md'}`}>
                      {itemSaving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}{itemSaving ? 'Salvando...' : editingItem ? 'Atualizar' : 'Criar Item'}
                    </button>
                  </div>
                </form>
              )}

              {/* ===== Aba: Grupos de Opções ===== */}
              {itemTab === 'options' && editingItem && (
                <div className="space-y-4">
                  {/* Formulário de criação/edição de OptionGroup */}
                  <form onSubmit={handleCreateOrUpdateOGInline} className="p-4 bg-slate-50 rounded-xl border border-slate-200 space-y-3">
                    <div className="flex items-center justify-between">
                      <p className="text-sm font-bold text-slate-700">
                        {ogInlineEditing ? 'Editar Grupo' : 'Criar Novo Grupo'}
                        {!ogInlineEditing && <span className="text-xs font-normal text-slate-400 ml-2">(será vinculado automaticamente)</span>}
                      </p>
                      {ogInlineEditing && (
                        <button type="button" onClick={() => { setOgInlineEditing(null); setOgInlineForm({ name: '', description: '', externalCode: '', minPermitted: 0, maxPermitted: 1, priceMethod: 'SUM', status: 'AVAILABLE' }); }}
                          className="text-xs text-purple-600 hover:text-purple-800 font-medium">+ Novo</button>
                      )}
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className="block text-[11px] font-bold text-slate-500 mb-1">Nome *</label>
                        <input type="text" value={ogInlineForm.name} onChange={e => setOgInlineForm({ ...ogInlineForm, name: e.target.value })}
                          placeholder="Ex: Escolha o Molho" className="w-full px-3 py-2 bg-white border border-slate-200 rounded-lg text-sm" />
                      </div>
                      <div>
                        <label className="block text-[11px] font-bold text-slate-500 mb-1">Código Externo</label>
                        <input type="text" value={ogInlineForm.externalCode} onChange={e => setOgInlineForm({ ...ogInlineForm, externalCode: e.target.value })}
                          placeholder="og-molhos-001" className="w-full px-3 py-2 bg-white border border-slate-200 rounded-lg text-sm font-mono" />
                      </div>
                    </div>
                    <div className="grid grid-cols-3 gap-2">
                      <div>
                        <label className="block text-[11px] font-bold text-slate-500 mb-1">Mín</label>
                        <input type="number" min="0" value={ogInlineForm.minPermitted} onChange={e => setOgInlineForm({ ...ogInlineForm, minPermitted: parseInt(e.target.value) || 0 })}
                          className="w-full px-2 py-2 bg-white border border-slate-200 rounded-lg text-sm" />
                      </div>
                      <div>
                        <label className="block text-[11px] font-bold text-slate-500 mb-1">Máx</label>
                        <input type="number" min="1" value={ogInlineForm.maxPermitted} onChange={e => setOgInlineForm({ ...ogInlineForm, maxPermitted: parseInt(e.target.value) || 1 })}
                          className="w-full px-2 py-2 bg-white border border-slate-200 rounded-lg text-sm" />
                      </div>
                      <div>
                        <label className="block text-[11px] font-bold text-slate-500 mb-1">Preço</label>
                        <select value={ogInlineForm.priceMethod} onChange={e => setOgInlineForm({ ...ogInlineForm, priceMethod: e.target.value })}
                          className="w-full px-2 py-2 bg-white border border-slate-200 rounded-lg text-xs">
                          <option value="SUM">Somar</option>
                          <option value="HIGHEST">Maior</option>
                          <option value="LOWEST">Menor</option>
                        </select>
                      </div>
                    </div>
                    <button type="submit" disabled={ogInlineSaving}
                      className={`px-4 py-2 rounded-lg text-sm font-bold flex items-center gap-2 ${ogInlineSaving ? 'bg-slate-300 cursor-not-allowed' : 'bg-purple-600 hover:bg-purple-700 text-white'}`}>
                      {ogInlineSaving ? <Loader2 className="w-4 h-4 animate-spin" /> : ogInlineEditing ? <Save className="w-4 h-4" /> : <Plus className="w-4 h-4" />}
                      {ogInlineSaving ? 'Salvando...' : ogInlineEditing ? 'Atualizar Grupo' : 'Criar e Vincular'}
                    </button>
                  </form>

                  {/* Lista de grupos (todas, vinculadas ou não) */}
                  <div>
                    <p className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-2">
                      Todos os Grupos ({optionGroups.length})
                      <span className="text-slate-300 font-normal normal-case ml-1">— expanda para gerenciar opções</span>
                    </p>
                    {optionGroups.length === 0 ? (
                      <p className="text-sm text-slate-400 py-4 text-center">Nenhum grupo criado ainda.</p>
                    ) : (
                      <div className="space-y-2">
                        {optionGroups.map(og => {
                          const isLinked = (editingItem.optionGroupsId || []).includes(og.id);
                          const isExpanded = expandedOGs[og.id];
                          return (
                            <div key={og.id} className={`rounded-xl border overflow-hidden transition-all ${isLinked ? 'border-purple-300 shadow-sm' : 'border-slate-200'}`}>
                              {/* Linha principal do grupo */}
                              <div className={`flex items-center justify-between px-4 py-3 ${isLinked ? 'bg-purple-50' : 'bg-white'}`}>
                                <button onClick={() => toggleExpandOG(og.id)} className="flex-1 min-w-0 text-left flex items-center gap-2">
                                  <ChevronRight className={`w-3.5 h-3.5 text-slate-400 shrink-0 transition-transform ${isExpanded ? 'rotate-90' : ''}`} />
                                  <div className="min-w-0">
                                    <div className="flex items-center gap-2">
                                      <span className="font-bold text-slate-800 text-sm truncate">{og.name}</span>
                                      {isLinked && <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-purple-200 text-purple-700 font-bold shrink-0">Vinculado</span>}
                                    </div>
                                    <span className="text-xs text-slate-400">
                                      {og.optionCount || 0} opções · min={og.minPermitted} máx={og.maxPermitted} · {og.priceMethod}
                                    </span>
                                  </div>
                                </button>
                                <div className="flex items-center gap-1 ml-2 shrink-0">
                                  <button onClick={() => startEditOGInline(og)} className="p-1.5 rounded-lg text-slate-300 hover:text-purple-600 hover:bg-purple-50" title="Editar"><Edit3 className="w-3.5 h-3.5" /></button>
                                  <button onClick={() => isLinked ? handleUnlinkOG(og.id) : handleLinkExistingOG(og.id)}
                                    className={`text-[10px] font-bold px-2 py-1 rounded-lg ${isLinked ? 'bg-red-50 text-red-600 hover:bg-red-100' : 'bg-purple-600 text-white hover:bg-purple-700'}`}>
                                    {isLinked ? 'Desvincular' : 'Vincular'}
                                  </button>
                                </div>
                              </div>

                              {/* Conteúdo expandido: opções */}
                              {isExpanded && (
                                <div className="px-4 py-3 border-t border-slate-100 bg-slate-50/50 space-y-2">
                                  <div className="flex items-center justify-between">
                                    <p className="text-xs font-bold text-slate-500">Opções ({og.optionCount || 0})</p>
                                    <button onClick={() => startNewOptionInline(og.id)}
                                      className="text-xs font-bold px-2.5 py-1 rounded-lg bg-purple-100 text-purple-700 hover:bg-purple-200 flex items-center gap-1">
                                      <Plus className="w-3 h-3" />Adicionar
                                    </button>
                                  </div>

                                  {(!og.options || og.options.length === 0) ? (
                                    <p className="text-xs text-slate-400 py-1">Nenhuma opção.</p>
                                  ) : (
                                    <div className="space-y-1">
                                      {og.options.map(opt => (
                                        <div key={opt.id} className="flex items-center justify-between px-3 py-2 bg-white border border-slate-100 rounded-lg text-sm group">
                                          <div className="flex-1 min-w-0 flex items-center gap-2">
                                            <span className="w-1.5 h-1.5 rounded-full bg-purple-400 shrink-0"></span>
                                            <span className="text-slate-700 font-medium truncate">{opt.name}</span>
                                            {opt.price > 0 && <span className="text-xs text-indigo-600 font-bold shrink-0">+{formatCurrency(opt.price)}</span>}
                                          </div>
                                          <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-all ml-2">
                                            <button onClick={() => startEditOptionInline(og.id, opt)} className="p-1 rounded text-slate-300 hover:text-indigo-600 hover:bg-indigo-50" title="Editar"><Edit3 className="w-3.5 h-3.5" /></button>
                                            <button onClick={() => handleDeleteOptionInline(og.id, opt.id, opt.name)} className="p-1 rounded text-slate-300 hover:text-red-600 hover:bg-red-50" title="Remover"><Trash2 className="w-3.5 h-3.5" /></button>
                                          </div>
                                        </div>
                                      ))}
                                    </div>
                                  )}

                                  {/* Form inline option */}
                                  {optInlineTarget && optInlineTarget.groupId === og.id && (
                                    <form onSubmit={handleSaveOptionInline} className="p-3 bg-purple-50 rounded-lg border border-purple-200 space-y-2">
                                      <p className="text-xs font-bold text-purple-700">{optInlineTarget.optionId ? 'Editar Opção' : 'Nova Opção'}</p>
                                      <div className="flex gap-2">
                                        <input type="text" placeholder="Nome *" value={optInlineForm.name}
                                          onChange={e => setOptInlineForm({ ...optInlineForm, name: e.target.value })}
                                          className="flex-1 px-2.5 py-1.5 text-sm border border-slate-200 rounded-lg" autoFocus />
                                        <input type="number" step="0.01" placeholder="R$" value={optInlineForm.price}
                                          onChange={e => setOptInlineForm({ ...optInlineForm, price: e.target.value })}
                                          className="w-24 px-2.5 py-1.5 text-sm border border-slate-200 rounded-lg" />
                                      </div>
                                      <div className="flex gap-2">
                                        <button type="submit" disabled={optInlineSaving}
                                          className={`px-3 py-1.5 rounded-lg text-xs font-bold flex items-center gap-1 ${optInlineSaving ? 'bg-slate-300 cursor-not-allowed' : 'bg-purple-600 text-white hover:bg-purple-700'}`}>
                                          {optInlineSaving ? <Loader2 className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />}
                                          {optInlineSaving ? '...' : optInlineTarget.optionId ? 'Atualizar' : 'Adicionar'}
                                        </button>
                                        <button type="button" onClick={() => setOptInlineTarget(null)}
                                          className="px-3 py-1.5 rounded-lg text-xs font-bold border border-slate-200 text-slate-600 hover:bg-slate-100">Cancelar</button>
                                      </div>
                                    </form>
                                  )}
                                </div>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>

                  <p className="text-xs text-slate-400 text-center pt-2">
                    Precisa de mais opções? Use o{" "}
                    <button onClick={() => { setShowItemModal(false); openOGManager(); }}
                      className="text-purple-600 underline font-medium hover:text-purple-800">Gerenciador Completo</button>
                  </p>
                </div>
              )}
              {itemTab === 'options' && !editingItem && (
                <div className="text-center py-8 text-slate-400"><p className="font-medium">Salve o item primeiro para gerenciar grupos de opções.</p></div>
              )}

              {/* ===== Aba: Disponibilidade ===== */}
              {itemTab === 'availability' && editingItem && (
                <div className="space-y-4">
                  <p className="text-sm text-slate-500">Regras de disponibilidade vinculadas a este item.</p>

                  {/* Criar nova disponibilidade inline */}
                  <form onSubmit={handleCreateAvailabilityInline} className="p-4 bg-slate-50 rounded-xl border border-slate-200 space-y-3">
                    <p className="text-sm font-bold text-slate-600">Criar e Vincular Nova Regra</p>
                    <div className="grid grid-cols-3 gap-3">
                      <input type="text" placeholder="Nome *" value={availForm.name} onChange={e => setAvailForm({ ...availForm, name: e.target.value })} className="px-3 py-2 bg-white border border-slate-200 rounded-lg text-sm" />
                      <input type="date" value={availForm.startDate} onChange={e => setAvailForm({ ...availForm, startDate: e.target.value })} className="px-3 py-2 bg-white border border-slate-200 rounded-lg text-sm" />
                      <input type="date" value={availForm.endDate} onChange={e => setAvailForm({ ...availForm, endDate: e.target.value })} className="px-3 py-2 bg-white border border-slate-200 rounded-lg text-sm" />
                    </div>
                    <button type="submit" disabled={availSaving} className="px-4 py-2 bg-teal-600 text-white rounded-lg text-sm font-bold hover:bg-teal-700 disabled:opacity-50">{availSaving ? '...' : 'Criar e Vincular'}</button>
                  </form>

                  {/* Vincular disponibilidades existentes */}
                  <div>
                    <p className="text-xs font-bold text-slate-500 mb-2">Vincular Regra Existente</p>
                    <div className="flex flex-wrap gap-2">
                      {availabilities.map(av => {
                        const isLinked = editingItem.availabilityId?.includes(av.id);
                        return (
                          <button key={av.id} onClick={() => isLinked ? handleUnlinkAvail(av.id) : handleLinkExistingAvail(av.id)}
                            className={`text-xs px-3 py-1.5 rounded-full font-medium transition-all ${isLinked ? 'bg-teal-100 text-teal-700 hover:bg-red-100 hover:text-red-700' : 'bg-slate-100 text-slate-500 hover:bg-teal-50 hover:text-teal-600'}`}>
                            {isLinked ? <><Unlink className="w-3 h-3 inline mr-1" />{av.name}</> : <><Link className="w-3 h-3 inline mr-1" />{av.name}</>}
                          </button>
                        );
                      })}
                      {availabilities.length === 0 && <span className="text-xs text-slate-400">Nenhuma regra disponível.</span>}
                    </div>
                  </div>

                  {/* Exibir disponibilidades vinculadas */}
                  {availabilities.filter(av => editingItem.availabilityId?.includes(av.id)).map(av => (
                    <div key={av.id} className="border border-teal-200 rounded-xl p-4 bg-teal-50/30">
                      <div className="flex items-center justify-between">
                        <span className="font-bold text-slate-700">{av.name}</span>
                        <button onClick={async () => { await availabilityService.delete(av.id); fetchData(); }} className="text-xs text-red-400 hover:text-red-600">🗑️</button>
                      </div>
                      <div className="text-xs text-slate-400 mt-1">{av.startDate && av.endDate ? `${av.startDate} até ${av.endDate}` : 'Sem limite de data'}</div>
                      <div className="flex flex-wrap gap-1 mt-2">
                        {av.hours?.map((h, i) => <span key={i} className="text-[10px] px-2 py-0.5 bg-slate-100 rounded-full text-slate-600">{h.dayOfWeek} {h.startTime?.slice(0,5)}-{h.endTime?.slice(0,5)}</span>)}
                      </div>
                    </div>
                  ))}
                </div>
              )}
              {itemTab === 'availability' && !editingItem && (
                <div className="text-center py-8 text-slate-400"><p className="font-medium">Salve o item primeiro para gerenciar disponibilidade.</p></div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ===== Categoria (já definido acima) ===== */}
      {/* O modal de categoria é renderizado condicionalmente acima */}

      {/* ===== MODAL: Gerenciador de Grupos de Opções ===== */}
      {showOGManager && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-3xl p-0 max-h-[90vh] overflow-y-auto">
            {/* Cabeçalho */}
            <div className="sticky top-0 bg-white z-10 border-b border-slate-200 rounded-t-2xl px-6 pt-5 pb-3 flex items-center justify-between">
              <div>
                <h3 className="font-bold text-lg text-slate-800 flex items-center gap-2">
                  <ListPlus className="w-5 h-5 text-purple-600" />
                  Gerenciar Grupos de Opções
                </h3>
                <p className="text-xs text-slate-400 mt-0.5">Crie, edite e gerencie grupos de opções e seus subitens</p>
              </div>
              <button onClick={() => { setShowOGManager(false); setOptionEditTarget(null); setOgEditingId(null); }}
                className="p-2 rounded-lg hover:bg-slate-100 text-slate-400"><X className="w-5 h-5" /></button>
            </div>

            <div className="p-6">
              {/* Formulário de criação/edição de OptionGroup */}
              <form onSubmit={handleSaveOG} className="mb-6 p-4 bg-slate-50 rounded-xl border border-slate-200 space-y-3">
                <p className="text-sm font-bold text-slate-700">{ogEditingId ? 'Editar Grupo' : 'Criar Novo Grupo'}</p>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-bold text-slate-500 mb-1">Nome *</label>
                    <input type="text" value={ogManagerForm.name} onChange={e => setOgManagerForm({ ...ogManagerForm, name: e.target.value })}
                      placeholder="Ex: Escolha o Molho" className="w-full px-3 py-2 bg-white border border-slate-200 rounded-lg text-sm" autoFocus={!ogEditingId} />
                  </div>
                  <div>
                    <label className="block text-xs font-bold text-slate-500 mb-1">Código Externo</label>
                    <input type="text" value={ogManagerForm.externalCode} onChange={e => setOgManagerForm({ ...ogManagerForm, externalCode: e.target.value })}
                      placeholder="og-molhos-001" className="w-full px-3 py-2 bg-white border border-slate-200 rounded-lg text-sm font-mono" />
                  </div>
                </div>
                <div>
                  <label className="block text-xs font-bold text-slate-500 mb-1">Descrição</label>
                  <input type="text" value={ogManagerForm.description} onChange={e => setOgManagerForm({ ...ogManagerForm, description: e.target.value })}
                    placeholder="Breve descrição do grupo" className="w-full px-3 py-2 bg-white border border-slate-200 rounded-lg text-sm" />
                </div>
                <div className="grid grid-cols-4 gap-3">
                  <div>
                    <label className="block text-xs font-bold text-slate-500 mb-1">Mínimo</label>
                    <input type="number" min="0" value={ogManagerForm.minPermitted} onChange={e => setOgManagerForm({ ...ogManagerForm, minPermitted: parseInt(e.target.value) || 0 })}
                      className="w-full px-3 py-2 bg-white border border-slate-200 rounded-lg text-sm" />
                  </div>
                  <div>
                    <label className="block text-xs font-bold text-slate-500 mb-1">Máximo</label>
                    <input type="number" min="1" value={ogManagerForm.maxPermitted} onChange={e => setOgManagerForm({ ...ogManagerForm, maxPermitted: parseInt(e.target.value) || 1 })}
                      className="w-full px-3 py-2 bg-white border border-slate-200 rounded-lg text-sm" />
                  </div>
                  <div>
                    <label className="block text-xs font-bold text-slate-500 mb-1">Método de Preço</label>
                    <select value={ogManagerForm.priceMethod} onChange={e => setOgManagerForm({ ...ogManagerForm, priceMethod: e.target.value })}
                      className="w-full px-3 py-2 bg-white border border-slate-200 rounded-lg text-sm">
                      <option value="SUM">Soma (SUM)</option>
                      <option value="HIGHEST">Maior (HIGHEST)</option>
                      <option value="LOWEST">Menor (LOWEST)</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs font-bold text-slate-500 mb-1">Status</label>
                    <select value={ogManagerForm.status} onChange={e => setOgManagerForm({ ...ogManagerForm, status: e.target.value })}
                      className="w-full px-3 py-2 bg-white border border-slate-200 rounded-lg text-sm">
                      <option value="AVAILABLE">Disponível</option>
                      <option value="UNAVAILABLE">Indisponível</option>
                    </select>
                  </div>
                </div>
                <div className="flex gap-3 pt-1">
                  <button type="submit" disabled={ogManagerSaving}
                    className={`px-4 py-2 rounded-lg text-sm font-bold flex items-center gap-2 ${ogManagerSaving ? 'bg-slate-300 cursor-not-allowed' : 'bg-purple-600 hover:bg-purple-700 text-white'}`}>
                    {ogManagerSaving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                    {ogManagerSaving ? 'Salvando...' : ogEditingId ? 'Atualizar Grupo' : 'Criar Grupo'}
                  </button>
                  {ogEditingId && (
                    <button type="button" onClick={() => { setOgEditingId(null); setOgManagerForm({ name: '', description: '', externalCode: '', minPermitted: 0, maxPermitted: 1, priceMethod: 'SUM', status: 'AVAILABLE' }); }}
                      className="px-4 py-2 rounded-lg text-sm font-bold border border-slate-200 text-slate-600 hover:bg-slate-100">
                      Novo Grupo
                    </button>
                  )}
                </div>
              </form>

              {/* Lista de todos os OptionGroups com seus Options */}
              <div>
                <p className="text-sm font-bold text-slate-500 uppercase tracking-wider mb-3">Todos os Grupos ({optionGroups.length})</p>
                {optionGroups.length === 0 ? (
                  <div className="text-center py-8 text-slate-400">
                    <ListPlus className="w-10 h-10 mx-auto mb-2 text-slate-300" />
                    <p className="font-medium">Nenhum grupo de opções criado.</p>
                    <p className="text-xs mt-1">Use o formulário acima para criar o primeiro.</p>
                  </div>
                ) : (
                  <div className="space-y-3">
                    {optionGroups.map(og => (
                      <div key={og.id} className="border border-slate-200 rounded-xl overflow-hidden">
                        {/* Cabeçalho do grupo */}
                        <div className="flex items-center justify-between px-4 py-3 bg-slate-50">
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2">
                              <span className="font-bold text-slate-800">{og.name}</span>
                              <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-bold ${og.status === 'AVAILABLE' ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-600'}`}>{og.status}</span>
                            </div>
                            <div className="text-xs text-slate-400 mt-0.5">
                              {og.description || 'Sem descrição'} · {og.externalCode} · min={og.minPermitted} max={og.maxPermitted} · {og.priceMethod}
                            </div>
                          </div>
                          <div className="flex items-center gap-1 ml-3">
                            <button onClick={() => openEditOG(og)} className="p-1.5 rounded-lg text-slate-400 hover:text-purple-600 hover:bg-purple-50" title="Editar grupo"><Edit3 className="w-4 h-4" /></button>
                            <button onClick={() => handleDeleteOG(og)} className="p-1.5 rounded-lg text-slate-400 hover:text-red-600 hover:bg-red-50" title="Remover grupo"><Trash2 className="w-4 h-4" /></button>
                          </div>
                        </div>

                        {/* Opções do grupo */}
                        <div className="px-4 py-3 space-y-2">
                          <div className="flex items-center justify-between">
                            <p className="text-xs font-bold text-slate-500">Opções ({og.optionCount || 0})</p>
                            <button onClick={() => openNewOption(og.id)}
                              className="text-xs font-bold px-2.5 py-1 rounded-lg bg-purple-100 text-purple-700 hover:bg-purple-200 flex items-center gap-1">
                              <Plus className="w-3 h-3" />Adicionar
                            </button>
                          </div>

                          {/* Lista de options */}
                          {(!og.options || og.options.length === 0) ? (
                            <p className="text-xs text-slate-400 py-1">Nenhuma opção neste grupo.</p>
                          ) : (
                            <div className="space-y-1">
                              {og.options.map(opt => (
                                <div key={opt.id} className="flex items-center justify-between px-3 py-2 bg-white border border-slate-100 rounded-lg text-sm group">
                                  <div className="flex-1 min-w-0 flex items-center gap-2">
                                    <span className="w-1.5 h-1.5 rounded-full bg-purple-400 shrink-0"></span>
                                    <span className="text-slate-700 font-medium truncate">{opt.name}</span>
                                    {opt.price > 0 && <span className="text-xs text-indigo-600 font-bold shrink-0">+{formatCurrency(opt.price)}</span>}
                                    {opt.description && <span className="text-xs text-slate-300 truncate hidden sm:inline">{opt.description}</span>}
                                  </div>
                                  <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-all ml-2">
                                    <button onClick={() => openEditOption(og.id, opt)} className="p-1 rounded text-slate-300 hover:text-indigo-600 hover:bg-indigo-50" title="Editar"><Edit3 className="w-3.5 h-3.5" /></button>
                                    <button onClick={() => handleDeleteOption(og.id, opt.id, opt.name)} className="p-1 rounded text-slate-300 hover:text-red-600 hover:bg-red-50" title="Remover"><Trash2 className="w-3.5 h-3.5" /></button>
                                  </div>
                                </div>
                              ))}
                            </div>
                          )}

                          {/* Formulário inline para criar/editar option */}
                          {optionEditTarget && optionEditTarget.groupId === og.id && (
                            <form onSubmit={handleSaveOption} className="mt-2 p-3 bg-purple-50 rounded-lg border border-purple-200 space-y-2">
                              <p className="text-xs font-bold text-purple-700">{optionEditTarget.optionId ? 'Editar Opção' : 'Nova Opção'}</p>
                              <div className="flex gap-2">
                                <input type="text" placeholder="Nome da opção *" value={optionManagerForm.name}
                                  onChange={e => setOptionManagerForm({ ...optionManagerForm, name: e.target.value })}
                                  className="flex-1 px-2.5 py-1.5 text-sm border border-slate-200 rounded-lg" autoFocus />
                                <input type="number" step="0.01" placeholder="R$" value={optionManagerForm.price}
                                  onChange={e => setOptionManagerForm({ ...optionManagerForm, price: e.target.value })}
                                  className="w-24 px-2.5 py-1.5 text-sm border border-slate-200 rounded-lg" />
                              </div>
                              <div className="flex gap-2">
                                <input type="text" placeholder="Descrição" value={optionManagerForm.description}
                                  onChange={e => setOptionManagerForm({ ...optionManagerForm, description: e.target.value })}
                                  className="flex-1 px-2.5 py-1.5 text-sm border border-slate-200 rounded-lg" />
                                <input type="text" placeholder="Código externo" value={optionManagerForm.externalCode}
                                  onChange={e => setOptionManagerForm({ ...optionManagerForm, externalCode: e.target.value })}
                                  className="w-36 px-2.5 py-1.5 text-sm border border-slate-200 rounded-lg font-mono" />
                                <select value={optionManagerForm.status} onChange={e => setOptionManagerForm({ ...optionManagerForm, status: e.target.value })}
                                  className="w-28 px-2 py-1.5 text-sm border border-slate-200 rounded-lg">
                                  <option value="AVAILABLE">Disponível</option>
                                  <option value="UNAVAILABLE">Indisponível</option>
                                </select>
                              </div>
                              <div className="flex gap-2">
                                <button type="submit" disabled={optionManagerSaving}
                                  className={`px-3 py-1.5 rounded-lg text-xs font-bold flex items-center gap-1 ${optionManagerSaving ? 'bg-slate-300 cursor-not-allowed' : 'bg-purple-600 text-white hover:bg-purple-700'}`}>
                                  {optionManagerSaving ? <Loader2 className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />}
                                  {optionManagerSaving ? 'Salvando...' : optionEditTarget.optionId ? 'Atualizar' : 'Adicionar'}
                                </button>
                                <button type="button" onClick={() => setOptionEditTarget(null)}
                                  className="px-3 py-1.5 rounded-lg text-xs font-bold border border-slate-200 text-slate-600 hover:bg-slate-100">Cancelar</button>
                              </div>
                            </form>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}
