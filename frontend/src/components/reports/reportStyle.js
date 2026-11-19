import { formatCurrency } from '../../utils/formatters';

// Cores (paleta de referência validada; tema claro do PDV)
export const COLORS = {
    surface: '#fcfcfb',
    grid: '#e1e0d9',
    axis: '#c3c2b7',
    muted: '#898781',
    series: ['#2a78d6', '#eb6834', '#1baf7a'],  // azul, laranja, verde-água (validadas em sequência)
    // Escala sequencial (uma cor, claro -> escuro) para o mapa de calor
    ramp: ['#cde2fb', '#9ec5f4', '#6da7ec', '#3987e5', '#256abf', '#184f95', '#0d366b'],
    empty: '#f0efec',
};

export const formatCompactCurrency = (value) => {
    if (Math.abs(value) >= 1000) {
        return 'R$ ' + new Intl.NumberFormat('pt-BR', { notation: 'compact', maximumFractionDigits: 1 }).format(value);
    }
    return formatCurrency(value);
};
