import { useState, useRef, useEffect } from 'react';
import { Store, ChevronDown, Check, Plus, Loader2 } from 'lucide-react';
import { storeService, selectStore } from '../services/api';

// Seletor do restaurante (marca) da conta. Cardápio e Configurações agem sobre
// o restaurante selecionado; o quadro de pedidos mostra todas as marcas.
export default function StoreSwitcher({ user }) {
    const [open, setOpen] = useState(false);
    const [adding, setAdding] = useState(false);
    const [name, setName] = useState('');
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState(null);
    const box = useRef(null);
    const stores = user?.stores || [];

    useEffect(() => {
        if (!open) return undefined;
        const close = (event) => { if (box.current && !box.current.contains(event.target)) setOpen(false); };
        document.addEventListener('mousedown', close);
        return () => document.removeEventListener('mousedown', close);
    }, [open]);

    // Recarrega a página: Cardápio, Configurações e o estado do PDV guardam
    // os dados do restaurante anterior.
    const switchTo = (storeId) => {
        if (storeId === user?.storeId) { setOpen(false); return; }
        selectStore(storeId);
        window.location.reload();
    };

    const create = async (event) => {
        event.preventDefault();
        setSaving(true);
        setError(null);
        try {
            const { data } = await storeService.create(name.trim());
            selectStore(data.id);
            window.location.reload();
        } catch (err) {
            setError(err.response?.data?.error || 'Não foi possível criar o restaurante.');
            setSaving(false);
        }
    };

    return (
        <div ref={box} className="relative px-4 pt-4 hidden md:block">
            <p className="px-1 mb-1 text-[10px] font-bold uppercase tracking-widest text-slate-500">Restaurante</p>
            <button type="button" onClick={() => setOpen(!open)} aria-expanded={open}
                className="w-full flex items-center gap-2 px-3 py-2.5 rounded-xl bg-slate-800 hover:bg-slate-700 border border-slate-700 text-left transition-colors">
                <Store className="w-4 h-4 text-indigo-300 shrink-0" />
                <span className="flex-1 min-w-0 text-sm font-semibold truncate">{user?.storeName || 'Sem restaurante'}</span>
                <ChevronDown className={`w-4 h-4 text-slate-400 transition-transform ${open ? 'rotate-180' : ''}`} />
            </button>

            {open && (
                <div className="absolute left-4 right-4 mt-2 z-30 bg-white text-slate-700 rounded-xl shadow-2xl border border-slate-200 overflow-hidden">
                    <ul className="max-h-64 overflow-y-auto py-1">
                        {stores.map(store => (
                            <li key={store.id}>
                                <button type="button" onClick={() => switchTo(store.id)}
                                    className="w-full flex items-center gap-2 px-3 py-2 text-sm hover:bg-slate-50 text-left">
                                    <span className="flex-1 min-w-0 truncate font-medium">{store.name}</span>
                                    {store.id === user?.storeId && <Check className="w-4 h-4 text-indigo-600" />}
                                </button>
                            </li>
                        ))}
                    </ul>
                    <div className="border-t border-slate-100 p-2">
                        {adding ? (
                            <form onSubmit={create} className="space-y-2">
                                <input autoFocus value={name} onChange={e => setName(e.target.value)} maxLength={150}
                                    placeholder="Nome da nova marca" aria-label="Nome do novo restaurante"
                                    className="w-full px-3 py-2 rounded-lg border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
                                {error && <p className="text-xs font-bold text-red-600">{error}</p>}
                                <div className="flex gap-2">
                                    <button type="button" onClick={() => { setAdding(false); setError(null); }}
                                        className="flex-1 px-3 py-1.5 rounded-lg border border-slate-200 text-xs font-bold text-slate-500 hover:bg-slate-50">Cancelar</button>
                                    <button type="submit" disabled={saving || !name.trim()}
                                        className="flex-1 flex items-center justify-center gap-1 px-3 py-1.5 rounded-lg bg-indigo-600 text-white text-xs font-bold hover:bg-indigo-700 disabled:opacity-50">
                                        {saving && <Loader2 className="w-3 h-3 animate-spin" />} Criar
                                    </button>
                                </div>
                            </form>
                        ) : (
                            <button type="button" onClick={() => setAdding(true)}
                                className="w-full flex items-center gap-2 px-2 py-1.5 rounded-lg text-sm font-bold text-indigo-600 hover:bg-indigo-50">
                                <Plus className="w-4 h-4" /> Adicionar restaurante
                            </button>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
}
