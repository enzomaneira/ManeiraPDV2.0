// Utilitários da tela de Cardápio.

export const getErrorMessage = (error, fallback) => error?.response?.data?.error || fallback;

export const inputClass = 'w-full px-3 py-2.5 bg-white border border-slate-200 rounded-xl focus:ring-2 focus:ring-indigo-400 focus:outline-none text-sm text-slate-700';
export const labelClass = 'block text-sm font-bold text-slate-600 mb-1.5';

// Regra do grupo em palavras: "Opcional · até 3", "Obrigatório · escolha 1".
export function groupRuleText(group) {
  const min = group.minPermitted || 0;
  const max = group.maxPermitted || 1;
  if (min === 0) return max === 1 ? 'Opcional · escolha 1' : `Opcional · até ${max}`;
  if (min === max) return `Obrigatório · escolha ${min}`;
  return `Obrigatório · de ${min} a ${max}`;
}

// Produtos (itens vendidos) e complementos (itens que só aparecem como opção).
export const isProduct = (item) => !item.isOptionItem;

// ===== Disponibilidade: horários de Brasília <-> UTC =====
// A Keeta só usa os horários semanais (datas são ignoradas) e eles ficam em
// UTC+0. O lojista digita no horário de Brasília (UTC−3, sem horário de verão
// desde 2019) e a conversão é feita aqui.
export const WEEK_DAYS = [
  ['MONDAY', 'Seg'], ['TUESDAY', 'Ter'], ['WEDNESDAY', 'Qua'], ['THURSDAY', 'Qui'],
  ['FRIDAY', 'Sex'], ['SATURDAY', 'Sáb'], ['SUNDAY', 'Dom'],
];
export const DAY_CODES = WEEK_DAYS.map(([code]) => code);
const DAY_LABELS = Object.fromEntries(WEEK_DAYS);
const BRASILIA_OFFSET_MINUTES = 180;
const MINUTES_PER_DAY = 1440;

const toMinutes = (time) => { const [h, m] = String(time).split(':').map(Number); return h * 60 + m; };
const formatMinutes = (minutes) => `${String(Math.floor(minutes / 60)).padStart(2, '0')}:${String(minutes % 60).padStart(2, '0')}`;

// Converte "dias + início/fim em Brasília" para as linhas em UTC que o backend
// guarda. Um intervalo que passa da meia-noite (em Brasília ou em UTC) vira duas
// linhas, uma em cada dia, porque cada linha precisa ter início antes do fim.
export function brasiliaRangeToUtcHours(days, start, end) {
  const hours = [];
  const startMin = toMinutes(start) + BRASILIA_OFFSET_MINUTES;
  let endMin = toMinutes(end) + BRASILIA_OFFSET_MINUTES;
  if (endMin <= startMin) endMin += MINUTES_PER_DAY;
  days.forEach(day => {
    const dayIndex = DAY_CODES.indexOf(day);
    for (let offset = 0; offset < 3; offset++) {
      const dayStart = offset * MINUTES_PER_DAY;
      const segStart = Math.max(startMin, dayStart) - dayStart;
      const segEnd = Math.min(endMin, dayStart + MINUTES_PER_DAY) - dayStart;
      if (segEnd <= segStart) continue;
      const startTime = formatMinutes(segStart);
      const endTime = segEnd >= MINUTES_PER_DAY ? '23:59' : formatMinutes(segEnd);
      if (endTime <= startTime) continue;
      hours.push({ dayOfWeek: DAY_CODES[(dayIndex + offset) % 7], startTime: `${startTime}:00.000Z`, endTime: `${endTime}:00.000Z` });
    }
  });
  return hours;
}

// Converte uma linha guardada em UTC para Brasília: { dayIndex, start, end } em minutos.
function utcHourToBrasilia(hour) {
  let dayIndex = DAY_CODES.indexOf(hour.dayOfWeek);
  const endUtc = hour.endTime.slice(0, 5) === '23:59' ? MINUTES_PER_DAY : toMinutes(hour.endTime.slice(0, 5));
  let start = toMinutes(hour.startTime.slice(0, 5)) - BRASILIA_OFFSET_MINUTES;
  let end = endUtc - BRASILIA_OFFSET_MINUTES;
  if (start < 0) { dayIndex = (dayIndex + 6) % 7; start += MINUTES_PER_DAY; end += MINUTES_PER_DAY; }
  return { dayIndex, start, end };
}

// Rótulos em Brasília (ex.: "Sex 18:00–23:00"), juntando os pedaços que a
// conversão para UTC separou na meia-noite.
export function brasiliaLabels(hours) {
  const ranges = (hours || []).map(utcHourToBrasilia).sort((a, b) => a.dayIndex - b.dayIndex || a.start - b.start);
  const merged = [];
  ranges.forEach(range => {
    const last = merged[merged.length - 1];
    if (last && last.dayIndex === range.dayIndex && last.end === range.start) last.end = range.end;
    else merged.push({ ...range });
  });
  return merged.map(({ dayIndex, start, end }) => {
    const endLabel = end === MINUTES_PER_DAY ? '24:00' : formatMinutes(end % MINUTES_PER_DAY);
    return `${DAY_LABELS[DAY_CODES[dayIndex]]} ${formatMinutes(start)}–${endLabel}`;
  });
}
