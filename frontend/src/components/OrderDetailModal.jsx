import { XCircle, CheckCircle, Bike, Ban, Zap, Navigation, User, Clock, DollarSign, Tag, MapPin } from 'lucide-react';
import { formatCurrency, formatFullDate } from '../utils/formatters';

export default function OrderDetailModal({ order, onClose, onStatusChange }) {
    if (!order) return null;

    const getHeaderColor = () => {
        switch(order.status) {
            case 'PENDING': return 'bg-amber-500';
            case 'NEW': return 'bg-blue-600';
            case 'PREPARING': return 'bg-orange-500';
            case 'READY': return 'bg-green-600';
            default: return 'bg-purple-600';
        }
    };

    const mapUrl = order.coordinates?.lat 
        ? `https://www.google.com/maps/search/?api=1&query=${order.coordinates.lat},${order.coordinates.lng}`
        : null;

    return (
        <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <div className="bg-white rounded-3xl shadow-2xl w-full max-w-2xl flex flex-col max-h-[90vh] animate-in zoom-in-95 duration-200">
                
                {/* Header */}
                <div className={`p-6 text-white flex justify-between items-start rounded-t-3xl ${getHeaderColor()}`}>
                    <div>
                        <div className="flex items-center gap-3">
                            <span className="text-sm font-medium opacity-80 uppercase tracking-widest bg-black/10 px-2 py-1 rounded">Código</span>
                            <h2 className="text-4xl font-black tracking-tighter">{order.displayId}</h2>
                        </div>
                        <p className="opacity-90 text-xs mt-2 flex items-center gap-1 font-medium">
                            <Clock className="w-3 h-3"/> {formatFullDate(order.createdAt)}
                        </p>
                    </div>
                    <button onClick={onClose} className="bg-white/20 hover:bg-white/30 p-2 rounded-full transition-colors">
                        <XCircle className="w-6 h-6" />
                    </button>
                </div>

                {/* Body */}
                <div className="p-6 overflow-y-auto space-y-6 bg-slate-50/50">
                    
                    {/* Itens */}
                    <div className="space-y-3">
                        <h3 className="font-bold text-slate-700 flex items-center gap-2 text-sm uppercase tracking-wide">
                            <ShoppingBagIcon className="w-4 h-4"/> Itens do Pedido
                        </h3>
                        <div className="space-y-2">
                            {order.items.map((item, idx) => {
                                // Lógica de Exibição do Desconto
                                // Se o preço original (35) for maior que o preço pago (25), mostra o risco.
                                const hasDiscount = (item.originalPrice > item.price);

                                return (
                                    <div key={idx} className="flex justify-between items-start p-3 rounded-xl bg-white border border-slate-200 shadow-sm">
                                        <div className="flex gap-4 items-center">
                                            <span className="w-8 h-8 flex items-center justify-center bg-slate-100 rounded-lg text-sm font-bold text-slate-700 border border-slate-200">{item.quantity}x</span>
                                            <div>
                                                <span className="font-bold text-slate-700 text-sm block">{item.name}</span>
                                                <div className="flex items-center gap-2">
                                                    <span className="text-xs text-slate-500 font-medium">
                                                        Unit: {formatCurrency(item.price)}
                                                    </span>
                                                    {hasDiscount && (
                                                        <span className="text-[10px] text-slate-400 line-through decoration-red-300">
                                                            {formatCurrency(item.originalPrice)}
                                                        </span>
                                                    )}
                                                </div>
                                            </div>
                                        </div>
                                        
                                        <div className="text-right">
                                            {/* Valor Total Pago (Em destaque) */}
                                            <span className="font-bold text-slate-800 text-sm block">
                                                {formatCurrency(item.total)}
                                            </span>
                                            
                                            {/* Valor Total Original (Riscado abaixo) */}
                                            {hasDiscount && (
                                                <span className="text-xs text-slate-400 line-through block decoration-slate-300">
                                                    {formatCurrency(item.subtotal)}
                                                </span>
                                            )}
                                        </div>
                                    </div>
                                );
                            })}
                        </div>
                    </div>

                    {/* Resumo Financeiro */}
                    <div className="bg-white p-5 rounded-xl border border-slate-200 space-y-3 text-sm shadow-sm">
                        <h3 className="font-bold text-slate-700 text-xs uppercase tracking-wide mb-2">Resumo Financeiro</h3>
                        
                        <div className="flex justify-between text-slate-500">
                            <span>Subtotal Itens</span>
                            <span>{formatCurrency(order.items.reduce((acc, i) => acc + i.total, 0))}</span>
                        </div>

                        {order.fees && order.fees.map((fee, idx) => {
                            // Mapeia o type da Keeta para um nome legível em português
                            const feeTypeNames = {
                                'SERVICE_FEE': 'Taxa de Serviço (Marketplace)',
                                'DELIVERY_FEE': 'Taxa de Entrega',
                                'MIN_ORDER_FEE': 'Suplemento Pedido Mínimo',
                            };
                            const feeName = feeTypeNames[fee.type] || (fee.type || 'Taxa').replace(/_/g, ' ').toLowerCase();
                            return (
                                <div key={idx} className="flex justify-between text-slate-500">
                                    <span className="flex items-center gap-1 capitalize text-xs">
                                        <DollarSign className="w-3 h-3 text-slate-400"/> 
                                        {feeName}
                                    </span>
                                    <span>+ {formatCurrency(fee.price?.value || fee.value || 0)}</span>
                                </div>
                            );
                        })}

                        {order.discounts && order.discounts.map((disc, idx) => {
                            const discValue = disc.amount?.value || disc.value || 0;
                            const sponsors = disc.sponsorshipValues || [];
                            const merchantSponsor = sponsors.find(s => s.name === 'MERCHANT');
                            const marketplaceSponsor = sponsors.find(s => s.name === 'MARKETPLACE');
                            return (
                                <div key={idx} className="flex justify-between text-red-500">
                                    <span className="flex items-center gap-1 text-xs">
                                        <Tag className="w-3 h-3"/> 
                                        Desconto{sponsors.length > 0 ? ' (Cupom)' : ''}
                                    </span>
                                    <div className="text-right">
                                        <span>- {formatCurrency(Math.abs(discValue))}</span>
                                        {sponsors.length > 0 && (
                                            <div className="text-[10px] text-slate-400 mt-0.5 space-y-0.5">
                                                {merchantSponsor && (
                                                    <div>🏪 Loja banca: -{formatCurrency(Math.abs(merchantSponsor.amount?.value || 0))}</div>
                                                )}
                                                {marketplaceSponsor && (
                                                    <div>📱 Keeta banca: -{formatCurrency(Math.abs(marketplaceSponsor.amount?.value || 0))}</div>
                                                )}
                                            </div>
                                        )}
                                    </div>
                                </div>
                            );
                        })}

                        <div className="border-t border-slate-100 pt-3 flex justify-between items-end">
                            <span className="text-slate-500 font-bold">Total Final</span>
                            <span className="text-2xl font-black text-slate-800 tracking-tight">{formatCurrency(order.total)}</span>
                        </div>
                        
                        <div className={`mt-3 py-2 px-3 rounded-lg text-center text-xs font-bold uppercase tracking-wide border ${order.paymentType === 'ONLINE' ? 'bg-green-50 text-green-700 border-green-200' : 'bg-yellow-50 text-yellow-700 border-yellow-200'}`}>
                            {order.paymentType === 'ONLINE' ? '✅ PAGO ONLINE (Não Cobrar)' : '⚠️ COBRAR NA ENTREGA'}
                        </div>
                    </div>

                    {/* Info Cliente */}
                    <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm space-y-4">
                        <div className="flex items-center gap-2 border-b border-slate-50 pb-3">
                            <div className="p-1.5 bg-slate-100 rounded-full"><User className="w-4 h-4 text-slate-500"/></div>
                            <span className="font-bold text-slate-700 text-lg">{order.customer}</span>
                        </div>
                        <div className="flex gap-3 items-start">
                            <MapPin className="w-5 h-5 text-red-500 shrink-0 mt-0.5" />
                            <div>
                                <p className="text-sm text-slate-600 leading-relaxed font-medium">
                                    {order.address}
                                </p>
                            </div>
                        </div>
                        {mapUrl && (
                            <a href={mapUrl} target="_blank" rel="noopener noreferrer" className="flex items-center justify-center gap-2 w-full py-3 bg-blue-50 text-blue-600 font-bold rounded-xl hover:bg-blue-100 transition-colors text-sm border border-blue-100">
                                <Navigation className="w-4 h-4" /> Abrir Localização no Maps
                            </a>
                        )}
                    </div>
                </div>

                {/* Footer (Botões) */}
                <div className="p-6 bg-white border-t border-slate-100 rounded-b-3xl">
                    {(order.status === 'PENDING' || order.status === 'NEW') && (
                        <div className="flex gap-4">
                            <button onClick={() => { if(window.confirm('Recusar este pedido? O cliente será notificado do cancelamento.')) onStatusChange(order.id, 'CANCELED'); }} className="w-1/3 py-4 bg-white border-2 border-red-200 text-red-500 font-bold rounded-2xl hover:bg-red-50 hover:text-red-600 hover:border-red-300 transition-all flex items-center justify-center gap-2">
                                <Ban className="w-5 h-5" /> Recusar
                            </button>
                            <button onClick={() => onStatusChange(order.id, 'PREPARING')} className="w-2/3 py-4 bg-blue-600 text-white font-bold rounded-2xl hover:bg-blue-700 shadow-xl shadow-blue-200 transition-all flex items-center justify-center gap-2 text-lg">
                                <Zap className="w-6 h-6" /> Aceitar Pedido
                            </button>
                        </div>
                    )}
                    {order.status === 'PREPARING' && (
                         <div className="flex gap-4">
                            <button onClick={() => { if(window.confirm('Cancelar este pedido?')) onStatusChange(order.id, 'CANCELED'); }} className="w-1/3 py-4 bg-white border-2 border-slate-100 text-red-400 font-bold rounded-2xl hover:bg-red-50 hover:text-red-600 hover:border-red-200 transition-all flex items-center justify-center gap-2">
                                <Ban className="w-5 h-5" /> Cancelar
                            </button>
                            <button onClick={() => onStatusChange(order.id, 'READY')} className="w-2/3 py-4 bg-green-600 text-white font-bold rounded-2xl hover:bg-green-700 shadow-xl shadow-green-200 transition-all flex items-center justify-center gap-2 text-lg">
                                <CheckCircle className="w-6 h-6" /> Pronto
                            </button>
                        </div>
                    )}
                    {order.status === 'READY' && (
                        <div className="flex gap-4">
                            <button onClick={() => onStatusChange(order.id, 'DISPATCHED')} className="w-full py-4 bg-purple-600 text-white font-bold rounded-2xl hover:bg-purple-700 shadow-xl shadow-purple-200 transition-all flex items-center justify-center gap-2 text-lg">
                                <Bike className="w-6 h-6" /> Despachar Motoqueiro
                            </button>
                        </div>
                    )}
                    {order.status === 'DISPATCHED' && (
                        <div className="flex gap-4">
                            <button onClick={() => { if(window.confirm('Confirmar entrega do pedido?')) onStatusChange(order.id, 'COMPLETED'); }} className="w-full py-4 bg-green-600 text-white font-bold rounded-2xl hover:bg-green-700 shadow-xl shadow-green-200 transition-all flex items-center justify-center gap-2 text-lg">
                                <CheckCircle className="w-6 h-6" /> Finalizar Entrega
                            </button>
                        </div>
                    )}
                    {order.status === 'COMPLETED' && (
                        <div className="w-full py-3 bg-slate-50 text-slate-400 font-bold rounded-xl text-center flex items-center justify-center gap-2 border border-slate-100">
                            <CheckCircle className="w-4 h-4"/> Pedido Finalizado
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}

function ShoppingBagIcon(props) {
    return (
      <svg {...props} xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M6 2 3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4Z"/><path d="M3 6h18"/><path d="M16 10a4 4 0 0 1-8 0"/></svg>
    )
}