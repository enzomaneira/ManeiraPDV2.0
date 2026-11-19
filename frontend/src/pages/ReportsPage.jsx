import { useEffect, useState } from 'react';
import { Loader2, AlertCircle, Clock, TrendingUp, Table2 } from 'lucide-react';
import { reportService } from '../services/api';
import { formatCurrency } from '../utils/formatters';
import { Card, StatTile, ColumnChart, Heatmap, RankedBars, SplitBar } from '../components/reports/ReportCharts';

// Datas em Brasília (o backend agrupa no mesmo fuso)
const todayInBrasilia = () => {
    const parts = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Sao_Paulo', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
    return parts; // AAAA-MM-DD
};
const shift = (iso, days) => {
    const d = new Date(`${iso}T12:00:00Z`);
    d.setUTCDate(d.getUTCDate() + days);
    return d.toISOString().slice(0, 10);
};
const PRESETS = [
    { id: 'today', label: 'Hoje', range: (t) => [t, t] },
    { id: 'yesterday', label: 'Ontem', range: (t) => [shift(t, -1), shift(t, -1)] },
    { id: '7', label: '7 dias', range: (t) => [shift(t, -6), t] },
    { id: '30', label: '30 dias', range: (t) => [shift(t, -29), t] },
    { id: '90', label: '90 dias', range: (t) => [shift(t, -89), t] },
    { id: 'month', label: 'Este mês', range: (t) => [`${t.slice(0, 8)}01`, t] },
];
const brDate = (iso) => iso ? iso.split('-').reverse().join('/') : '';
const count = (n, one, many) => `${n.toLocaleString('pt-BR')} ${n === 1 ? one : many}`;

export default function ReportsPage({ stores = [] }) {
    const [today] = useState(todayInBrasilia);
    const [preset, setPreset] = useState('30');
    const [range, setRange] = useState(() => PRESETS[3].range(today));
    const [storeId, setStoreId] = useState('all');
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [showTable, setShowTable] = useState(false);

    useEffect(() => {
        let cancelled = false;
        reportService.get({ from: range[0], to: range[1], storeId })
            .then(({ data: report }) => { if (!cancelled) { setData(report); setError(null); } })
            .catch((err) => { if (!cancelled) setError(err.response?.data?.error || 'Não foi possível carregar o relatório.'); })
            .finally(() => { if (!cancelled) setLoading(false); });
        return () => { cancelled = true; };
    }, [range, storeId]);

    // Cada mudança de filtro marca "carregando"; o efeito busca o relatório
    const choosePreset = (p) => { setLoading(true); setPreset(p.id); setRange(p.range(today)); };
    const chooseStore = (value) => { setLoading(true); setStoreId(value); };
    const setCustom = (index, value) => {
        if (!value) return;
        setLoading(true);
        setPreset('custom');
        setRange(prev => (index === 0 ? [value, prev[1]] : [prev[0], value]));
    };

    const s = data?.summary;
    const multiBrand = stores.length > 1;
    const unitIsHour = data?.timeline.unit === 'hour';

    return (
        <div className="max-w-7xl mx-auto space-y-6">
            {/* Filtros: uma linha acima de tudo, valem para a página inteira */}
            <div className="flex flex-wrap items-center gap-3">
                <div className="flex flex-wrap gap-1 bg-white border border-slate-200 rounded-xl p-1" role="group" aria-label="Período">
                    {PRESETS.map(p => (
                        <button key={p.id} type="button" onClick={() => choosePreset(p)} aria-pressed={preset === p.id}
                            className={`px-3 py-1.5 rounded-lg text-sm font-bold transition-colors ${preset === p.id ? 'bg-indigo-600 text-white' : 'text-slate-600 hover:bg-slate-100'}`}>
                            {p.label}
                        </button>
                    ))}
                </div>
                <div className="flex items-center gap-2 text-sm text-slate-600">
                    <input type="date" value={range[0]} max={range[1]} onChange={e => setCustom(0, e.target.value)} aria-label="Data inicial"
                        className="px-2 py-1.5 rounded-lg border border-slate-200 bg-white" />
                    <span>até</span>
                    <input type="date" value={range[1]} min={range[0]} max={today} onChange={e => setCustom(1, e.target.value)} aria-label="Data final"
                        className="px-2 py-1.5 rounded-lg border border-slate-200 bg-white" />
                </div>
                {multiBrand && (
                    <select value={storeId} onChange={e => chooseStore(e.target.value)} aria-label="Restaurante"
                        className="px-3 py-2 rounded-lg border border-slate-200 bg-white text-sm font-medium text-slate-700">
                        <option value="all">Todos os restaurantes</option>
                        {stores.map(store => <option key={store.id} value={store.id}>{store.name}</option>)}
                    </select>
                )}
                {loading && <Loader2 className="w-4 h-4 animate-spin text-slate-400" aria-label="Carregando" />}
            </div>

            {error && (
                <p className="flex items-center gap-2 p-3 rounded-xl bg-red-50 border border-red-200 text-sm font-bold text-red-700">
                    <AlertCircle className="w-4 h-4" /> {error}
                </p>
            )}

            {data && (
                // Ao recarregar, mantém o desenho anterior meio apagado (sem piscar)
                <div className={`space-y-6 transition-opacity ${loading ? 'opacity-50' : ''}`}>
                    <p className="text-xs text-slate-500">
                        {brDate(data.range.from)} a {brDate(data.range.to)} · comparado com {brDate(data.range.previousFrom)} a {brDate(data.range.previousTo)} · horário de Brasília · pedidos cancelados não entram no faturamento
                    </p>

                    <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
                        <StatTile hero label="Faturamento" value={formatCurrency(s.revenue)} change={s.change.revenue} />
                        <StatTile label="Pedidos" value={s.orders.toLocaleString('pt-BR')} change={s.change.orders}
                            hint={count(s.itemsSold, 'item vendido', 'itens vendidos')} />
                        <StatTile label="Ticket médio" value={formatCurrency(s.averageTicket)} change={s.change.averageTicket} />
                        <StatTile label="Cancelados" value={`${s.canceled.toLocaleString('pt-BR')} (${s.cancelRate.toLocaleString('pt-BR')}%)`}
                            change={s.change.canceled} upIsGood={false} hint={`${formatCurrency(s.canceledValue)} em pedidos cancelados`} />
                    </div>

                    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
                        <MiniFact icon={<Clock className="w-4 h-4" />} label="Horário de pico"
                            value={data.peakHour === null ? '—' : `${data.peakHour}h às ${data.peakHour + 1}h`}
                            hint={data.peakHour === null ? 'Sem pedidos no período' : count(data.byHour[data.peakHour], 'pedido nesse horário', 'pedidos nesse horário')} />
                        <MiniFact icon={<TrendingUp className="w-4 h-4" />} label={unitIsHour ? 'Melhor hora' : 'Melhor dia'}
                            value={data.bestDay ? (unitIsHour ? data.bestDay.label : `${data.bestDay.weekday}, ${data.bestDay.label}`) : '—'}
                            hint={data.bestDay ? `${formatCurrency(data.bestDay.revenue)} · ${count(data.bestDay.orders, 'pedido', 'pedidos')}` : 'Sem vendas no período'} />
                        <MiniFact label="Taxas e descontos" value={`${formatCurrency(s.fees)} em taxas`} hint={`${formatCurrency(s.discounts)} em descontos`} />
                    </div>

                    <Card title={unitIsHour ? 'Faturamento por hora' : 'Faturamento por dia'}
                        subtitle="Passe o mouse em uma coluna para ver o valor e os pedidos"
                        action={
                            <button type="button" onClick={() => setShowTable(!showTable)} aria-pressed={showTable}
                                className="flex items-center gap-1 px-2.5 py-1 rounded-lg border border-slate-200 text-xs font-bold text-slate-500 hover:bg-slate-50">
                                <Table2 className="w-3.5 h-3.5" /> {showTable ? 'Ver gráfico' : 'Ver tabela'}
                            </button>
                        }>
                        {showTable ? <TimelineTable points={data.timeline.points} unitIsHour={unitIsHour} /> : (
                            <ColumnChart points={data.timeline.points}
                                describe={(p) => `${p.weekday ? `${p.weekday}, ` : ''}${p.label}: ${formatCurrency(p.revenue)}, ${count(p.orders, 'pedido', 'pedidos')}`} />
                        )}
                    </Card>

                    <Card title="Horários de pico" subtitle="Pedidos por dia da semana e hora (cancelados fora)">
                        <Heatmap weekdays={data.heatmap.weekdays} counts={data.heatmap.counts} />
                    </Card>

                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                        <Card title="Itens mais vendidos" subtitle={`Por quantidade · ${count(data.itemCount, 'produto diferente', 'produtos diferentes')} no período`}>
                            <RankedBars rows={data.topItems} valueKey="quantity" formatValue={(v) => `${v.toLocaleString('pt-BR')} un.`}
                                detail={(r) => formatCurrency(r.revenue)} />
                        </Card>
                        <Card title="Complementos mais pedidos" subtitle={`Por quantidade · ${count(data.optionCount, 'complemento diferente', 'complementos diferentes')}`}>
                            <RankedBars rows={data.topOptions} valueKey="quantity" formatValue={(v) => `${v.toLocaleString('pt-BR')} un.`}
                                detail={(r) => (r.revenue ? `+ ${formatCurrency(r.revenue)}` : 'grátis')} emptyText="Nenhum complemento escolhido no período." />
                        </Card>
                    </div>

                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                        <Card title="Formas de pagamento" subtitle="Faturamento por forma de pagamento">
                            <RankedBars rows={data.payments} valueKey="revenue" formatValue={formatCurrency} detail={(r) => count(r.orders, 'pedido', 'pedidos')} />
                        </Card>
                        <Card title="Entrega" subtitle="Pedidos por quem fez a entrega">
                            <SplitBar parts={data.delivery.map(d => ({ name: d.name, value: d.orders }))} formatValue={(v) => count(v, 'pedido', 'pedidos')} />
                        </Card>
                        <Card title="Clientes" subtitle="Primeiro pedido na loja ou cliente que voltou">
                            <SplitBar parts={[
                                { name: 'Clientes novos', value: data.customers.new },
                                { name: 'Clientes que voltaram', value: data.customers.returning },
                                ...(data.customers.unknown ? [{ name: 'Sem informação', value: data.customers.unknown }] : []),
                            ]} formatValue={(v) => count(v, 'pedido', 'pedidos')} />
                        </Card>
                        {multiBrand && data.storeId === 'all' && (
                            <Card title="Por restaurante" subtitle="Faturamento de cada marca">
                                <RankedBars rows={data.byStore} valueKey="revenue" formatValue={formatCurrency} detail={(r) => count(r.orders, 'pedido', 'pedidos')} />
                            </Card>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
}

function MiniFact({ icon, label, value, hint }) {
    return (
        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm px-5 py-4">
            <p className="flex items-center gap-1.5 text-sm font-medium text-slate-500">{icon}{label}</p>
            <p className="mt-1 text-lg font-semibold text-slate-900">{value}</p>
            {hint && <p className="text-xs text-slate-500">{hint}</p>}
        </div>
    );
}

function TimelineTable({ points, unitIsHour }) {
    const rows = unitIsHour ? points.filter(p => p.orders) : points;
    return (
        <div className="max-h-72 overflow-y-auto">
            <table className="w-full text-sm">
                <thead className="text-xs uppercase text-slate-500 bg-slate-50 sticky top-0">
                    <tr><th className="text-left px-3 py-2">{unitIsHour ? 'Hora' : 'Dia'}</th><th className="text-right px-3 py-2">Pedidos</th><th className="text-right px-3 py-2">Faturamento</th></tr>
                </thead>
                <tbody className="divide-y divide-slate-100" style={{ fontVariantNumeric: 'tabular-nums' }}>
                    {rows.map(p => (
                        <tr key={p.key}>
                            <td className="px-3 py-1.5 text-slate-600">{p.weekday ? `${p.weekday}, ` : ''}{p.label}</td>
                            <td className="px-3 py-1.5 text-right text-slate-700">{p.orders}</td>
                            <td className="px-3 py-1.5 text-right font-semibold text-slate-900">{formatCurrency(p.revenue)}</td>
                        </tr>
                    ))}
                    {!rows.length && <tr><td colSpan="3" className="px-3 py-6 text-center text-slate-400">Sem vendas no período.</td></tr>}
                </tbody>
            </table>
        </div>
    );
}
