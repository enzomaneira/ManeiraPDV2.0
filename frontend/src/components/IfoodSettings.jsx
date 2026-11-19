import { useEffect, useState } from 'react';
import { Loader2, CheckCircle, AlertCircle, Search, Link2, Unlink } from 'lucide-react';
import api from '../services/api';

// Liga o restaurante selecionado à sua loja no iFood (merchantId).
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
        setMessage({ type: 'success', text: data.merchantId ? `Loja do iFood ligada${data.name ? `: ${data.name}` : ''}. Os pedidos dela passam a chegar no PDV.` : 'Loja do iFood desligada deste restaurante.' });
    });

    if (!status) return null;

    return (
        <div className="bg-white p-6 rounded-2xl shadow-sm border border-slate-200">
            <div className="flex items-center gap-3 border-b border-slate-100 pb-4">
                <div className="p-2 bg-red-100 text-red-600 rounded-lg font-black text-sm w-10 h-10 flex items-center justify-center">iF</div>
                <div className="flex-1">
                    <h3 className="font-bold text-lg text-slate-800">Integração iFood</h3>
                    <p className="text-xs text-slate-400">Loja do iFood deste restaurante</p>
                </div>
                <span className={`text-xs font-bold px-2 py-1 rounded-lg ${status.merchantId ? 'bg-green-100 text-green-700' : 'bg-slate-100 text-slate-500'}`}>
                    {status.merchantId ? 'LIGADA' : 'NÃO LIGADA'}
                </span>
            </div>

            {!status.configured ? (
                <p className="mt-4 flex items-start gap-2 text-sm text-amber-700">
                    <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                    As credenciais do app do iFood ainda não foram configuradas no servidor.
                </p>
            ) : (
                <div className="mt-4 space-y-3">
                    <label className="block text-sm font-bold text-slate-700" htmlFor="ifood-merchant">ID da loja no iFood (merchantId)</label>
                    <div className="flex flex-wrap gap-2">
                        <input id="ifood-merchant" value={merchantId} onChange={e => setMerchantId(e.target.value)} placeholder="Ex.: 3f2c1a…"
                            className="flex-1 min-w-[220px] px-3 py-2 rounded-lg border border-slate-200 text-sm font-mono" />
                        <button type="button" disabled={busy || !merchantId.trim()} onClick={() => save(merchantId.trim())}
                            className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-red-600 text-white text-sm font-bold hover:bg-red-700 disabled:opacity-50">
                            {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Link2 className="w-4 h-4" />} Ligar loja
                        </button>
                        {status.merchantId && (
                            <button type="button" disabled={busy} onClick={() => save('')}
                                className="flex items-center gap-1.5 px-3 py-2 rounded-lg border border-slate-200 text-sm font-bold text-slate-500 hover:bg-slate-50">
                                <Unlink className="w-4 h-4" /> Desligar
                            </button>
                        )}
                    </div>
                    <button type="button" disabled={busy} onClick={findStores}
                        className="flex items-center gap-1.5 text-sm font-bold text-red-600 hover:underline disabled:opacity-50">
                        <Search className="w-4 h-4" /> Ver as lojas que autorizaram o app
                    </button>
                    {merchants && merchants.length > 0 && (
                        <ul className="space-y-1">
                            {merchants.map(m => (
                                <li key={m.id} className="flex items-center gap-2 text-sm">
                                    <span className="flex-1 truncate"><b>{m.name || 'Loja'}</b> <span className="font-mono text-xs text-slate-500">{m.id}</span></span>
                                    <button type="button" onClick={() => save(m.id)} disabled={busy}
                                        className="px-2 py-1 rounded-lg border border-slate-200 text-xs font-bold text-slate-600 hover:bg-slate-50">Usar esta</button>
                                </li>
                            ))}
                        </ul>
                    )}
                </div>
            )}

            {message && (
                <p className={`mt-3 flex items-start gap-2 text-sm font-bold ${message.type === 'success' ? 'text-green-700' : 'text-red-600'}`}>
                    {message.type === 'success' ? <CheckCircle className="w-4 h-4 shrink-0 mt-0.5" /> : <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />}
                    {message.text}
                </p>
            )}
        </div>
    );
}
