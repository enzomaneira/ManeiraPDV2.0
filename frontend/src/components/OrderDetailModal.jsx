import { useState } from 'react';
import { XCircle, CheckCircle, Bike, Ban, Zap, Navigation, User, Clock, DollarSign, Tag, MapPin, Phone, MessageCircle, ShieldAlert, RefreshCw, Store, Wallet, Package } from 'lucide-react';
import { formatCurrency, formatFullDate, formatTime } from '../utils/formatters';
import { STAGE_LABELS, isKeetaDelivery, nextOwnStages } from '../utils/deliveryStages';
import { orderService } from '../services/api';

const PAYMENT_METHOD_NAMES = {
    CREDIT: 'Cartão de crédito', DEBIT: 'Cartão de débito', CREDIT_DEBIT: 'Cartão', PIX: 'PIX', CASH: 'Dinheiro',
    MEAL_VOUCHER: 'Vale-refeição', FOOD_VOUCHER: 'Vale-alimentação', DIGITAL_WALLET: 'Carteira digital',
    COUPON: 'Cupom', REDEEM: 'Resgate', PREPAID_REDEEM: 'Resgate pré-pago', OTHER: 'Outro',
};

// Dígitos para links de telefone; números do Brasil sem DDI ganham o 55.
function phoneDigits(phone) {
    const digits = (phone || '').replace(/\D/g, '');
    if (!digits) return '';
    return phone.trim().startsWith('+') || digits.length > 11 ? digits : `55${digits}`;
}

// Botões das próximas etapas da entrega própria: a próxima em destaque e as
// demais como atalho (o motoboy da loja pode pular etapas).
const STAGE_BUTTON_ICONS = { PICKUP_ONGOING: Navigation, ARRIVED_AT_MERCHANT: Store, ORDER_PICKED: Package,
    DELIVERY_ONGOING: Bike, ARRIVED_AT_CUSTOMER: MapPin, ORDER_DELIVERED: CheckCircle };

function StageButtons({ stages, onPick, compact = false }) {
    const [next, ...others] = stages;
    const NextIcon = STAGE_BUTTON_ICONS[next] || Bike;
    if (compact) {
        return (
            <div className="mb-3 flex flex-wrap items-center gap-2">
                <span className="text-xs font-bold text-slate-400">Entregador:</span>
                {stages.map(stage => {
                    const Icon = STAGE_BUTTON_ICONS[stage] || Bike;
                    return (
                        <button key={stage} onClick={() => onPick(stage)}
                            className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-sky-50 text-sky-700 border border-sky-200 text-xs font-bold hover:bg-sky-100">
                            <Icon className="w-3.5 h-3.5"/> {STAGE_LABELS[stage]}
                        </button>
                    );
                })}
            </div>
        );
    }
    return (
        <div className="space-y-2">
            <button onClick={() => onPick(next)}
                className={`w-full py-4 text-white font-bold rounded-2xl shadow-xl transition-all flex items-center justify-center gap-2 text-lg ${next === 'ORDER_DELIVERED' ? 'bg-green-600 hover:bg-green-700 shadow-green-200' : 'bg-purple-600 hover:bg-purple-700 shadow-purple-200'}`}>
                <NextIcon className="w-6 h-6" /> {next === 'ORDER_DELIVERED' ? 'Entregue (finalizar)' : STAGE_LABELS[next]}
            </button>
            {others.length > 0 && (
                <div className="flex flex-wrap items-center justify-center gap-2">
                    <span className="text-xs font-bold text-slate-400">Pular para:</span>
                    {others.map(stage => (
                        <button key={stage} onClick={() => onPick(stage)}
                            className="px-2.5 py-1 rounded-lg border border-slate-200 text-xs font-bold text-slate-500 hover:bg-slate-50">
                            {stage === 'ORDER_DELIVERED' ? 'Entregue' : STAGE_LABELS[stage]}
                        </button>
                    ))}
                </div>
            )}
        </div>
    );
}

function CustomerSection({ order, mapUrl, onOrderUpdated }) {
    const [retrying, setRetrying] = useState(false);
    const [retryError, setRetryError] = useState(null);
    const details = order.addressDetails || {};
    const ownDelivery = order.deliveredBy === 'MERCHANT';
    const digits = phoneDigits(order.phone);
    const addressText = (order.address || '').toLowerCase();
    // Só repete complemento/referência se não estiverem já no endereço formatado
    const extraLines = [
        details.complement && !addressText.includes(details.complement.toLowerCase()) && ['Complemento', details.complement],
        details.reference && !addressText.includes(details.reference.toLowerCase()) && ['Referência', details.reference],
        details.postalCode && !addressText.includes(details.postalCode.toLowerCase()) && ['CEP', details.postalCode],
    ].filter(Boolean);

    const retry = async () => {
        setRetrying(true);
        setRetryError(null);
        try {
            const { data } = await orderService.retryDecrypt(order.id);
            onOrderUpdated?.(data);
            if (data.dataProtected) setRetryError('A Keeta ainda não liberou os dados. Tente de novo em alguns minutos.');
        } catch (error) {
            setRetryError(error.response?.data?.error || 'Não foi possível falar com a Keeta agora.');
        } finally {
            setRetrying(false);
        }
    };

    return (
        <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm space-y-4">
            <div className="flex items-center gap-2 border-b border-slate-50 pb-3 flex-wrap">
                <div className="p-1.5 bg-slate-100 rounded-full"><User className="w-4 h-4 text-slate-500"/></div>
                <span className="font-bold text-slate-700 text-lg">{order.customer}</span>
                {order.customerOrdersCount > 1 && (
                    <span className="text-[11px] text-slate-500 font-medium">{order.customerOrdersCount} pedidos na loja</span>
                )}
                {order.customerOrdersCount === 1 && (
                    <span className="text-[11px] text-emerald-600 font-bold">1º pedido na loja</span>
                )}
                {order.deliveredBy && (
                    <span className={`ml-auto flex items-center gap-1 text-[11px] font-bold uppercase tracking-wide px-2 py-1 rounded-lg border ${ownDelivery ? 'bg-indigo-50 text-indigo-700 border-indigo-200' : 'bg-slate-50 text-slate-500 border-slate-200'}`}>
                        {ownDelivery ? <><Store className="w-3 h-3"/> Entrega própria</> : <><Bike className="w-3 h-3"/> Entrega Keeta</>}
                    </span>
                )}
            </div>

            {order.dataProtected && (
                <div className="flex flex-col gap-2 p-3 rounded-xl bg-amber-50 border border-amber-200 text-amber-800 text-sm">
                    <p className="flex items-start gap-2 font-medium">
                        <ShieldAlert className="w-4 h-4 shrink-0 mt-0.5"/>
                        Telefone e endereço estão protegidos pela Keeta e não puderam ser abertos agora.
                    </p>
                    <button type="button" onClick={retry} disabled={retrying}
                        className="self-start flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white border border-amber-300 font-bold text-xs hover:bg-amber-100 disabled:opacity-60">
                        <RefreshCw className={`w-3.5 h-3.5 ${retrying ? 'animate-spin' : ''}`}/> {retrying ? 'Buscando na Keeta…' : 'Tentar novamente'}
                    </button>
                    {retryError && <p className="text-xs font-bold text-red-600">{retryError}</p>}
                </div>
            )}

            {order.deliveredBy === 'MARKETPLACE' && !order.phone && (
                <p className="flex items-start gap-2 text-xs text-slate-500">
                    <Bike className="w-4 h-4 shrink-0 text-slate-400"/>
                    O entregador da Keeta busca o pedido na loja. Telefone e endereço do cliente ficam só com a Keeta.
                </p>
            )}

            {order.phone && (
                <div className="flex gap-3 items-center flex-wrap">
                    <Phone className="w-5 h-5 text-emerald-600 shrink-0" />
                    <span className="text-sm text-slate-700 font-bold">
                        {order.phone}{order.phoneExtension && <span className="font-medium text-slate-500"> · ramal {order.phoneExtension}</span>}
                    </span>
                    <div className="flex gap-2 ml-auto">
                        <a href={`tel:+${digits}${order.phoneExtension ? `,${order.phoneExtension}` : ''}`}
                            className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-emerald-50 text-emerald-700 border border-emerald-200 text-xs font-bold hover:bg-emerald-100">
                            <Phone className="w-3.5 h-3.5"/> Ligar
                        </a>
                        {!order.phoneExtension && digits && (
                            <a href={`https://wa.me/${digits}`} target="_blank" rel="noopener noreferrer"
                                className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-green-50 text-green-700 border border-green-200 text-xs font-bold hover:bg-green-100">
                                <MessageCircle className="w-3.5 h-3.5"/> WhatsApp
                            </a>
                        )}
                    </div>
                </div>
            )}
            {order.phoneExtension && (
                <p className="text-[11px] text-slate-400 -mt-2 ml-8">Ao ligar, digite o ramal {order.phoneExtension} quando for pedido.</p>
            )}

            {(order.address || extraLines.length > 0) && (
                <div className="flex gap-3 items-start">
                    <MapPin className="w-5 h-5 text-red-500 shrink-0 mt-0.5" />
                    <div className="space-y-1">
                        {order.address && <p className="text-sm text-slate-600 leading-relaxed font-medium">{order.address}</p>}
                        {extraLines.map(([label, value]) => (
                            <p key={label} className="text-xs text-slate-500"><span className="font-bold text-slate-600">{label}:</span> {value}</p>
                        ))}
                    </div>
                </div>
            )}

            {order.customerDocument && (
                <p className="text-xs text-slate-500 ml-8"><span className="font-bold text-slate-600">CPF/CNPJ na nota:</span> {order.customerDocument}</p>
            )}

            {mapUrl && (
                <a href={mapUrl} target="_blank" rel="noopener noreferrer" className="flex items-center justify-center gap-2 w-full py-3 bg-blue-50 text-blue-600 font-bold rounded-xl hover:bg-blue-100 transition-colors text-sm border border-blue-100">
                    <Navigation className="w-4 h-4" /> Abrir Localização no Maps
                </a>
            )}
        </div>
    );
}

// "Dinheiro · troco para R$ 100,00 (levar R$ 48,41)"
function describePayment(method, total) {
    const name = PAYMENT_METHOD_NAMES[method.method] || method.method || 'Pagamento';
    let text = method.brand && method.brand !== 'OTHER' ? `${name} ${method.brand}` : name;
    if (method.methodInfo) text += ` (${method.methodInfo})`;
    if (method.method === 'CASH' && method.changeFor > 0) {
        const change = method.changeFor - (method.value ?? total ?? 0);
        text += ` · troco para ${formatCurrency(method.changeFor)}`;
        if (change > 0.009) text += ` (levar ${formatCurrency(change)} de troco)`;
    }
    return text;
}

export default function OrderDetailModal({ order, onClose, onStatusChange, onStageChange, onOrderUpdated, detailed = false }) {
    if (!order) return null;
    const keetaDelivery = isKeetaDelivery(order);
    const ownStages = detailed ? nextOwnStages(order) : [];

    const getHeaderColor = () => {
        switch(order.status) {
            case 'PENDING': return 'bg-amber-500';
            case 'NEW': return 'bg-blue-600';
            case 'PREPARING': return 'bg-orange-500';
            case 'READY': return 'bg-green-600';
            default: return 'bg-purple-600';
        }
    };

    const mapUrl = order.coordinates
        ? `https://www.google.com/maps/search/?api=1&query=${order.coordinates.lat},${order.coordinates.lng}`
        : order.address
            ? `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(order.address)}`
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
                        {order.pickupCode && (
                            <p className="opacity-80 text-xs mt-1 font-bold bg-white/10 px-2 py-0.5 rounded inline-block">
                                🏷️ Retirada: {order.pickupCode}
                            </p>
                        )}
                        {order.deliveryStage && (
                            <p className="text-xs mt-1 ml-1 font-bold bg-white/20 px-2 py-0.5 rounded inline-flex items-center gap-1">
                                <Bike className="w-3 h-3"/> {STAGE_LABELS[order.deliveryStage]}
                                {order.deliveryStageAt && <> · {formatTime(order.deliveryStageAt)}</>}
                                {order.deliveryStage === 'PICKUP_ONGOING' && order.pickupEta && <> · chega às {formatTime(order.pickupEta)}</>}
                            </p>
                        )}
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
                        {order.paymentMethods?.length > 0 && (
                            <div className="space-y-1">
                                {order.paymentMethods.map((method, idx) => (
                                    <p key={idx} className="flex items-start gap-1.5 text-xs text-slate-600">
                                        <Wallet className="w-3.5 h-3.5 text-slate-400 shrink-0 mt-px"/>
                                        <span>
                                            <b>{describePayment(method, order.total)}</b>
                                            {order.paymentMethods.length > 1 && <> · {formatCurrency(method.value)}</>}
                                            {method.type === 'PENDING' && <span className="text-yellow-700 font-bold"> · cobrar na entrega</span>}
                                        </span>
                                    </p>
                                ))}
                            </div>
                        )}
                    </div>

                    <CustomerSection order={order} mapUrl={mapUrl} onOrderUpdated={onOrderUpdated} />
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
                    {order.status === 'PREPARING' && ownStages.length > 0 && (
                        <StageButtons stages={ownStages} onPick={(stage) => onStageChange(order.id, stage)} compact />
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
                    {/* Entrega da Keeta: quem avança é o entregador dela (eventos da Keeta) */}
                    {(order.status === 'READY' || order.status === 'DISPATCHED') && keetaDelivery && (
                        <div className="space-y-2">
                            <div className="w-full py-3 px-4 bg-sky-50 text-sky-800 font-bold rounded-2xl border border-sky-100 flex items-center justify-center gap-2 text-sm text-center">
                                <Bike className="w-5 h-5 shrink-0" />
                                {order.deliveryStage ? STAGE_LABELS[order.deliveryStage] : 'Aguardando o entregador da Keeta'}
                                {order.deliveryStage === 'PICKUP_ONGOING' && order.pickupEta && <> · chega às {formatTime(order.pickupEta)}</>}
                            </div>
                            <button onClick={() => { if (window.confirm('Finalizar este pedido só no PDV? A Keeta não é avisada (a entrega é dela).')) onStatusChange(order.id, 'COMPLETED'); }}
                                className="w-full text-xs font-bold text-slate-400 hover:text-slate-600 py-1">
                                Finalizar manualmente no PDV
                            </button>
                        </div>
                    )}
                    {/* Entrega própria com etapas detalhadas */}
                    {(order.status === 'READY' || order.status === 'DISPATCHED') && !keetaDelivery && detailed && ownStages.length > 0 && (
                        <StageButtons stages={ownStages} onPick={(stage) => {
                            if (stage === 'ORDER_DELIVERED' && !window.confirm('Confirmar entrega do pedido?')) return;
                            onStageChange(order.id, stage);
                        }} />
                    )}
                    {/* Entrega própria no modo simples */}
                    {order.status === 'READY' && !keetaDelivery && !detailed && (
                        <div className="flex gap-4">
                            <button onClick={() => onStatusChange(order.id, 'DISPATCHED')} className="w-full py-4 bg-purple-600 text-white font-bold rounded-2xl hover:bg-purple-700 shadow-xl shadow-purple-200 transition-all flex items-center justify-center gap-2 text-lg">
                                <Bike className="w-6 h-6" /> Despachar Motoqueiro
                            </button>
                        </div>
                    )}
                    {order.status === 'DISPATCHED' && !keetaDelivery && !detailed && (
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