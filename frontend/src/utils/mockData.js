export const MOCK_ORDERS = [
  {
    id: 99,
    customer: "Cliente Histórico",
    platform: "iFood",
    status: "CANCELED", 
    total: 55.00,
    time: new Date(Date.now() - 1000 * 60 * 120).toISOString(),
    items: [{ name: "Pizza G", quantity: 1, price: 55.00 }],
    address: "Rua Cancelada"
  },
  {
    id: 101,
    customer: "João Silva",
    platform: "Keeta",
    status: "PREPARING", 
    total: 45.90,
    time: new Date().toISOString(),
    items: [
      { name: "X-Bacon Maneiro", quantity: 2, price: 35.00 },
      { name: "Coca-Cola Lata", quantity: 2, price: 5.45 }
    ],
    address: "Rua das Flores, 123 - Centro"
  }
];