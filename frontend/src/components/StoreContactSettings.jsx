import { useEffect, useState } from 'react';
import { Phone, Clock, Save, RefreshCw, CheckCircle, AlertCircle, Plus, Trash2, Loader2 } from 'lucide-react';
import api from '../services/api';

const WEEK_DAYS = [
  ['MONDAY', 'Seg'], ['TUESDAY', 'Ter'], ['WEDNESDAY', 'Qua'], ['THURSDAY', 'Qui'],
  ['FRIDAY', 'Sex'], ['SATURDAY', 'Sáb'], ['SUNDAY', 'Dom'],
];
const DAY_CODES = WEEK_DAYS.map(([code]) => code);
const NEW_PERIOD = { days: [...DAY_CODES], start: '18:00', end: '23:00' };

const inputClass = 'w-full px-4 py-3 bg-slate-50 border border-slate-200 rounded-xl focus:ring-2 focus:ring-indigo-400 focus:outline-none font-medium text-slate-700';
const labelClass = 'block text-sm font-bold text-slate-600 mb-2';

// "55-11987654321" -> "(11) 98765-4321" para exibir no campo.
function formatPhone(value) {
  const digits = String(value || '').replace(/\D/g, '').replace(/^55(?=\d{10,11}$)/, '');
  if (digits.length === 11) return `(${digits.slice(0, 2)}) ${digits.slice(2, 7)}-${digits.slice(7)}`;
  if (digits.length === 10) return `(${digits.slice(0, 2)}) ${digits.slice(2, 6)}-${digits.slice(6)}`;
  return value || '';
}

// Contatos e horário de funcionamento que a Keeta mostra para a loja. São
// enviados no próximo "Enviar para Keeta" (o envio grava esses dados na loja).
export default function StoreContactSettings() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState(null);
  const [ownerEmail, setOwnerEmail] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [periods, setPeriods] = useState([]);
  const [savedPhone, setSavedPhone] = useState(null);

  useEffect(() => {
    api.get('/config')
      .then(({ data }) => {
        setOwnerEmail(data.ownerEmail || '');
        setEmail(data.contactEmail || '');
        setPhone(formatPhone(data.contactPhone));
        setSavedPhone(data.contactPhone || null);
        setPeriods(data.serviceHours || []);
      })
      .catch(error => setMessage({ type: 'error', text: error?.response?.data?.error || 'Não foi possível carregar os dados da loja.' }))
      .finally(() => setLoading(false));
  }, []);

  const updatePeriod = (index, changes) => setPeriods(prev => prev.map((period, i) => (i === index ? { ...period, ...changes } : period)));
  const toggleDay = (index, code) => {
    const days = periods[index].days;
    updatePeriod(index, { days: days.includes(code) ? days.filter(day => day !== code) : DAY_CODES.filter(day => day === code || days.includes(day)) });
  };

  const handleSave = async (e) => {
    e.preventDefault();
    setMessage(null);
    if (periods.some(period => period.days.length === 0)) { setMessage({ type: 'error', text: 'Escolha pelo menos um dia em cada período.' }); return; }
    if (periods.some(period => period.start === period.end)) { setMessage({ type: 'error', text: 'Abertura e fechamento não podem ser no mesmo horário.' }); return; }
    setSaving(true);
    try {
      const { data } = await api.post('/config', { contactEmail: email.trim(), contactPhone: phone.trim(), serviceHours: periods });
      setEmail(data.contactEmail || '');
      setPhone(formatPhone(data.contactPhone));
      setSavedPhone(data.contactPhone || null);
      setPeriods(data.serviceHours || []);
      setMessage({ type: 'success', text: 'Dados salvos. Clique em "Enviar para Keeta" no Cardápio para atualizar a loja na Keeta.' });
    } catch (error) {
      setMessage({ type: 'error', text: error?.response?.data?.error || 'Não foi possível salvar.' });
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <div className="bg-white p-6 rounded-2xl shadow-sm border border-slate-200 flex items-center gap-2 text-slate-400"><Loader2 className="w-5 h-5 animate-spin" />Carregando dados da loja…</div>;
  }

  const usingPlaceholders = !savedPhone || periods.length === 0;

  return (
    <form onSubmit={handleSave} className="bg-white p-6 rounded-2xl shadow-sm border border-slate-200 space-y-5">
      <div className="flex items-center gap-3 border-b border-slate-100 pb-4">
        <div className="p-2 bg-teal-100 text-teal-700 rounded-lg"><Phone className="w-6 h-6" /></div>
        <div>
          <h3 className="font-bold text-lg text-slate-800">Contato e horário na Keeta</h3>
          <p className="text-xs text-slate-400">Aparecem para a Keeta e definem quando a loja aceita pedidos</p>
        </div>
      </div>

      {usingPlaceholders && (
        <div className="p-3 rounded-xl bg-amber-50 border border-amber-200 text-amber-800 text-sm">
          A loja ainda usa valores de exemplo: {!savedPhone && <>telefone <b>(11) 99999-9999</b></>}{!savedPhone && periods.length === 0 && ' e '}
          {periods.length === 0 && <>horário <b>todos os dias, 08:00–20:00</b></>}. Preencha abaixo com os dados reais.
        </div>
      )}

      {message && (
        <div className={`p-3 rounded-xl flex items-start gap-2 text-sm font-bold ${message.type === 'success' ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}`}>
          {message.type === 'success' ? <CheckCircle className="w-4 h-4 shrink-0 mt-0.5" /> : <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />}
          {message.text}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label className={labelClass} htmlFor="store-contact-email">E-mail de contato</label>
          <input id="store-contact-email" type="email" maxLength={254} value={email} onChange={e => setEmail(e.target.value)} placeholder={ownerEmail || 'contato@restaurante.com.br'} className={inputClass} />
          <p className="text-[11px] text-slate-400 mt-1">Em branco, usamos o e-mail da sua conta{ownerEmail ? ` (${ownerEmail})` : ''}.</p>
        </div>
        <div>
          <label className={labelClass} htmlFor="store-contact-phone">Telefone da loja (com DDD)</label>
          <input id="store-contact-phone" type="tel" maxLength={20} value={phone} onChange={e => setPhone(e.target.value)} placeholder="(11) 98765-4321" className={inputClass} />
        </div>
      </div>

      <div>
        <div className="flex items-center justify-between mb-2">
          <span className={labelClass + ' mb-0 flex items-center gap-1.5'}><Clock className="w-4 h-4" />Horário de funcionamento (Brasília)</span>
          <button type="button" onClick={() => setPeriods(prev => [...prev, { ...NEW_PERIOD, days: [...NEW_PERIOD.days] }])}
            className="text-xs font-bold px-3 py-1.5 rounded-lg bg-teal-50 text-teal-700 hover:bg-teal-100 flex items-center gap-1">
            <Plus className="w-3.5 h-3.5" />Adicionar período
          </button>
        </div>
        <p className="text-[11px] text-slate-400 mb-3">Use mais de um período para almoço e jantar. Fechamento antes da abertura (ex.: 18:00 às 02:00) termina no dia seguinte.</p>
        {periods.length === 0 && <p className="text-sm text-slate-400 py-2">Nenhum período cadastrado.</p>}
        <div className="space-y-3">
          {periods.map((period, index) => (
            <div key={index} className="p-3 rounded-xl border border-slate-200 bg-slate-50 space-y-2">
              <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label={`Dias do período ${index + 1}`}>
                {WEEK_DAYS.map(([code, label]) => {
                  const checked = period.days.includes(code);
                  return (
                    <button key={code} type="button" aria-pressed={checked} onClick={() => toggleDay(index, code)}
                      className={`px-2.5 py-1 rounded-lg text-xs font-bold border ${checked ? 'bg-teal-600 text-white border-teal-600' : 'bg-white text-slate-500 border-slate-200 hover:border-teal-300'}`}>
                      {label}
                    </button>
                  );
                })}
                <button type="button" onClick={() => setPeriods(prev => prev.filter((_, i) => i !== index))} title="Remover período" aria-label={`Remover período ${index + 1}`}
                  className="ml-auto p-1.5 rounded-lg text-slate-400 hover:text-red-600 hover:bg-red-50"><Trash2 className="w-4 h-4" /></button>
              </div>
              <div className="flex flex-wrap items-center gap-2 text-sm text-slate-600">
                <label className="flex items-center gap-1.5">Abre <input type="time" required value={period.start} onChange={e => updatePeriod(index, { start: e.target.value })} className="px-2 py-1.5 bg-white border border-slate-200 rounded-lg text-sm" /></label>
                <label className="flex items-center gap-1.5">Fecha <input type="time" required value={period.end} onChange={e => updatePeriod(index, { end: e.target.value })} className="px-2 py-1.5 bg-white border border-slate-200 rounded-lg text-sm" /></label>
                {period.end < period.start && <span className="text-xs text-slate-400">(fecha no dia seguinte)</span>}
              </div>
            </div>
          ))}
        </div>
      </div>

      <button type="submit" disabled={saving}
        className={`w-full py-3 font-bold rounded-xl transition-all flex items-center justify-center gap-2 shadow-sm ${saving ? 'bg-slate-300 text-slate-500 cursor-not-allowed' : 'bg-teal-600 hover:bg-teal-700 text-white'}`}>
        {saving ? <RefreshCw className="w-5 h-5 animate-spin" /> : <Save className="w-5 h-5" />}
        {saving ? 'Salvando...' : 'Salvar contato e horário'}
      </button>
    </form>
  );
}
