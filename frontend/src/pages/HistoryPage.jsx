import { History, Search, Calendar, Ban, CheckCircle } from 'lucide-react';
import { formatCurrency, formatFullDate } from '../utils/formatters';

export default function HistoryPage({ orders }) {
    
    // FILTRO ATUALIZADO: Mostra Cancelados OU Completados (Entregues)
    // Nota: Se quiser mostrar os que estão "Saiu para Entrega" aqui também, adicione || o.status === 'DISPATCHED'
    const historyOrders = orders.filter(o => o.status === 'COMPLETED' || o.status === 'CANCELED');

    // Ordenar do mais recente para o mais antigo
    const sortedOrders = [...historyOrders].sort((a, b) => new Date(b.time) - new Date(a.time));

    return (
        <div className="max-w-5xl mx-auto bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden animate-in fade-in slide-in-from-bottom-4">
            <div className="p-6 border-b border-slate-100 flex justify-between items-center">
                <h3 className="text-lg font-bold text-slate-700 flex items-center gap-2">
                    <History className="w-5 h-5" /> Histórico de Pedidos
                </h3>
                <div className="relative">
                    <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                    <input type="text" placeholder="Buscar..." className="pl-9 pr-4 py-2 bg-slate-50 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 w-64" />
                </div>
            </div>
            
            <div className="overflow-x-auto">
                <table className="w-full text-left text-sm text-slate-600">
                    <thead className="bg-slate-50 text-xs uppercase font-bold text-slate-500">
                        <tr>
                            <th className="px-6 py-4">ID</th>
                            <th className="px-6 py-4">Data/Hora</th>
                            <th className="px-6 py-4">Cliente</th>
                            <th className="px-6 py-4">Plataforma</th>
                            <th className="px-6 py-4">Total</th>
                            <th className="px-6 py-4">Status</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                        {sortedOrders.length === 0 ? (
                            <tr>
                                <td colSpan="6" className="px-6 py-12 text-center text-slate-400">
                                    Nenhum pedido finalizado ainda.
                                </td>
                            </tr>
                        ) : (
                            sortedOrders.map((order) => (
                                <tr key={order.id} className="hover:bg-slate-50 transition-colors">
                                    <td className="px-6 py-4 font-bold">#{order.displayId || order.id}</td>
                                    <td className="px-6 py-4 flex items-center gap-2">
                                        <Calendar className="w-4 h-4 text-slate-400" /> {formatFullDate(order.time)}
                                    </td>
                                    <td className="px-6 py-4 font-medium text-slate-900">{order.customer}</td>
                                    <td className="px-6 py-4">
                                        <span className="px-2 py-1 bg-yellow-100 text-yellow-800 rounded text-xs font-bold">{order.platform}</span>
                                    </td>
                                    <td className="px-6 py-4 font-bold text-slate-700">{formatCurrency(order.total)}</td>
                                    <td className="px-6 py-4">
                                        {order.status === 'CANCELED' ? (
                                            <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-bold bg-red-100 text-red-700">
                                                <Ban className="w-3 h-3"/> Cancelado
                                            </span>
                                        ) : (
                                            <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-bold bg-green-100 text-green-700">
                                                <CheckCircle className="w-3 h-3"/> Entregue
                                            </span>
                                        )}
                                    </td>
                                </tr>
                            ))
                        )}
                    </tbody>
                </table>
            </div>
        </div>
    );
}