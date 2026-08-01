import { useState, useEffect } from 'react';
import { menuService } from '../services/api';
import { Plus, Trash2, Utensils, Loader2, AlertCircle, CheckCircle, PackageOpen } from 'lucide-react';
import { formatCurrency } from '../utils/formatters';

export default function MenuPage() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(null); // ID do item sendo deletado
  const [message, setMessage] = useState(null);

  // --- Form state ---
  const [newName, setNewName] = useState('');
  const [newPrice, setNewPrice] = useState('');

  // Busca os itens do cardápio ao montar
  const fetchMenu = async () => {
    setLoading(true);
    try {
      const res = await menuService.getAll();
      setItems(res.data || []);
    } catch (error) {
      console.error('Erro ao buscar cardápio:', error);
      setMessage({ type: 'error', text: 'Erro ao carregar o cardápio.' });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchMenu();
  }, []);

  // --- Adicionar novo item ---
  const handleAddItem = async (e) => {
    e.preventDefault();
    const name = newName.trim();
    const price = parseFloat(newPrice);

    if (!name) {
      setMessage({ type: 'error', text: 'Informe o nome do item.' });
      return;
    }
    if (isNaN(price) || price <= 0) {
      setMessage({ type: 'error', text: 'Informe um preço válido (maior que zero).' });
      return;
    }

    setSaving(true);
    setMessage(null);

    try {
      const res = await menuService.create(name, price);
      setItems(prev => [...prev, res.data]);
      setNewName('');
      setNewPrice('');
      setMessage({ type: 'success', text: `"${name}" adicionado ao cardápio!` });
    } catch (error) {
      console.error('Erro ao adicionar item:', error);
      setMessage({ type: 'error', text: 'Erro ao adicionar item. Verifique o backend.' });
    } finally {
      setSaving(false);
      setTimeout(() => setMessage(null), 3000);
    }
  };

  // --- Remover item ---
  const handleDeleteItem = async (itemId, itemName) => {
    if (!confirm(`Remover "${itemName}" do cardápio?`)) return;

    setDeleting(itemId);
    setMessage(null);

    try {
      await menuService.delete(itemId);
      setItems(prev => prev.filter(i => i.id !== itemId));
      setMessage({ type: 'success', text: `"${itemName}" removido.` });
    } catch (error) {
      console.error('Erro ao remover item:', error);
      setMessage({ type: 'error', text: 'Erro ao remover item.' });
    } finally {
      setDeleting(null);
      setTimeout(() => setMessage(null), 3000);
    }
  };

  // --- Agrupa itens por faixa de preço para estatísticas ---
  const avgPrice = items.length > 0
    ? items.reduce((sum, i) => sum + i.price, 0) / items.length
    : 0;

  return (
    <div className="max-w-5xl mx-auto animate-in fade-in slide-in-from-bottom-4 space-y-6 pb-10">

      {/* Cabeçalho */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-slate-800">Cardápio da Loja</h2>
          <p className="text-slate-500">Gerencie os itens disponíveis para venda.</p>
        </div>
        {items.length > 0 && (
          <div className="flex items-center gap-4 text-sm font-bold text-slate-500">
            <span className="px-3 py-1.5 bg-white rounded-lg border border-slate-200 shadow-sm">
              {items.length} {items.length === 1 ? 'item' : 'itens'}
            </span>
            <span className="px-3 py-1.5 bg-white rounded-lg border border-slate-200 shadow-sm text-indigo-600">
              Média {formatCurrency(avgPrice)}
            </span>
          </div>
        )}
      </div>

      {/* Mensagem de Feedback */}
      {message && (
        <div className={`p-4 rounded-xl flex items-center gap-2 font-bold animate-in fade-in slide-in-from-top-2 ${
          message.type === 'success' ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'
        }`}>
          {message.type === 'success' ? <CheckCircle className="w-5 h-5" /> : <AlertCircle className="w-5 h-5" />}
          {message.text}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* ================================================================= */}
        {/*  COLUNA DA ESQUERDA: FORMULÁRIO DE NOVO ITEM                        */}
        {/* ================================================================= */}
        <div className="lg:col-span-1">
          <div className="bg-white p-6 rounded-2xl shadow-sm border border-slate-200 sticky top-28">
            <div className="flex items-center gap-3 border-b border-slate-100 pb-4 mb-5">
              <div className="p-2 bg-indigo-100 text-indigo-700 rounded-lg">
                <Plus className="w-5 h-5" />
              </div>
              <div>
                <h3 className="font-bold text-lg text-slate-800">Novo Item</h3>
                <p className="text-xs text-slate-400">Adicione ao cardápio</p>
              </div>
            </div>

            <form onSubmit={handleAddItem} className="space-y-4">
              {/* Nome do item */}
              <div>
                <label className="block text-sm font-bold text-slate-600 mb-2">
                  Nome do Produto
                </label>
                <input
                  type="text"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  placeholder="Ex: Hambúrguer Artesanal"
                  disabled={saving}
                  className="w-full px-4 py-3 bg-slate-50 border border-slate-200 rounded-xl
                             focus:ring-2 focus:ring-indigo-400 focus:outline-none
                             font-medium text-slate-700 placeholder-slate-400
                             disabled:opacity-50 disabled:cursor-not-allowed"
                />
              </div>

              {/* Preço */}
              <div>
                <label className="block text-sm font-bold text-slate-600 mb-2">
                  Preço (R$)
                </label>
                <div className="relative">
                  <span className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400 font-bold">
                    R$
                  </span>
                  <input
                    type="number"
                    step="0.01"
                    min="0.01"
                    value={newPrice}
                    onChange={(e) => setNewPrice(e.target.value)}
                    placeholder="29,90"
                    disabled={saving}
                    className="w-full pl-12 pr-4 py-3 bg-slate-50 border border-slate-200 rounded-xl
                               focus:ring-2 focus:ring-indigo-400 focus:outline-none
                               font-bold text-slate-700 placeholder-slate-400
                               disabled:opacity-50 disabled:cursor-not-allowed"
                  />
                </div>
              </div>

              {/* Botão de adicionar */}
              <button
                type="submit"
                disabled={saving}
                className={`w-full py-3 font-bold rounded-xl transition-all flex items-center justify-center gap-2 shadow-md ${
                  saving
                    ? 'bg-slate-300 text-slate-500 cursor-not-allowed'
                    : 'bg-indigo-600 hover:bg-indigo-700 text-white shadow-indigo-200 active:scale-[0.98]'
                }`}
              >
                {saving ? (
                  <>
                    <Loader2 className="w-5 h-5 animate-spin" />
                    Adicionando...
                  </>
                ) : (
                  <>
                    <Plus className="w-5 h-5" />
                    Adicionar ao Cardápio
                  </>
                )}
              </button>
            </form>
          </div>
        </div>

        {/* ================================================================= */}
        {/*  COLUNA DA DIREITA: LISTA DE ITENS                                 */}
        {/* ================================================================= */}
        <div className="lg:col-span-2">
          <div className="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden">
            {/* Cabeçalho da tabela */}
            <div className="px-6 py-4 border-b border-slate-100 bg-slate-50/50">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-amber-100 text-amber-700 rounded-lg">
                  <Utensils className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="font-bold text-lg text-slate-800">Itens do Cardápio</h3>
                  <p className="text-xs text-slate-400">
                    Estes itens serão sincronizados com a Keeta via menu endpoint.
                  </p>
                </div>
              </div>
            </div>

            {/* Loading state */}
            {loading && (
              <div className="flex items-center justify-center py-20 text-slate-400">
                <Loader2 className="w-8 h-8 animate-spin mr-3" />
                <span className="font-medium">Carregando cardápio...</span>
              </div>
            )}

            {/* Empty state */}
            {!loading && items.length === 0 && (
              <div className="flex flex-col items-center justify-center py-20 text-slate-400">
                <PackageOpen className="w-16 h-16 mb-4 text-slate-300" />
                <p className="font-bold text-lg text-slate-500 mb-1">Cardápio vazio</p>
                <p className="text-sm mb-6">Nenhum item cadastrado ainda. Adicione o primeiro!</p>
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
                    {/* Info do item */}
                    <div className="flex items-center gap-4 min-w-0">
                      <div className="w-10 h-10 rounded-xl bg-indigo-50 flex items-center justify-center shrink-0">
                        <Utensils className="w-5 h-5 text-indigo-500" />
                      </div>
                      <div className="min-w-0">
                        <p className="font-bold text-slate-800 truncate">{item.name}</p>
                        <p className="text-xs text-slate-400">
                          ID: {item.id} · Store: {item.storeId}
                        </p>
                      </div>
                    </div>

                    {/* Preço + ações */}
                    <div className="flex items-center gap-4 shrink-0">
                      <span className="text-lg font-extrabold text-indigo-600 tabular-nums">
                        {formatCurrency(item.price)}
                      </span>

                      <button
                        onClick={() => handleDeleteItem(item.id, item.name)}
                        disabled={deleting === item.id}
                        title="Remover item"
                        className="p-2.5 rounded-xl text-slate-300 hover:text-red-600 hover:bg-red-50
                                   opacity-0 group-hover:opacity-100 transition-all
                                   disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        {deleting === item.id ? (
                          <Loader2 className="w-5 h-5 animate-spin text-red-400" />
                        ) : (
                          <Trash2 className="w-5 h-5" />
                        )}
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
