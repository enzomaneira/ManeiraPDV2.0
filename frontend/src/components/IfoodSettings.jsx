import { useEffect, useState } from 'react';
import { Loader2, CheckCircle, AlertCircle, Search, Link2, Unlink, Store, UtensilsCrossed } from 'lucide-react';
import api from '../services/api';

// Liga o restaurante selecionado à sua loja no iFood (merchantId).
// Mesmo visual do cartão "Integração Keeta", que fica ao lado.
export default function IfoodSettings() {
    const [status, setStatus] = useState(null);
    const [merchantId, setMerchantId] = useState('');
    const [merchants, setMerchants] = useState(null);
    const [busy, setBusy] = useState(false);
    const [message, setMessage] = useState(null);

    useEffect(() => {
        api.get('/ifood/status')
            .then(({ data }) => { setStatus(data); setMerchantId(data.merchantId || ''); })
            .catch(() => setStatus({ configured: false }));
    }, []);

    const run = async (fn) => {
        setBusy(true);
        setMessage(null);
        try { await fn(); } catch (error) {
            setMessage({ type: 'error', text: error.response?.data?.error || 'Não foi possível falar com o iFood agora.' });
        } finally { setBusy(false); }
    };

    const findStores = () => run(async () => {
        const { data } = await api.get('/ifood/merchants');
        setMerchants(data);
        if (!data.length) setMessage({ type: 'error', text: 'Nenhuma loja autorizou o app ainda.' });
    });

    const save = (id) => run(async () => {
        const { data } = await api.put('/ifood/merchant', { merchantId: id });
        setStatus(prev => ({ ...prev, merchantId: data.merchantId }));
        setMerchantId(data.merchantId || '');
        setMerchants(null);
        setMessage({ type: 'success', text: data.merchantId ? `Loja do iFood ligada${data.name ? `: ${data.name}` : ''}. Os pedidos dela passam a chegar no PDV.` : 'Loja do iFood desligada deste restaurante.' });
    });

    const connected = Boolean(status?.merchantId);

    return (
        <div className="bg-white p-6 rounded-2xl shadow-sm border border-slate-200 space-y-6">
            <div className="flex items-center gap-3 border-b border-slate-100 pb-4">
                <div className="p-2 bg-red-100 text-red-600 rounded-lg">
                    <UtensilsCrossed className="w-6 h-6" />
                </div>
                <div>
                    <h3 className="font-bold text-lg text-slate-800">Integração iFood</h3>
                    <p className="text-xs text-slate-400">Status da conexão com a plataforma</p>
                </div>
                <div className={`ml-auto px-3 py-1 rounded-full text-xs font-bold ${connected ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}`}>
                    {connected ? 'CONECTADO' : 'DESCONECTADO'}
                </div>
            </div>

            {!status ? (
                <Loader2 className="w-5 h-5 animate-spin text-slate-400" />
            ) : !status.configured ? (
                <p className="flex items-start gap-2 text-sm text-amber-700">
                    <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                    As credenciais do app do iFood ainda não foram configuradas no servidor.
                </p>
            ) : (
                <div className="space-y-4">
                    <div>
                        <label className="block text-sm font-bold text-slate-600 mb-2" htmlFor="ifood-merchant">ID da loja no iFood</label>
                        <div className="relative">
                            <Store className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
                            <input id="ifood-merchant" value={merchantId} onChange={e => setMerchantId(e.target.value)} placeholder="Ex: e769f5f1-8a2e-4f13-…"
                                className="w-full pl-10 pr-4 py-3 bg-slate-50 border border-slate-200 rounded-xl focus:ring-2 focus:ring-red-400 focus:outline-none font-medium text-slate-700 font-mono text-sm" />
                        </div>
                        <p className="text-[10px] text-slate-400 mt-1 ml-1">
                            Cada loja do iFood só pode estar em um restaurante. Não sabe o ID? Use “Ver as lojas que autorizaram o app”.
                        </p>
                    </div>

                    <button type="button" disabled={busy || !merchantId.trim()} onClick={() => save(merchantId.trim())}
                        className={`w-full py-3 font-bold rounded-xl transition-all flex items-center justify-center gap-2 shadow-sm ${busy || !merchantId.trim() ? 'bg-slate-300 text-slate-500 cursor-not-allowed' : 'bg-red-600 hover:bg-red-700 text-white shadow-red-100'}`}>
                        {busy ? <Loader2 className="w-5 h-5 animate-spin" /> : <Link2 className="w-5 h-5" />}
                        {busy ? 'Ligando...' : 'Ligar loja do iFood'}
                    </button>

                    <div className="flex flex-wrap items-center justify-between gap-2">
                        <button type="button" disabled={busy} onClick={findStores}
                            className="flex items-center gap-1.5 text-sm font-bold text-red-600 hover:underline disabled:opacity-50">
                            <Search className="w-4 h-4" /> Ver as lojas que autorizaram o app
                        </button>
                        {connected && (
                            <button type="button" disabled={busy} onClick={() => save('')}
                                className="flex items-center gap-1.5 text-sm font-bold text-slate-500 hover:text-slate-700 disabled:opacity-50">
                                <Unlink className="w-4 h-4" /> Desligar
                            </button>
                        )}
                    </div>

                    {merchants && merchants.length > 0 && (
                        <ul className="space-y-1 p-3 rounded-xl bg-slate-50 border border-slate-200">
                            {merchants.map(m => (
                                <li key={m.id} className="flex items-center gap-2 text-sm">
                                    <span className="flex-1 min-w-0 truncate"><b>{m.name || 'Loja'}</b> <span className="font-mono text-xs text-slate-500">{m.id}</span></span>
                                    <button type="button" onClick={() => save(m.id)} disabled={busy}
                                        className="px-2 py-1 rounded-lg border border-slate-200 bg-white text-xs font-bold text-slate-600 hover:bg-slate-100">Usar esta</button>
                                </li>
                            ))}
                        </ul>
                    )}
                </div>
            )}

            {message && (
                <p className={`flex items-start gap-2 text-sm font-bold ${message.type === 'success' ? 'text-green-700' : 'text-red-600'}`}>
                    {message.type === 'success' ? <CheckCircle className="w-4 h-4 shrink-0 mt-0.5" /> : <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />}
                    {message.text}
                </p>
            )}
        </div>
    );
}
