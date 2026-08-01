import { useState, useEffect } from 'react';
import { categoryService, menuService } from '../services/api';
import {
  Plus, Trash2, Utensils, Loader2, AlertCircle, CheckCircle,
  PackageOpen, FolderPlus, Edit3, ChevronRight, Tag, Image, Layers,
  X, Save, FolderOpen
} from 'lucide-react';
import { formatCurrency } from '../utils/formatters';

export default function MenuPage() {
  // --- Dados ---
  const [categories, setCategories] = useState([]);
  const [items, setItems] = useState([]);
  const [selectedCategoryId, setSelectedCategoryId] = useState(null);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState(null);

  // --- Modal de categoria ---
  const [showCatModal, setShowCatModal] = useState(false);
  const [catForm, setCatForm] = useState({ name: '', description: '', externalCode: '' });
  const [catSaving, setCatSaving] = useState(false);
  const [editingCategory, setEditingCategory] = useState(null); // null = nova, obj = editando

  // --- Modal de item ---
  const [showItemModal, setShowItemModal] = useState(false);
  const [itemForm, setItemForm] = useState({
    name: '', description: '', externalCode: '', price: '', originalPrice: '',
    status: 'AVAILABLE', imageUrl: ''
  });
  const [itemSaving, setItemSaving] = useState(false);
  const [editingItem, setEditingItem] = useState(null); // null = novo, obj = editando

  // --- Deleting ---
  const [deletingId, setDeletingId] = useState(null);

  // ===== Carrega dados =====
  const fetchData = async () => {
    setLoading(true);
    try {
      const [catRes, itemRes] = await Promise.all([
        categoryService.getAll(),
        menuService.getAll(selectedCategoryId || undefined),
      ]);
      setCategories(catRes.data || []);
      setItems(itemRes.data || []);
    } catch (error) {
      console.error('Erro ao carregar cardápio:', error);
      setMessage({ type: 'error', text: 'Erro ao carregar dados.' });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchData(); }, []);
  useEffect(() => {
    if (!loading) fetchData();
  }, [selectedCategoryId]);

  // ===== Categoria: abrir modal =====
  const openNewCategory = () => {
    setEditingCategory(null);
    setCatForm({ name: '', description: '', externalCode: '' });
    setShowCatModal(true);
  };

  const openEditCategory = (cat) => {
    setEditingCategory(cat);
    setCatForm({
      name: cat.name,
      description: cat.description || '',
      externalCode: cat.externalCode,
    });
    setShowCatModal(true);
  };

  // ===== Categoria: salvar =====
  const handleSaveCategory = async (e) => {
    e.preventDefault();
    const name = catForm.name.trim();
    if (!name) {
      setMessage({ type: 'error', text: 'Nome da categoria é obrigatório.' });
      return;
    }

    setCatSaving(true);
    setMessage(null);
    try {
      if (editingCategory) {
        await categoryService.update(editingCategory.id, {
          name,
          description: catForm.description.trim(),
          externalCode: catForm.externalCode.trim() || `cat-${Date.now()}`,
        });
        setMessage({ type: 'success', text: `Categoria "${name}" atualizada!` });
      } else {
        await categoryService.create({
          name,
          description: catForm.description.trim(),
          externalCode: catForm.externalCode.trim() || `cat-${Date.now()}`,
        });
        setMessage({ type: 'success', text: `Categoria "${name}" criada!` });
      }
      setShowCatModal(false);
      fetchData();
    } catch (error) {
      console.error('Erro ao salvar categoria:', error);
      setMessage({ type: 'error', text: 'Erro ao salvar categoria.' });
    } finally {
      setCatSaving(false);
      setTimeout(() => setMessage(null), 3000);
    }
  };

  // ===== Categoria: deletar =====
  const handleDeleteCategory = async (cat) => {
    const itemCount = cat.itemCount || cat.items?.length || 0;
    const msg = itemCount > 0
      ? `Remover categoria "${cat.name}" e seus ${itemCount} item(ns)?`
      : `Remover categoria "${cat.name}"?`;
    if (!confirm(msg)) return;

    setDeletingId(cat.id);
    try {
      await categoryService.delete(cat.id);
      if (selectedCategoryId === cat.id) setSelectedCategoryId(null);
      setMessage({ type: 'success', text: `Categoria "${cat.name}" removida.` });
      fetchData();
    } catch (error) {
      console.error('Erro ao remover categoria:', error);
      setMessage({ type: 'error', text: 'Erro ao remover categoria.' });
    } finally {
      setDeletingId(null);
      setTimeout(() => setMessage(null), 3000);
    }
  };

  // ===== Item: abrir modal =====
  const openNewItem = () => {
    setEditingItem(null);
    setItemForm({
      name: '', description: '', externalCode: '', price: '', originalPrice: '',
      status: 'AVAILABLE', imageUrl: ''
    });
    setShowItemModal(true);
  };

  const openEditItem = (item) => {
    setEditingItem(item);
    setItemForm({
      name: item.name,
      description: item.description || '',
      externalCode: item.externalCode,
      price: String(item.price || ''),
      originalPrice: String(item.originalPrice || item.price || ''),
      status: item.status || 'AVAILABLE',
      imageUrl: item.imageUrl || '',
    });
    setShowItemModal(true);
  };

  // ===== Item: salvar =====
  const handleSaveItem = async (e) => {
    e.preventDefault();
    const name = itemForm.name.trim();
    const price = parseFloat(itemForm.price);
    if (!name) { setMessage({ type: 'error', text: 'Nome é obrigatório.' }); return; }
    if (isNaN(price) || price < 0) { setMessage({ type: 'error', text: 'Preço inválido.' }); return; }

    setItemSaving(true);
    setMessage(null);

    const payload = {
      name,
      description: itemForm.description.trim(),
      externalCode: itemForm.externalCode.trim() || String(Date.now()),
      price,
      originalPrice: parseFloat(itemForm.originalPrice) || price,
      status: itemForm.status,
      imageUrl: itemForm.imageUrl.trim(),
      categoryId: selectedCategoryId || null,
    };

    try {
      if (editingItem) {
        await menuService.update(editingItem.id, payload);
        setMessage({ type: 'success', text: `"${name}" atualizado!` });
      } else {
        await menuService.create(payload);
        setMessage({ type: 'success', text: `"${name}" adicionado!` });
      }
      setShowItemModal(false);
      fetchData();
    } catch (error) {
      console.error('Erro ao salvar item:', error);
      setMessage({ type: 'error', text: 'Erro ao salvar item.' });
    } finally {
      setItemSaving(false);
      setTimeout(() => setMessage(null), 3000);
    }
  };

  // ===== Item: deletar =====
  const handleDeleteItem = async (item) => {
    if (!confirm(`Remover "${item.name}" do cardápio?`)) return;
    setDeletingId(item.id);
    try {
      await menuService.delete(item.id);
      setMessage({ type: 'success', text: `"${item.name}" removido.` });
      fetchData();
    } catch (error) {
      console.error('Erro ao remover item:', error);
      setMessage({ type: 'error', text: 'Erro ao remover item.' });
    } finally {
      setDeletingId(null);
      setTimeout(() => setMessage(null), 3000);
    }
  };

  // ===== Estatísticas =====
  const avgPrice = items.length > 0
    ? items.reduce((s, i) => s + i.price, 0) / items.length
    : 0;

  const selectedCategory = categories.find(c => c.id === selectedCategoryId);

  return (
    <div className="max-w-6xl mx-auto animate-in fade-in slide-in-from-bottom-4 space-y-6 pb-10">

      {/* ================================================================= */}
      {/*  CABEÇALHO                                                         */}
      {/* ================================================================= */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-slate-800">Cardápio da Loja</h2>
          <p className="text-slate-500">
            Organize categorias e itens para sincronizar com a Keeta.
          </p>
        </div>
        <div className="flex items-center gap-4 text-sm font-bold text-slate-500">
          <span className="px-3 py-1.5 bg-white rounded-lg border border-slate-200 shadow-sm">
            {categories.length} {categories.length === 1 ? 'categoria' : 'categorias'}
          </span>
          <span className="px-3 py-1.5 bg-white rounded-lg border border-slate-200 shadow-sm">
            {items.length} {items.length === 1 ? 'item' : 'itens'}
          </span>
          {items.length > 0 && (
            <span className="px-3 py-1.5 bg-white rounded-lg border border-slate-200 shadow-sm text-indigo-600">
              Média {formatCurrency(avgPrice)}
            </span>
          )}
        </div>
      </div>

      {/* Mensagem de feedback */}
      {message && (
        <div className={`p-4 rounded-xl flex items-center gap-2 font-bold animate-in fade-in slide-in-from-top-2 ${
          message.type === 'success' ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'
        }`}>
          {message.type === 'success' ? <CheckCircle className="w-5 h-5" /> : <AlertCircle className="w-5 h-5" />}
          {message.text}
        </div>
      )}

      {/* ================================================================= */}
      {/*  LAYOUT PRINCIPAL: Sidebar de categorias + Área de itens           */}
      {/* ================================================================= */}
      <div className="flex gap-6">
        {/* ------------------------------------------------------------- */}
        {/*  SIDEBAR: Lista de categorias                                  */}
        {/* ------------------------------------------------------------- */}
        <div className="w-64 shrink-0 space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="font-bold text-sm text-slate-500 uppercase tracking-wider">
              <Layers className="w-4 h-4 inline mr-1" />
              Categorias
            </h3>
            <button
              onClick={openNewCategory}
              className="p-1.5 rounded-lg text-indigo-500 hover:bg-indigo-50 transition-all"
              title="Nova categoria"
            >
              <FolderPlus className="w-4 h-4" />
            </button>
          </div>

          {/* Botão "Todas" */}
          <button
            onClick={() => setSelectedCategoryId(null)}
            className={`w-full text-left px-3 py-2.5 rounded-xl transition-all font-medium text-sm flex items-center gap-2 ${
              selectedCategoryId === null
                ? 'bg-indigo-50 text-indigo-700 border border-indigo-200'
                : 'text-slate-600 hover:bg-slate-100 border border-transparent'
            }`}
          >
            <FolderOpen className="w-4 h-4 shrink-0" />
            <span className="truncate">Todas ({items.length})</span>
          </button>

          {/* Lista de categorias */}
          <div className="space-y-1 max-h-[50vh] overflow-y-auto pr-1">
            {loading ? (
              <div className="flex items-center justify-center py-8 text-slate-400">
                <Loader2 className="w-5 h-5 animate-spin" />
              </div>
            ) : categories.length === 0 ? (
              <p className="text-xs text-slate-400 py-4 text-center">
                Nenhuma categoria ainda.<br/>Clique em + para criar.
              </p>
            ) : (
              categories.map(cat => (
                <div key={cat.id} className="group relative">
                  <button
                    onClick={() => setSelectedCategoryId(cat.id)}
                    className={`w-full text-left px-3 py-2.5 rounded-xl transition-all font-medium text-sm flex items-center gap-2 ${
                      selectedCategoryId === cat.id
                        ? 'bg-indigo-50 text-indigo-700 border border-indigo-200'
                        : 'text-slate-600 hover:bg-slate-100 border border-transparent'
                    }`}
                  >
                    <ChevronRight className={`w-3.5 h-3.5 shrink-0 transition-transform ${selectedCategoryId === cat.id ? 'rotate-90' : ''}`} />
                    <span className="truncate flex-1">{cat.name}</span>
                    <span className="text-xs text-slate-400 shrink-0">{cat.itemCount || cat.items?.length || 0}</span>
                  </button>
                  {/* Ações hover */}
                  <div className="absolute right-1 top-1/2 -translate-y-1/2 hidden group-hover:flex items-center gap-0.5 bg-white rounded-lg shadow-sm border border-slate-200 px-1 py-0.5">
                    <button
                      onClick={(e) => { e.stopPropagation(); openEditCategory(cat); }}
                      className="p-1 rounded text-slate-400 hover:text-indigo-600 hover:bg-indigo-50"
                      title="Editar"
                    >
                      <Edit3 className="w-3.5 h-3.5" />
                    </button>
                    <button
                      onClick={(e) => { e.stopPropagation(); handleDeleteCategory(cat); }}
                      disabled={deletingId === cat.id}
                      className="p-1 rounded text-slate-400 hover:text-red-600 hover:bg-red-50 disabled:opacity-50"
                      title="Remover"
                    >
                      {deletingId === cat.id ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Trash2 className="w-3.5 h-3.5" />}
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* ------------------------------------------------------------- */}
        {/*  ÁREA PRINCIPAL: Itens da categoria selecionada                */}
        {/* ------------------------------------------------------------- */}
        <div className="flex-1 min-w-0">
          <div className="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden">
            {/* Cabeçalho */}
            <div className="px-6 py-4 border-b border-slate-100 bg-slate-50/50 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className={`p-2 rounded-lg ${selectedCategory ? 'bg-amber-100 text-amber-700' : 'bg-indigo-100 text-indigo-700'}`}>
                  {selectedCategory ? <Layers className="w-5 h-5" /> : <Utensils className="w-5 h-5" />}
                </div>
                <div>
                  <h3 className="font-bold text-lg text-slate-800">
                    {selectedCategory ? selectedCategory.name : 'Todos os Itens'}
                  </h3>
                  <p className="text-xs text-slate-400">
                    {selectedCategory
                      ? `${selectedCategory.description || 'Sem descrição'} · Código: ${selectedCategory.externalCode}`
                      : 'Itens de todas as categorias'}
                  </p>
                </div>
              </div>
              <button
                onClick={openNewItem}
                className="flex items-center gap-2 px-4 py-2 rounded-xl font-bold text-sm bg-indigo-600 hover:bg-indigo-700 text-white shadow-md shadow-indigo-200 transition-all active:scale-[0.98]"
              >
                <Plus className="w-4 h-4" />
                Novo Item
              </button>
            </div>

            {/* Loading */}
            {loading && (
              <div className="flex items-center justify-center py-20 text-slate-400">
                <Loader2 className="w-8 h-8 animate-spin mr-3" />
                <span className="font-medium">Carregando...</span>
              </div>
            )}

            {/* Empty */}
            {!loading && items.length === 0 && (
              <div className="flex flex-col items-center justify-center py-20 text-slate-400">
                <PackageOpen className="w-16 h-16 mb-4 text-slate-300" />
                <p className="font-bold text-lg text-slate-500 mb-1">
                  {selectedCategory ? 'Categoria vazia' : 'Cardápio vazio'}
                </p>
                <p className="text-sm mb-6">
                  {selectedCategory
                    ? 'Nenhum item nesta categoria. Clique em "Novo Item".'
                    : 'Crie uma categoria e depois adicione itens.'}
                </p>
              </div>
            )}

            {/* Lista de itens */}
            {!loading && items.length > 0 && (
              <div className="divide-y divide-slate-100">
                {items.map((item) => (
                  <div
                    key={item.id}
                    className="flex items-center justify-between px-6 py-4 hover:bg-slate-50 transition-colors group"
                  >
                    {/* Info */}
                    <div className="flex items-center gap-4 min-w-0 flex-1">
                      <div className="w-12 h-12 rounded-xl bg-indigo-50 flex items-center justify-center shrink-0 overflow-hidden">
                        {item.imageUrl ? (
                          <img src={item.imageUrl} alt="" className="w-full h-full object-cover" />
                        ) : (
                          <Utensils className="w-6 h-6 text-indigo-400" />
                        )}
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <p className="font-bold text-slate-800 truncate">{item.name}</p>
                          {item.status !== 'AVAILABLE' && (
                            <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-red-100 text-red-600 font-bold shrink-0">
                              {item.status}
                            </span>
                          )}
                        </div>
                        <div className="flex items-center gap-3 text-xs text-slate-400 mt-0.5">
                          {item.description && (
                            <span className="truncate max-w-[200px]">{item.description}</span>
                          )}
                          <span className="flex items-center gap-1">
                            <Tag className="w-3 h-3" />
                            {item.externalCode}
                          </span>
                          {item.categoryName && (
                            <span className="flex items-center gap-1 text-indigo-500">
                              <Layers className="w-3 h-3" />
                              {item.categoryName}
                            </span>
                          )}
                        </div>
                      </div>
                    </div>

                    {/* Preço + ações */}
                    <div className="flex items-center gap-4 shrink-0 ml-4">
                      <div className="text-right">
                        <span className="text-lg font-extrabold text-indigo-600 tabular-nums">
                          {formatCurrency(item.price)}
                        </span>
                        {item.originalPrice && item.originalPrice !== item.price && (
                          <span className="block text-xs text-slate-400 line-through">
                            {formatCurrency(item.originalPrice)}
                          </span>
                        )}
                      </div>

                      <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-all">
                        <button
                          onClick={() => openEditItem(item)}
                          className="p-2 rounded-xl text-slate-300 hover:text-indigo-600 hover:bg-indigo-50"
                          title="Editar item"
                        >
                          <Edit3 className="w-4 h-4" />
                        </button>
                        <button
                          onClick={() => handleDeleteItem(item)}
                          disabled={deletingId === item.id}
                          className="p-2 rounded-xl text-slate-300 hover:text-red-600 hover:bg-red-50 disabled:opacity-50"
                          title="Remover item"
                        >
                          {deletingId === item.id ? (
                            <Loader2 className="w-4 h-4 animate-spin text-red-400" />
                          ) : (
                            <Trash2 className="w-4 h-4" />
                          )}
                        </button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ================================================================= */}
      {/*  MODAL: Criar/Editar Categoria                                     */}
      {/* ================================================================= */}
      {showCatModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm animate-in fade-in">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md p-6 animate-in zoom-in-95">
            <div className="flex items-center justify-between mb-5">
              <h3 className="font-bold text-lg text-slate-800">
                {editingCategory ? 'Editar Categoria' : 'Nova Categoria'}
              </h3>
              <button onClick={() => setShowCatModal(false)} className="p-2 rounded-lg hover:bg-slate-100 text-slate-400">
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleSaveCategory} className="space-y-4">
              <div>
                <label className="block text-sm font-bold text-slate-600 mb-1.5">Nome *</label>
                <input
                  type="text"
                  value={catForm.name}
                  onChange={(e) => setCatForm({ ...catForm, name: e.target.value })}
                  placeholder="Ex: Pizzas, Bebidas..."
                  className="w-full px-4 py-2.5 bg-slate-50 border border-slate-200 rounded-xl focus:ring-2 focus:ring-indigo-400 focus:outline-none font-medium text-slate-700"
                  autoFocus
                />
              </div>
              <div>
                <label className="block text-sm font-bold text-slate-600 mb-1.5">Descrição</label>
                <input
                  type="text"
                  value={catForm.description}
                  onChange={(e) => setCatForm({ ...catForm, description: e.target.value })}
                  placeholder="Breve descrição da categoria"
                  className="w-full px-4 py-2.5 bg-slate-50 border border-slate-200 rounded-xl focus:ring-2 focus:ring-indigo-400 focus:outline-none font-medium text-slate-700"
                />
              </div>
              <div>
                <label className="block text-sm font-bold text-slate-600 mb-1.5">
                  <Tag className="w-3.5 h-3.5 inline mr-1" />
                  Código Externo (PDV Code)
                </label>
                <input
                  type="text"
                  value={catForm.externalCode}
                  onChange={(e) => setCatForm({ ...catForm, externalCode: e.target.value })}
                  placeholder="Ex: cat-pizzas"
                  className="w-full px-4 py-2.5 bg-slate-50 border border-slate-200 rounded-xl focus:ring-2 focus:ring-indigo-400 focus:outline-none font-mono text-sm text-slate-700"
                />
              </div>
              <div className="flex gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setShowCatModal(false)}
                  className="flex-1 py-2.5 font-bold rounded-xl border border-slate-200 text-slate-600 hover:bg-slate-50 transition-all"
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  disabled={catSaving}
                  className={`flex-1 py-2.5 font-bold rounded-xl transition-all flex items-center justify-center gap-2 ${
                    catSaving
                      ? 'bg-slate-300 text-slate-500 cursor-not-allowed'
                      : 'bg-indigo-600 hover:bg-indigo-700 text-white shadow-md shadow-indigo-200'
                  }`}
                >
                  {catSaving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                  {catSaving ? 'Salvando...' : editingCategory ? 'Atualizar' : 'Criar Categoria'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ================================================================= */}
      {/*  MODAL: Criar/Editar Item                                          */}
      {/* ================================================================= */}
      {showItemModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm animate-in fade-in">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg p-6 animate-in zoom-in-95 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-5">
              <h3 className="font-bold text-lg text-slate-800">
                {editingItem ? 'Editar Item' : 'Novo Item'}
                {selectedCategory && <span className="text-sm font-normal text-slate-400 ml-2">· {selectedCategory.name}</span>}
              </h3>
              <button onClick={() => setShowItemModal(false)} className="p-2 rounded-lg hover:bg-slate-100 text-slate-400">
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleSaveItem} className="space-y-4">
              <div>
                <label className="block text-sm font-bold text-slate-600 mb-1.5">Nome do Produto *</label>
                <input
                  type="text"
                  value={itemForm.name}
                  onChange={(e) => setItemForm({ ...itemForm, name: e.target.value })}
                  placeholder="Ex: Pizza Margherita"
                  className="w-full px-4 py-2.5 bg-slate-50 border border-slate-200 rounded-xl focus:ring-2 focus:ring-indigo-400 focus:outline-none font-medium text-slate-700"
                  autoFocus
                />
              </div>

              <div>
                <label className="block text-sm font-bold text-slate-600 mb-1.5">Descrição</label>
                <textarea
                  value={itemForm.description}
                  onChange={(e) => setItemForm({ ...itemForm, description: e.target.value })}
                  placeholder="Descreva o produto..."
                  rows={2}
                  className="w-full px-4 py-2.5 bg-slate-50 border border-slate-200 rounded-xl focus:ring-2 focus:ring-indigo-400 focus:outline-none font-medium text-slate-700 resize-none"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-sm font-bold text-slate-600 mb-1.5">
                    <Tag className="w-3.5 h-3.5 inline mr-1" />
                    Código Externo
                  </label>
                  <input
                    type="text"
                    value={itemForm.externalCode}
                    onChange={(e) => setItemForm({ ...itemForm, externalCode: e.target.value })}
                    placeholder="PDV Code"
                    className="w-full px-4 py-2.5 bg-slate-50 border border-slate-200 rounded-xl focus:ring-2 focus:ring-indigo-400 focus:outline-none font-mono text-sm text-slate-700"
                  />
                </div>
                <div>
                  <label className="block text-sm font-bold text-slate-600 mb-1.5">Status</label>
                  <select
                    value={itemForm.status}
                    onChange={(e) => setItemForm({ ...itemForm, status: e.target.value })}
                    className="w-full px-4 py-2.5 bg-slate-50 border border-slate-200 rounded-xl focus:ring-2 focus:ring-indigo-400 focus:outline-none font-medium text-slate-700"
                  >
                    <option value="AVAILABLE">Disponível</option>
                    <option value="UNAVAILABLE">Indisponível</option>
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-sm font-bold text-slate-600 mb-1.5">Preço (R$) *</label>
                  <input
                    type="number" step="0.01" min="0"
                    value={itemForm.price}
                    onChange={(e) => setItemForm({ ...itemForm, price: e.target.value })}
                    placeholder="29,90"
                    className="w-full px-4 py-2.5 bg-slate-50 border border-slate-200 rounded-xl focus:ring-2 focus:ring-indigo-400 focus:outline-none font-bold text-slate-700"
                  />
                </div>
                <div>
                  <label className="block text-sm font-bold text-slate-600 mb-1.5">Preço Original</label>
                  <input
                    type="number" step="0.01" min="0"
                    value={itemForm.originalPrice}
                    onChange={(e) => setItemForm({ ...itemForm, originalPrice: e.target.value })}
                    placeholder="Igual ao preço"
                    className="w-full px-4 py-2.5 bg-slate-50 border border-slate-200 rounded-xl focus:ring-2 focus:ring-indigo-400 focus:outline-none font-bold text-slate-700"
                  />
                </div>
              </div>

              <div>
                <label className="block text-sm font-bold text-slate-600 mb-1.5">
                  <Image className="w-3.5 h-3.5 inline mr-1" />
                  URL da Imagem
                </label>
                <input
                  type="url"
                  value={itemForm.imageUrl}
                  onChange={(e) => setItemForm({ ...itemForm, imageUrl: e.target.value })}
                  placeholder="https://..."
                  className="w-full px-4 py-2.5 bg-slate-50 border border-slate-200 rounded-xl focus:ring-2 focus:ring-indigo-400 focus:outline-none font-mono text-sm text-slate-700"
                />
              </div>

              <div className="flex gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setShowItemModal(false)}
                  className="flex-1 py-2.5 font-bold rounded-xl border border-slate-200 text-slate-600 hover:bg-slate-50 transition-all"
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  disabled={itemSaving}
                  className={`flex-1 py-2.5 font-bold rounded-xl transition-all flex items-center justify-center gap-2 ${
                    itemSaving
                      ? 'bg-slate-300 text-slate-500 cursor-not-allowed'
                      : 'bg-indigo-600 hover:bg-indigo-700 text-white shadow-md shadow-indigo-200'
                  }`}
                >
                  {itemSaving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                  {itemSaving ? 'Salvando...' : editingItem ? 'Atualizar' : 'Criar Item'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
