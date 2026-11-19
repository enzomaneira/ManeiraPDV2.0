import { useState } from 'react';
import { ArrowUpRight, ArrowDownRight, Minus } from 'lucide-react';
import { formatCurrency } from '../../utils/formatters';
import { COLORS, formatCompactCurrency } from './reportStyle';

export function Card({ title, subtitle, children, className = '', action }) {
    return (
        <section className={`bg-white rounded-2xl border border-slate-200 shadow-sm p-5 ${className}`}>
            <div className="flex items-start justify-between gap-3 mb-4">
                <div>
                    <h3 className="font-bold text-slate-800">{title}</h3>
                    {subtitle && <p className="text-xs text-slate-500 mt-0.5">{subtitle}</p>}
                </div>
                {action}
            </div>
            {children}
        </section>
    );
}

// Número principal com variação em relação ao período anterior
export function StatTile({ label, value, change, upIsGood = true, hint, hero = false }) {
    let tone = 'text-slate-500';
    let Icon = Minus;
    let changeText = 'sem comparação';
    if (change !== null && change !== undefined) {
        const good = change === 0 ? null : (change > 0) === upIsGood;
        tone = good === null ? 'text-slate-500' : good ? 'text-[#006300]' : 'text-[#d03b3b]';
        Icon = change > 0 ? ArrowUpRight : change < 0 ? ArrowDownRight : Minus;
        changeText = `${change > 0 ? '+' : ''}${change.toLocaleString('pt-BR')}% vs período anterior`;
    }
    return (
        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-5">
            <p className="text-sm font-medium text-slate-500">{label}</p>
            <p className={`mt-1 font-semibold text-slate-900 tracking-tight ${hero ? 'text-4xl' : 'text-2xl'}`}>{value}</p>
            <p className={`mt-1 flex items-center gap-1 text-xs font-medium ${tone}`}>
                <Icon className="w-3.5 h-3.5" aria-hidden="true" /> {changeText}
            </p>
            {hint && <p className="mt-1 text-xs text-slate-400">{hint}</p>}
        </div>
    );
}

function niceMax(value) {
    if (value <= 0) return 1;
    const magnitude = 10 ** Math.floor(Math.log10(value));
    const step = [1, 2, 2.5, 5, 10].find(s => s * magnitude >= value / 4) * magnitude;
    return Math.ceil(value / step) * step;
}

// Colunas (faturamento por dia ou por hora), com dica ao passar o mouse/foco
export function ColumnChart({ points, valueKey = 'revenue', formatValue = formatCurrency, describe }) {
    const [hover, setHover] = useState(null);
    const width = 760, height = 240, left = 56, right = 12, top = 12, bottom = 28;
    const max = niceMax(Math.max(0, ...points.map(p => p[valueKey])));
    const plotW = width - left - right, plotH = height - top - bottom;
    const band = plotW / Math.max(points.length, 1);
    const barW = Math.max(2, Math.min(24, band - 4));
    const ticks = [0, 0.25, 0.5, 0.75, 1].map(f => f * max);
    const labelEvery = Math.ceil(points.length / 12);
    const best = points.reduce((b, p, i) => (p[valueKey] > (points[b]?.[valueKey] ?? -1) ? i : b), 0);
    const y = (v) => top + plotH - (v / max) * plotH;

    return (
        <div className="relative">
            <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-auto" role="img"
                aria-label={`Gráfico de colunas com ${points.length} períodos`}>
                {ticks.map((t, i) => (
                    <g key={i}>
                        <line x1={left} x2={width - right} y1={y(t)} y2={y(t)} stroke={i === 0 ? COLORS.axis : COLORS.grid} strokeWidth="1" />
                        <text x={left - 8} y={y(t) + 4} textAnchor="end" fontSize="11" fill={COLORS.muted} style={{ fontVariantNumeric: 'tabular-nums' }}>
                            {formatCompactCurrency(t).replace(',00', '')}
                        </text>
                    </g>
                ))}
                {points.map((p, i) => {
                    const v = p[valueKey];
                    const x = left + i * band + (band - barW) / 2;
                    const h = Math.max(0, (v / max) * plotH);
                    const r = Math.min(4, barW / 2, h);
                    const yTop = top + plotH - h;
                    const active = hover === i;
                    return (
                        <g key={p.key ?? i}>
                            {h > 0 && (
                                <path d={`M${x},${top + plotH} V${yTop + r} Q${x},${yTop} ${x + r},${yTop} H${x + barW - r} Q${x + barW},${yTop} ${x + barW},${yTop + r} V${top + plotH} Z`}
                                    fill={COLORS.series[0]} opacity={hover === null || active ? 1 : 0.55} />
                            )}
                            {/* Área de toque maior que a coluna */}
                            <rect x={left + i * band} y={top} width={band} height={plotH} fill="transparent" tabIndex={0}
                                aria-label={describe ? describe(p) : `${p.label}: ${formatValue(v)}`}
                                onPointerEnter={() => setHover(i)} onPointerLeave={() => setHover(null)}
                                onFocus={() => setHover(i)} onBlur={() => setHover(null)} style={{ outline: 'none' }} />
                            {i % labelEvery === 0 && (
                                <text x={left + i * band + band / 2} y={height - 8} textAnchor="middle" fontSize="11" fill={COLORS.muted}>{p.label}</text>
                            )}
                        </g>
                    );
                })}
                {points[best]?.[valueKey] > 0 && hover === null && (
                    <text x={Math.min(width - right - 4, Math.max(left + 40, left + best * band + band / 2))} y={Math.max(12, y(points[best][valueKey]) - 6)}
                        textAnchor="middle" fontSize="11" fontWeight="600" fill="#52514e">{formatCompactCurrency(points[best][valueKey])}</text>
                )}
            </svg>
            {hover !== null && points[hover] && (
                <div className="pointer-events-none absolute -translate-x-1/2 -translate-y-full bg-white border border-slate-200 shadow-lg rounded-lg px-3 py-2 text-xs"
                    style={{ left: `${((left + hover * band + band / 2) / width) * 100}%`, top: `${(y(points[hover][valueKey]) / height) * 100}%` }}>
                    <p className="font-bold text-slate-900 text-sm">{formatValue(points[hover][valueKey])}</p>
                    <p className="text-slate-500">{points[hover].weekday ? `${points[hover].weekday}, ` : ''}{points[hover].label} · {points[hover].orders} pedido{points[hover].orders === 1 ? '' : 's'}</p>
                </div>
            )}
        </div>
    );
}

// Mapa de calor: dia da semana × hora (pedidos)
export function Heatmap({ weekdays, counts }) {
    const [hover, setHover] = useState(null);
    const max = Math.max(0, ...counts.flat());
    const color = (v) => {
        if (!v) return COLORS.empty;
        const index = Math.min(COLORS.ramp.length - 1, Math.floor((v / max) * (COLORS.ramp.length - 1) + 0.0001));
        return COLORS.ramp[Math.max(0, index)];
    };
    return (
        <div>
            <div className="overflow-x-auto">
                <div className="min-w-[640px]">
                    <div className="grid gap-[2px]" style={{ gridTemplateColumns: '36px repeat(24, minmax(0, 1fr))' }}>
                        <span />
                        {Array.from({ length: 24 }, (_, h) => (
                            <span key={h} className="text-[10px] text-center text-slate-400" style={{ fontVariantNumeric: 'tabular-nums' }}>{h % 3 === 0 ? `${h}h` : ''}</span>
                        ))}
                        {weekdays.map((day, d) => (
                            <Row key={day} day={day} values={counts[d]} color={color} onHover={(h) => setHover(h === null ? null : { d, h })} />
                        ))}
                    </div>
                </div>
            </div>
            <div className="mt-3 flex flex-wrap items-center justify-between gap-3 text-xs text-slate-500">
                <p aria-live="polite" className="min-h-[1rem]">
                    {hover ? <><b className="text-slate-900">{counts[hover.d][hover.h]} pedido{counts[hover.d][hover.h] === 1 ? '' : 's'}</b> · {weekdays[hover.d]}, {hover.h}h às {hover.h + 1}h</> : 'Passe o mouse em um quadrado para ver os pedidos.'}
                </p>
                <div className="flex items-center gap-1.5">
                    <span>Menos</span>
                    {[COLORS.empty, ...COLORS.ramp].map(c => <span key={c} className="w-4 h-3 rounded-sm" style={{ background: c }} />)}
                    <span>Mais</span>
                </div>
            </div>
        </div>
    );
}

function Row({ day, values, color, onHover }) {
    return (
        <>
            <span className="text-xs font-medium text-slate-500 self-center">{day}</span>
            {values.map((v, h) => (
                <span key={h} role="img" aria-label={`${day} ${h}h: ${v} pedidos`}
                    onPointerEnter={() => onHover(h)} onPointerLeave={() => onHover(null)}
                    className="h-6 rounded-[3px] hover:ring-2 hover:ring-slate-700/40 cursor-default"
                    style={{ background: color(v) }} />
            ))}
        </>
    );
}

// Barras horizontais ordenadas (uma cor), com o valor na ponta
export function RankedBars({ rows, valueKey, formatValue, detail, emptyText = 'Sem dados no período.' }) {
    if (!rows.length) return <p className="text-sm text-slate-400 py-6 text-center">{emptyText}</p>;
    const max = Math.max(...rows.map(r => r[valueKey])) || 1;
    return (
        <ol className="space-y-2.5">
            {rows.map((row, i) => (
                <li key={row.name} className="grid grid-cols-[1.25rem_minmax(0,1fr)] gap-x-2 items-start">
                    <span className="text-xs font-bold text-slate-400 text-right leading-5" style={{ fontVariantNumeric: 'tabular-nums' }}>{i + 1}</span>
                    <div className="min-w-0">
                        <div className="flex items-baseline justify-between gap-3">
                            <span className="text-sm font-medium text-slate-700 truncate" title={row.name}>{row.name}</span>
                            <span className="text-sm font-semibold text-slate-900 shrink-0" style={{ fontVariantNumeric: 'tabular-nums' }}>{formatValue(row[valueKey])}</span>
                        </div>
                        <div className="mt-1 flex items-center gap-2">
                            <div className="flex-1 h-2 rounded-full bg-[#f0efec] overflow-hidden">
                                <div className="h-full rounded-full" style={{ width: `${Math.max(2, (row[valueKey] / max) * 100)}%`, background: COLORS.series[0] }} />
                            </div>
                            {detail && <span className="text-[11px] text-slate-500 shrink-0 w-28 text-right" style={{ fontVariantNumeric: 'tabular-nums' }}>{detail(row)}</span>}
                        </div>
                    </div>
                </li>
            ))}
        </ol>
    );
}

// Uma barra dividida em partes (até 3), com legenda que traz os números
export function SplitBar({ parts, formatValue = (v) => v, emptyText = 'Sem dados no período.' }) {
    const total = parts.reduce((s, p) => s + p.value, 0);
    if (!total) return <p className="text-sm text-slate-400 py-4 text-center">{emptyText}</p>;
    const visible = parts.filter(p => p.value > 0);
    return (
        <div>
            <div className="flex h-7 gap-[2px]" role="img"
                aria-label={visible.map(p => `${p.name}: ${formatValue(p.value)} (${Math.round(p.value / total * 100)}%)`).join('; ')}>
                {visible.map((p) => {
                    const share = Math.round(p.value / total * 100);
                    const color = COLORS.series[parts.indexOf(p) % COLORS.series.length];
                    return (
                        <div key={p.name} className="h-full rounded flex items-center px-2 min-w-[4px]" title={`${p.name}: ${formatValue(p.value)} (${share}%)`}
                            style={{ width: `${(p.value / total) * 100}%`, background: color }}>
                            {share >= 12 && <span className="text-xs font-bold text-white">{share}%</span>}
                        </div>
                    );
                })}
            </div>
            <ul className="mt-3 space-y-1.5">
                {parts.map((p, i) => (
                    <li key={p.name} className="flex items-center gap-2 text-sm">
                        <span className="w-3 h-3 rounded-sm shrink-0" style={{ background: COLORS.series[i % COLORS.series.length] }} />
                        <span className="flex-1 text-slate-600">{p.name}</span>
                        <span className="font-semibold text-slate-900" style={{ fontVariantNumeric: 'tabular-nums' }}>{formatValue(p.value)}</span>
                        <span className="w-10 text-right text-xs text-slate-500" style={{ fontVariantNumeric: 'tabular-nums' }}>{Math.round(p.value / total * 100)}%</span>
                    </li>
                ))}
            </ul>
        </div>
    );
}
