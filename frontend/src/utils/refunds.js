// Reembolsos da Keeta: textos usados no PDV.

// Motivos aceitos pela Keeta para recusar um reembolso
export const REJECT_CODES = [
  ['DISH_ALREADY_DONE', 'O prato já tinha sido preparado'],
  ['OUT_FOR_DELIVERY', 'O pedido já tinha saído para entrega'],
  ['OTHER', 'Outro motivo'],
];

// Texto curto do estado do reembolso (lista do histórico, aviso no topo)
export function refundLabel(refund) {
  if (!refund) return null;
  switch (refund.status) {
    case 'REQUESTED': return { text: 'Reembolso pedido', style: 'bg-amber-100 text-amber-800' };
    case 'ACCEPTED': return { text: 'Reembolso aceito', style: 'bg-sky-100 text-sky-800' };
    case 'REFUNDED': return { text: refund.partial ? 'Reembolso parcial' : 'Reembolsado', style: 'bg-violet-100 text-violet-800' };
    case 'REJECTED': return { text: 'Reembolso recusado', style: 'bg-slate-200 text-slate-700' };
    default: return null;
  }
}
