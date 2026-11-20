// Cardápio por plataforma: dados e funções usados pelos campos e listas.

export const PLATFORMS = [
  { key: 'keeta', name: 'Keeta', at: 'na Keeta', on: 'onKeeta', price: 'keetaPrice', dot: 'bg-[#ffd100] border-[#e6bc00]', active: 'border-[#f0c400] bg-[#fffbe6]' },
  { key: 'ifood', name: 'iFood', at: 'no iFood', on: 'onIfood', price: 'ifoodPrice', dot: 'bg-[#ea1d2c] border-[#c81624]', active: 'border-[#f5a3a9] bg-[#fff1f2]' },
];

// Estado do formulário a partir da entidade salva
export const platformForm = (source = {}) => ({
  onKeeta: source.onKeeta !== false,
  onIfood: source.onIfood !== false,
  keetaPrice: source.keetaPrice != null ? String(source.keetaPrice) : '',
  ifoodPrice: source.ifoodPrice != null ? String(source.ifoodPrice) : '',
});

// Campos para a API; preço vazio = usa o preço normal. Lança erro se inválido.
export function platformPayload(form, withPrices) {
  const payload = { onKeeta: form.onKeeta, onIfood: form.onIfood };
  if (withPrices) {
    for (const { price, at } of PLATFORMS) {
      const raw = String(form[price] ?? '').trim();
      if (raw === '') { payload[price] = null; continue; }
      const value = parseFloat(raw.replace(',', '.'));
      if (isNaN(value) || value < 0) throw new Error(`Confira o preço ${at}.`);
      payload[price] = value;
    }
  }
  return payload;
}
