import { Undo2, ChevronRight } from 'lucide-react';
import { formatCurrency } from '../utils/formatters';

// Faixa no topo do PDV quando um cliente pediu reembolso e a loja ainda não respondeu.
export default function RefundAlert({ orders, onSelectOrder }) {
  const waiting = orders.filter(order => order.refund?.status === 'REQUESTED');
  if (waiting.length === 0) return null;
  return (
    <div role="alert" className="mx-8 mt-4 p-3 rounded-xl bg-amber-50 border border-amber-300 flex flex-wrap items-center gap-2 text-sm text-amber-900">
      <Undo2 className="w-5 h-5 text-amber-600 shrink-0" />
      <span className="font-bold">
        {waiting.length === 1 ? 'Um cliente pediu reembolso.' : `${waiting.length} clientes pediram reembolso.`}
      </span>
      <span className="text-amber-800">Responda para a Keeta:</span>
      {waiting.map(order => (
        <button key={order.id} type="button" onClick={() => onSelectOrder(order)}
          className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-white border border-amber-300 font-bold text-xs hover:bg-amber-100">
          #{order.displayId}{order.refund.amount != null && <> · {formatCurrency(order.refund.amount)}</>}
          <ChevronRight className="w-3.5 h-3.5" />
        </button>
      ))}
    </div>
  );
}
