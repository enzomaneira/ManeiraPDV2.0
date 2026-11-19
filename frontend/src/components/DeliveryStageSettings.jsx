import { Lock, Check } from 'lucide-react';
import { OPTIONAL_STAGES } from '../utils/deliveryStages';

// Fluxo completo do pedido, na ordem. As etapas principais são fixas; as
// opcionais a loja liga ou desliga (viram colunas e botões no quadro).
const FLOW = [
    { id: 'PENDING', label: 'Aprovação pendente', hint: 'Aparece com o aceite manual' },
    { id: 'PREPARING', label: 'Em preparo' },
    { id: 'READY', label: 'Pronto p/ entrega' },
    { id: 'PICKUP_ONGOING', label: 'Entregador a caminho', hint: 'Mostra a previsão de chegada quando a Keeta envia' },
    { id: 'ARRIVED_AT_MERCHANT', label: 'Entregador na loja' },
    { id: 'ORDER_PICKED', label: 'Pedido coletado' },
    { id: 'DELIVERY_ONGOING', label: 'Saiu para entrega' },
    { id: 'ARRIVED_AT_CUSTOMER', label: 'Chegou ao cliente' },
    { id: 'ORDER_DELIVERED', label: 'Entregue', hint: 'O pedido vai para o Histórico' },
];

export default function DeliveryStageSettings({ value = [], onChange }) {
    const toggle = (id) => {
        const next = value.includes(id) ? value.filter(stage => stage !== id) : [...value, id];
        onChange(OPTIONAL_STAGES.filter(stage => next.includes(stage)));
    };

    return (
        <div className="mt-3 p-4 rounded-xl border border-slate-200 bg-slate-50">
            <p className="font-bold text-slate-700">Etapas do quadro de pedidos</p>
            <p className="text-xs text-slate-500 mt-1">
                Escolha as etapas extras que viram colunas no quadro. Na entrega da Keeta, o entregador dela avisa cada etapa;
                na entrega própria, você marca no pedido e o PDV envia para a Keeta.
            </p>
            <ol className="mt-3 space-y-1.5">
                {FLOW.map((step, index) => {
                    const optional = OPTIONAL_STAGES.includes(step.id);
                    const checked = !optional || value.includes(step.id);
                    return (
                        <li key={step.id}>
                            <button type="button" role="checkbox" aria-checked={checked} disabled={!optional}
                                onClick={() => toggle(step.id)}
                                className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg border text-left transition-colors ${optional
                                    ? (checked ? 'bg-sky-50 border-sky-200 hover:bg-sky-100' : 'bg-white border-slate-200 hover:bg-slate-100')
                                    : 'bg-white/60 border-slate-100 cursor-default'}`}>
                                <span className="w-5 text-xs font-bold text-slate-400 text-right">{index + 1}</span>
                                <span className={`w-5 h-5 shrink-0 rounded-md flex items-center justify-center border ${!optional
                                    ? 'bg-slate-200 border-slate-200 text-slate-500'
                                    : checked ? 'bg-sky-500 border-sky-500 text-white' : 'bg-white border-slate-300'}`}>
                                    {!optional ? <Lock className="w-3 h-3" /> : checked && <Check className="w-3.5 h-3.5" />}
                                </span>
                                <span className="flex-1 min-w-0">
                                    <span className={`block text-sm font-bold ${optional && !checked ? 'text-slate-400' : 'text-slate-700'}`}>{step.label}</span>
                                    {step.hint && <span className="block text-[11px] text-slate-400">{step.hint}</span>}
                                </span>
                                <span className={`text-[10px] font-bold uppercase tracking-wide ${optional ? 'text-sky-600' : 'text-slate-400'}`}>
                                    {optional ? (checked ? 'Ligada' : 'Desligada') : 'Obrigatória'}
                                </span>
                            </button>
                        </li>
                    );
                })}
            </ol>
        </div>
    );
}
