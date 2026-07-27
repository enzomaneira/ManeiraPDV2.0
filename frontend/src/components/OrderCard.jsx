import { Clock, User, Tag } from 'lucide-react';
import { formatCurrency, formatTime } from '../utils/formatters';

export default function OrderCard({ order, onClick }) {
  
  // --- LÓGICA DE CÁLCULO ROBUSTA ---
  
  // 1. Total Final (O que o cliente paga)
  // Já vem calculado corretamente do App.jsx (R$ 28,00)
  const finalPrice = order.total || 0;

  // 2. Cálculo do Preço Original (Para o risco)
  // Somamos o 'subtotal' de cada item (que no App.jsx definimos como originalPrice * qtd)
  const itemsOriginalSum = order.items.reduce((acc, item) => {
      return acc + (item.subtotal || 0); // Soma os 35,00
  }, 0);

  // Somamos as taxas
  const feesSum = (order.fees || []).reduce((acc, fee) => {
      return acc + (fee.price?.value || 0); // Soma os 3,00
  }, 0);

  // Preço Original Total = Soma dos Itens Originais + Taxas
  // Ex: 35 + 3 = 38
  const calculatedOriginalPrice = itemsOriginalSum + feesSum;

  // 3. Verifica se tem desconto
  // Se o Original (38) for maior que o Final (28), tem desconto
  const hasDiscount = calculatedOriginalPrice > (finalPrice + 0.05); // margem de 5 centavos
  const discountAmount = calculatedOriginalPrice - finalPrice;

  // --- CORES DE STATUS ---
  const getStatusColor = () => {
      if (order.status === 'READY') return 'bg-green-500';
      if (order.status === 'DISPATCHED') return 'bg-purple-500';
      if (order.status === 'CANCELED') return 'bg-red-500';
      return 'bg-blue-500';
  };

  return (
    <div 
      onClick={() => onClick(order)}
      className="bg-white p-4 rounded-2xl shadow-sm border border-slate-200 hover:shadow-md transition-all cursor-pointer group active:scale-95 relative overflow-hidden"
    >
      {/* Indicador lateral de status */}
      <div className={`absolute left-0 top-0 bottom-0 w-1 ${getStatusColor()}`}></div>

      {/* Cabeçalho */}
      <div className="flex justify-between items-start mb-3 pl-2">
        <div>
          <div className="bg-slate-100 px-2 py-1 rounded-lg border border-slate-200 group-hover:bg-indigo-50 group-hover:border-indigo-100 transition-colors inline-block">
            <span className="text-xs font-bold text-slate-500 group-hover:text-indigo-600">
              #{order.displayId}
            </span>
          </div>
          {order.pickupCode && (
            <div className="text-[10px] text-slate-400 mt-1 font-medium">
              🏷️ {order.pickupCode}
            </div>
          )}
        </div>
        <div className="flex items-center gap-1 text-xs font-medium text-slate-400">
          <Clock className="w-3 h-3" />
          {formatTime(order.time)}
        </div>
      </div>

      {/* Info Cliente */}
      <div className="mb-3 pl-2">
        <h4 className="font-bold text-slate-700 text-sm truncate">{order.customer}</h4>
        <div className="flex items-center gap-1 text-xs text-slate-400 mt-0.5">
            <User className="w-3 h-3" /> 
            <span className="truncate max-w-[150px]">{order.platform}</span>
        </div>
      </div>

      {/* Resumo de Itens */}
      <div className="space-y-1 mb-4 border-t border-slate-50 pt-3 pl-2">
        {order.items.slice(0, 2).map((item, index) => (
          <div key={index} className="flex justify-between text-xs text-slate-600">
            <div className="flex items-center gap-1 overflow-hidden">
                <span className="font-bold text-slate-700 bg-slate-100 px-1.5 py-0.5 rounded text-[10px]">{item.quantity}x</span>
                <span className="truncate">{item.name}</span>
            </div>
          </div>
        ))}
        {order.items.length > 2 && (
          <p className="text-xs text-slate-400 font-medium pl-1">
            +{order.items.length - 2} outros...
          </p>
        )}
      </div>

      {/* Footer: Preços */}
      <div className="flex items-end justify-between border-t border-slate-100 pt-3 pl-2">
        <div className="flex flex-col">
            
            {/* PREÇO ORIGINAL (MAIOR) RISCADO - Agora calculado manualmente */}
            {hasDiscount && (
                <div className="flex items-center gap-1 mb-0.5">
                    <span className="text-[11px] text-slate-400 line-through decoration-slate-400/50">
                        {formatCurrency(calculatedOriginalPrice)}
                    </span>
                    <span className="bg-green-100 text-green-700 text-[9px] font-bold px-1 rounded flex items-center">
                        <Tag className="w-2 h-2 mr-0.5" />
                        -{formatCurrency(discountAmount)}
                    </span>
                </div>
            )}

            {/* PREÇO FINAL (MENOR) EM DESTAQUE */}
            <span className="text-lg font-black text-slate-800 leading-none">
                {formatCurrency(finalPrice)}
            </span>
            
            <span className="text-[10px] font-bold text-slate-400 uppercase mt-1">
                {order.paymentType === 'ONLINE' ? 'Pago Online' : 'Na Entrega'}
            </span>
        </div>

        <div className={`w-2 h-2 rounded-full ${getStatusColor()}`}></div>
      </div>
    </div>
  );
}