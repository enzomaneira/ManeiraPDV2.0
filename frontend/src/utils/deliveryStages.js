// Etapas da entrega e colunas do quadro de pedidos.
//
// As etapas usam os nomes do /tracking da Keeta. Na entrega da Keeta elas vêm
// dos eventos do entregador; na entrega própria é o restaurante que avança.

export const STAGES = [
  'PICKUP_ONGOING',
  'ARRIVED_AT_MERCHANT',
  'ORDER_PICKED',
  'DELIVERY_ONGOING',
  'ARRIVED_AT_CUSTOMER',
  'ORDER_DELIVERED',
];

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

// Próximas etapas possíveis para o restaurante (entrega própria)
export function nextOwnStages(order) {
  if (isKeetaDelivery(order)) return [];
  if (!['PREPARING', 'READY', 'DISPATCHED'].includes(order.status)) return [];
  const current = stageRank(order.deliveryStage);
  return STAGES.filter((stage, index) => index > current
    && (order.status !== 'PREPARING' || STAGES_DURING_PREPARATION.includes(stage)));
}

const SIMPLE_COLUMNS = [
  { id: 'PREPARING', title: 'Em Preparo', theme: 'orange', icon: 'chef' },
  { id: 'READY', title: 'Pronto p/ Entrega', theme: 'green', icon: 'check' },
  { id: 'DISPATCHED', title: 'Entregas', theme: 'purple', icon: 'bike' },
];

const DETAILED_COLUMNS = [
  { id: 'PREPARING', title: 'Em Preparo', theme: 'orange', icon: 'chef' },
  { id: 'READY', title: 'Pronto p/ Entrega', theme: 'green', icon: 'check' },
  { id: 'PICKUP_ONGOING', title: 'Entregador a caminho', theme: 'sky', icon: 'navigation' },
  { id: 'ARRIVED_AT_MERCHANT', title: 'Entregador na loja', theme: 'teal', icon: 'store' },
  { id: 'ORDER_PICKED', title: 'Pedido coletado', theme: 'indigo', icon: 'package' },
  { id: 'DELIVERY_ONGOING', title: 'Saiu para entrega', theme: 'purple', icon: 'bike' },
  { id: 'ARRIVED_AT_CUSTOMER', title: 'Chegou ao cliente', theme: 'pink', icon: 'map' },
];

const PENDING_COLUMN = { id: 'PENDING', title: 'Aprovação Pendente', theme: 'blue', icon: 'alert' };

// Coluna de cada pedido. Todo pedido em andamento cai em exatamente uma
// coluna, nos dois modos; concluídos e cancelados vão para o Histórico (null).
export function columnFor(order, detailed) {
  const { status } = order;
  if (status === 'PENDING' || status === 'NEW') return 'PENDING';
  if (status === 'COMPLETED' || status === 'CANCELED') return null;
  if (status === 'PREPARING') return 'PREPARING';

  if (!detailed) return status === 'READY' ? 'READY' : 'DISPATCHED';

  switch (order.deliveryStage) {
    case 'PICKUP_ONGOING':
    case 'ARRIVED_AT_MERCHANT':
    case 'ORDER_PICKED':
    case 'DELIVERY_ONGOING':
    case 'ARRIVED_AT_CUSTOMER':
      return order.deliveryStage;
    case 'ORDER_DELIVERED':
      return 'ARRIVED_AT_CUSTOMER';
    default:
      return status === 'READY' ? 'READY' : 'DELIVERY_ONGOING';
  }
}

// Colunas a mostrar. A de aprovação aparece com aceite manual ou quando há
// algum pedido esperando (para nenhum pedido ficar escondido).
export function boardColumns(orders, { detailed, autoAccept }) {
  const columns = detailed ? DETAILED_COLUMNS : SIMPLE_COLUMNS;
  const hasPending = orders.some((order) => columnFor(order, detailed) === 'PENDING');
  const visible = !autoAccept || hasPending ? [PENDING_COLUMN, ...columns] : columns;
  return visible.map((column) => ({
    ...column,
    orders: orders.filter((order) => columnFor(order, detailed) === column.id),
  }));
}
