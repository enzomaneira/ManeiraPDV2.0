import { useState } from 'react';
import { Undo2, CheckCircle, Ban, Loader2, Clock, Image as ImageIcon } from 'lucide-react';
import { formatCurrency, formatFullDate } from '../utils/formatters';
import { orderService } from '../services/api';
import { REJECT_CODES } from '../utils/refunds';

const STATUS_TEXT = {
  ACCEPTED: 'Você aceitou o reembolso. A Keeta devolve o dinheiro ao cliente e confirma em instantes.',
  REFUNDED: 'Reembolso concluído pela Keeta.',
  REJECTED: 'Reembolso recusado.',
};

// Pedido de reembolso do cliente (Keeta), com aceitar/recusar enquanto espera resposta.
export default function RefundPanel({ order, onOrderUpdated }) {
  const refund = order.refund;
  const [busy, setBusy] = useState(null); // 'accept' | 'reject'
  const [error, setError] = useState(null);
  const [rejecting, setRejecting] = useState(false);
  const [code, setCode] = useState('DISH_ALREADY_DONE');
  const [reason, setReason] = useState('');
  if (!refund) return null;
  const waiting = refund.status === 'REQUESTED';

  const run = async (kind) => {
    setBusy(kind);
    setError(null);
    try {
      const { data } = kind === 'accept'
        ? await orderService.acceptRefund(order.id)
        : await orderService.rejectRefund(order.id, code, reason.trim());
      setRejecting(false);
      onOrderUpdated?.(data.order);
    } catch (err) {
      setError(err.response?.data?.error || 'Não foi possível responder o reembolso agora.');
    } finally {
      setBusy(null);
    }
  };

  const accept = () => {
    const amount = refund.amount != null ? formatCurrency(refund.amount) : 'o valor pedido';
    if (window.confirm(`Aceitar o reembolso de ${amount}? O dinheiro volta para o cliente e isso não dá para desfazer.`)) run('accept');
  };

  return (
    <section aria-label="Reembolso" className={`p-4 rounded-xl border space-y-3 ${waiting ? 'bg-amber-50 border-amber-300' : 'bg-white border-slate-200'}`}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <h3 className="font-bold text-slate-800 flex items-center gap-2">
          <Undo2 className={`w-5 h-5 ${waiting ? 'text-amber-600' : 'text-slate-500'}`} />
          {waiting ? 'O cliente pediu reembolso' : 'Reembolso'}
        </h3>
        <div className="text-right">
          {refund.amount != null && <p className="text-lg font-black text-slate-800">{formatCurrency(refund.amount)}</p>}
          <p className="text-[11px] font-bold text-slate-500">{refund.partial ? 'Só alguns itens' : 'Pedido inteiro'}</p>
        </div>
      </div>
      {refund.reason && <p className="text-sm text-slate-700"><b>Motivo do cliente:</b> {refund.reason}</p>}
      {refund.items?.length > 0 && (
        <ul className="text-xs text-slate-600 space-y-0.5">
          {refund.items.map((item, index) => (
            <li key={index}>{item.count}x {item.name}{item.price != null && <span className="text-slate-400"> · {formatCurrency(item.price)}</span>}</li>
          ))}
        </ul>
      )}
      {refund.pictures?.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {refund.pictures.map((url, index) => (
            <a key={url} href={url} target="_blank" rel="noopener noreferrer" title="Abrir foto do cliente"
              className="flex items-center gap-1 px-2 py-1 rounded-lg bg-white border border-slate-200 text-xs font-bold text-slate-600 hover:bg-slate-50">
              <ImageIcon className="w-3.5 h-3.5" /> Foto {index + 1}
            </a>
          ))}
        </div>
      )}
      {refund.requestedAt && (
        <p className="flex items-center gap-1 text-[11px] text-slate-500"><Clock className="w-3 h-3" /> Pedido em {formatFullDate(refund.requestedAt)}</p>
      )}

      {!waiting && STATUS_TEXT[refund.status] && (
        <p className={`text-sm font-bold ${refund.status === 'REJECTED' ? 'text-slate-600' : 'text-sky-800'}`}>
          {STATUS_TEXT[refund.status]}
          {refund.status === 'REJECTED' && refund.decision?.reason && <span className="font-medium"> Motivo: {refund.decision.reason}</span>}
        </p>
      )}

      {waiting && !rejecting && (
        <div className="flex flex-wrap gap-2 pt-1">
          <button type="button" onClick={accept} disabled={Boolean(busy)}
            className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-green-600 text-white text-sm font-bold hover:bg-green-700 disabled:opacity-60">
            {busy === 'accept' ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle className="w-4 h-4" />} Aceitar reembolso
          </button>
          <button type="button" onClick={() => setRejecting(true)} disabled={Boolean(busy)}
            className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-white border border-slate-300 text-slate-700 text-sm font-bold hover:bg-slate-50 disabled:opacity-60">
            <Ban className="w-4 h-4" /> Recusar
          </button>
        </div>
      )}
      {waiting && rejecting && (
        <div className="space-y-2 pt-1">
          <label className="block text-xs font-bold text-slate-600" htmlFor="refund-code">Por que você recusa?</label>
          <select id="refund-code" value={code} onChange={e => setCode(e.target.value)}
            className="w-full px-3 py-2 bg-white border border-slate-300 rounded-lg text-sm">
            {REJECT_CODES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
          <textarea value={reason} onChange={e => setReason(e.target.value)} maxLength={300} rows={2}
            placeholder="Explique para o cliente (opcional)" aria-label="Explicação da recusa"
            className="w-full px-3 py-2 bg-white border border-slate-300 rounded-lg text-sm resize-none" />
          <div className="flex flex-wrap gap-2">
            <button type="button" onClick={() => run('reject')} disabled={Boolean(busy)}
              className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-red-600 text-white text-sm font-bold hover:bg-red-700 disabled:opacity-60">
              {busy === 'reject' ? <Loader2 className="w-4 h-4 animate-spin" /> : <Ban className="w-4 h-4" />} Recusar reembolso
            </button>
            <button type="button" onClick={() => setRejecting(false)} disabled={Boolean(busy)}
              className="px-4 py-2 rounded-xl text-sm font-bold text-slate-500 hover:bg-slate-100">Voltar</button>
          </div>
        </div>
      )}
      {error && <p className="text-xs font-bold text-red-600">{error}</p>}
    </section>
  );
}
