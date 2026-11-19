// Etiqueta da plataforma de origem do pedido (iFood, Keeta ou balcão)
const STYLES = {
    IFOOD: 'bg-[#ea1d2c] text-white border-[#ea1d2c]',
    KEETA: 'bg-[#ffd100] text-slate-900 border-[#f0c400]',
    BALCAO: 'bg-slate-100 text-slate-600 border-slate-200',
};

export default function PlatformTag({ order, className = '' }) {
    const id = order?.platformId || 'KEETA';
    return (
        <span className={`inline-flex items-center px-2 py-0.5 rounded-md border text-[10px] font-black uppercase tracking-wide ${STYLES[id] || STYLES.KEETA} ${className}`}
            title={`Pedido ${id === 'BALCAO' ? 'do balcão' : `da plataforma ${order?.platform}`}`}>
            {order?.platform || 'Keeta'}
        </span>
    );
}
