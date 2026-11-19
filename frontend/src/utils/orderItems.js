// Complementos de um item do pedido, juntando repetidos com a quantidade.
// A Keeta pode mandar o mesmo complemento com quantity 2 ou repetido na lista.
export function groupOptions(options = []) {
  const byName = new Map();
  for (const option of options) {
    const name = String(option?.name || '').trim();
    if (!name) continue;
    const quantity = Number(option.quantity) > 0 ? Number(option.quantity) : 1;
    const price = Number(option.price ?? option.unitPrice?.value ?? 0) || 0;
    const current = byName.get(name) || { name, quantity: 0, price };
    current.quantity += quantity;
    byName.set(name, current);
  }
  return [...byName.values()];
}

const optionLabel = (option) => (option.quantity !== 1 ? `${option.quantity}x ${option.name}` : option.name);

// Separa o nome salvo ("X-Burguer (2x Bacon, Cheddar) [Obs: sem cebola]") em
// produto, complementos (com quantidade) e observação.
export function orderItemParts(item) {
  let name = String(item?.name || '').trim();
  let note = '';
  const obsAt = name.indexOf(' [Obs: ');
  if (obsAt >= 0) {
    note = name.slice(obsAt + 7).replace(/\]$/, '').trim();
    name = name.slice(0, obsAt).trim();
  }
  const options = groupOptions(item?.options || []);
  if (options.length) {
    const suffixes = [
      ` (${options.map(optionLabel).join(', ')})`,                                   // formato atual
      ` (${(item.options || []).map(o => o?.name).filter(Boolean).join(', ')})`,    // formato antigo
    ];
    const suffix = suffixes.find(s => name.endsWith(s));
    if (suffix) name = name.slice(0, -suffix.length);
  }
  return { name, options, note };
}
