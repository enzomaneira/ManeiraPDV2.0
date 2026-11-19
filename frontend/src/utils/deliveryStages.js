// Etapas da entrega e colunas do quadro de pedidos.
//
// As etapas usam os nomes do /tracking da Keeta. Na entrega da Keeta elas vêm
// dos eventos do entregador; na entrega própria é o restaurante que avança.
// A loja escolhe quais etapas opcionais aparecem; as principais são fixas.

export const STAGES = [
  'PICKUP_ONGOING',
  'ARRIVED_AT_MERCHANT',
  'ORDER_PICKED',
  'DELIVERY_ONGOING',
  'ARRIVED_AT_CUSTOMER',
  'ORDER_DELIVERED',
];

// Etapas que a loja pode ligar/desligar (as demais são principais)
export const OPTIONAL_STAGES = ['PICKUP_ONGOING', 'ARRIVED_AT_MERCHANT', 'ORDER_PICKED', 'ARRIVED_AT_CUSTOMER'];

export const STAGE_LABELS = {
  PICKUP_ONGOING: 'Entregador a caminho',
  ARRIVED_AT_MERCHANT: 'Entregador na loja',
  ORDER_PICKED: 'Pedido coletado',
  DELIVERY_ONGOING: 'Saiu para entrega',
  ARRIVED_AT_CUSTOMER: 'Chegou ao cliente',
  ORDER_DELIVERED: 'Entregue',
};

// Etapas que o restaurante pode marcar antes do pedido ficar pronto
export const STAGES_DURING_PREPARATION = ['PICKUP_ONGOING', 'ARRIVED_AT_MERCHANT'];

export const stageRank = (stage) => STAGES.indexOf(stage);

export const isKeetaDelivery = (order) => order.deliveredBy === 'MARKETPLACE';

const isVisibleStage = (stage, enabledStages) => !OPTIONAL_STAGES.includes(stage) || enabledStages.includes(stage);

// Próximas etapas que o restaurante pode marcar (entrega própria): só as
// principais e as opcionais que a loja escolheu.
export function nextOwnStages(order, enabledStages = []) {
  if (isKeetaDelivery(order)) return [];
  if (!['PREPARING', 'READY', 'DISPATCHED'].includes(order.status)) return [];
  const current = stageRank(order.deliveryStage);
  return STAGES.filter((stage, index) => index > current
    && isVisibleStage(stage, enabledStages)
    && (order.status !== 'PREPARING' || STAGES_DURING_PREPARATION.includes(stage)));
}

const COLUMN_INFO = {
  PENDING: { title: 'Aprovação Pendente', theme: 'blue', icon: 'alert' },
  PREPARING: { title: 'Em Preparo', theme: 'orange', icon: 'chef' },
  READY: { title: 'Pronto p/ Entrega', theme: 'green', icon: 'check' },
  PICKUP_ONGOING: { title: 'Entregador a caminho', theme: 'sky', icon: 'navigation' },
  ARRIVED_AT_MERCHANT: { title: 'Entregador na loja', theme: 'teal', icon: 'store' },
  ORDER_PICKED: { title: 'Pedido coletado', theme: 'indigo', icon: 'package' },
  DELIVERY_ONGOING: { title: 'Saiu para entrega', theme: 'purple', icon: 'bike' },
  ARRIVED_AT_CUSTOMER: { title: 'Chegou ao cliente', theme: 'pink', icon: 'map' },
};
const COLUMN_ORDER = ['PREPARING', 'READY', 'PICKUP_ONGOING', 'ARRIVED_AT_MERCHANT', 'ORDER_PICKED', 'DELIVERY_ONGOING', 'ARRIVED_AT_CUSTOMER'];

// Coluna de cada pedido. Todo pedido em andamento cai em exatamente uma
// coluna visível; concluídos e cancelados vão para o Histórico (null). Se a
// etapa do pedido não tem coluna (a loja desligou), ele fica na coluna
// principal do seu status: Pronto ou Saiu para entrega.
export function columnFor(order, enabledStages = []) {
  const { status } = order;
  if (status === 'PENDING' || status === 'NEW') return 'PENDING';
  if (status === 'COMPLETED' || status === 'CANCELED') return null;
  if (status === 'PREPARING') return 'PREPARING';

  const fallback = status === 'READY' ? 'READY' : 'DELIVERY_ONGOING';
  const stage = order.deliveryStage === 'ORDER_DELIVERED' ? 'ARRIVED_AT_CUSTOMER' : order.deliveryStage;
  if (!stage || !COLUMN_ORDER.includes(stage)) return fallback;
  return isVisibleStage(stage, enabledStages) ? stage : fallback;
}

// Colunas a mostrar. A de aprovação aparece com aceite manual ou quando há
// algum pedido esperando (para nenhum pedido ficar escondido).
export function boardColumns(orders, { enabledStages = [], autoAccept }) {
  const ids = COLUMN_ORDER.filter((id) => isVisibleStage(id, enabledStages));
  const hasPending = orders.some((order) => columnFor(order, enabledStages) === 'PENDING');
  const visible = !autoAccept || hasPending ? ['PENDING', ...ids] : ids;
  return visible.map((id) => ({
    id,
    ...COLUMN_INFO[id],
    orders: orders.filter((order) => columnFor(order, enabledStages) === id),
  }));
}
