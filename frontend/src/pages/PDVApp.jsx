import { useState, useEffect } from 'react';
import api from '../services/api';
import { LogOut } from 'lucide-react';

import Sidebar from '../components/Sidebar';
import OrderDetailModal from '../components/OrderDetailModal';
import OrdersPage from './OrdersPage';
import HistoryPage from './HistoryPage';
import MenuPage from './MenuPage';
import SettingsPage from './SettingsPage';
import ReportsPage from './ReportsPage';
import StoreStatusControls from '../components/StoreStatusControls';
import { orderService, storeService } from '../services/api';
import { useAuth } from '../context/AuthContext';

const PLATFORM_NAMES = { KEETA: 'Keeta', IFOOD: 'iFood', BALCAO: 'Balcão' };

// Converte o pedido da API para o formato usado pelas telas do PDV
function formatOrder(order) {
  let displayStatus = order.status;
  if (order.status === 'PENDING' || order.status === 'NEW') displayStatus = 'PENDING';
  else if (order.status === 'READY_FOR_PICKUP') displayStatus = 'READY';
  else if (order.status === 'DELIVERY_IN_PROGRESS') displayStatus = 'DISPATCHED';
  else if (order.status === 'CANCELLED') displayStatus = 'CANCELED';
  else if (order.status === 'DELIVERED' || order.status === 'COMPLETED' || order.status === 'PICKED_UP') {
    displayStatus = 'COMPLETED';
  }

  const processedItems = order.items.map(item => ({
    name: item.menuItemName,
    quantity: item.quantity,
    price: item.unitPrice,
    originalPrice: item.originalPrice,
    total: item.total,
    subtotal: item.subtotal,
    options: item.options || []
  }));

  return {
    id: order.id,
    storeId: order.storeId,
    storeName: order.storeName || null,
    keetaId: order.externalId,
    displayId: order.displayId || order.pickupCode || order.id,
    pickupCode: order.pickupCode || null,
    customer: order.customerName,
    platform: PLATFORM_NAMES[order.platform] || 'Keeta',
    platformId: order.platform || 'KEETA',
    status: displayStatus,
    total: order.totalPrice,
    itemsPrice: order.itemsPrice || 0,
    otherFeesTotal: order.otherFeesTotal || 0,
    discount: order.discount || 0,
    subtotal: processedItems.reduce((acc, i) => acc + i.total, 0),
    paymentType: order.paymentType,
    paymentMethods: order.paymentMethods || [],
    address: order.deliveryAddress,
    addressDetails: order.deliveryDetails || {},
    coordinates: order.latitude != null && order.longitude != null ? { lat: order.latitude, lng: order.longitude } : null,
    deliveredBy: order.deliveredBy || null,
    phone: order.customerPhone || null,
    phoneExtension: order.customerPhoneExtension || null,
    customerDocument: order.customerDocument || null,
    customerOrdersCount: order.customerOrdersCount ?? null,
    dataProtected: Boolean(order.dataProtected),
    deliveryStage: order.deliveryStage || null,
    deliveryStageAt: order.deliveryStageAt || null,
    pickupEta: order.pickupEta || null,
    createdAt: order.createdAt,
    // Cartão de pedido e Histórico mostram/ordenam por "time".
    time: order.createdAt,
    items: processedItems,
    fees: order.fees || [],
    discounts: order.discounts || []
  };
}

function PDVApp() {
  const { user, logout } = useAuth();

  const [orders, setOrders] = useState([]);
  // Restaurantes (marcas) da conta: o quadro junta os pedidos de todas
  const [stores, setStores] = useState([]);
  const [selectedOrder, setSelectedOrder] = useState(null);
  const [activeTab, setActiveTab] = useState("orders");
  // Loja aberta/fechada em cada delivery: { keeta: {linked, isOpen}, ifood: {linked, isOpen, closedUntil} }
  const [storeStatus, setStoreStatus] = useState({ keeta: { linked: false }, ifood: { linked: false } });
  const [isConnected, setIsConnected] = useState(false);
  const [statusLoading, setStatusLoading] = useState(null); // 'keeta' | 'ifood'

  const [config, setConfig] = useState({
    autoAccept: true,
    enabledDeliveryStages: [],
    keetaId: "",
    keetaStatus: "DISCONNECTED",
  });

  // 1. Busca a configuração da loja do usuário logado
  useEffect(() => {
    const fetchConfig = async (onlyStoreStatus = false) => {
      try {
        const res = await api.get('/config');
        if (res.data) {
          // Na recarga periódica só o status muda: não desfaz edições ainda
          // não salvas na tela de Configurações.
          if (!onlyStoreStatus) setConfig(prev => ({
            ...prev,
            autoAccept: res.data.autoAccept,
            enabledDeliveryStages: res.data.enabledDeliveryStages || [],
            keetaId: res.data.keetaMerchantId || "",
            keetaStatus: res.data.keetaMerchantId ? "CONNECTED" : "DISCONNECTED",
          }));
          setStoreStatus(prev => ({ ...prev, keeta: { linked: Boolean(res.data.keetaMerchantId), isOpen: res.data.isStoreOpen !== false } }));
        }
        setIsConnected(true);
      } catch (error) {
        console.error("Erro ao buscar configurações do backend:", error);
        setIsConnected(false);
      }
    };

    fetchConfig();
    // O backend consulta a Keeta (no máximo a cada 5 min) e traz o status da
    // loja; assim o botão da Keeta acompanha o que vale na Keeta.
    const interval = setInterval(() => fetchConfig(true), 5 * 60 * 1000);
    return () => clearInterval(interval);
  }, []);

  // iFood: aberta/fechada vem das pausas da loja no iFood. Recarrega a cada
  // 5 min e ao trocar de aba (ex.: depois de ligar a loja nas Configurações).
  const fetchIfoodStatus = () => api.get('/ifood/store-status')
    .then(({ data }) => setStoreStatus(prev => ({ ...prev, ifood: data })))
    .catch(error => setStoreStatus(prev => ({ ...prev, ifood: { ...(error.response?.data || {}), linked: prev.ifood.linked || error.response?.status === 502, isOpen: null } })));
  useEffect(() => {
    fetchIfoodStatus();
    const interval = setInterval(fetchIfoodStatus, 5 * 60 * 1000);
    return () => clearInterval(interval);
  }, [activeTab]);

  // iFood: com o PDV aberto, busca os eventos das lojas do iFood a cada 30s
  // (o backend ignora chamadas repetidas de outras abas). O webhook, quando
  // configurado no portal do iFood, entrega os pedidos sem esperar.
  useEffect(() => {
    const pollIfood = () => api.post('/ifood/poll').then(({ data }) => { if (data?.events) fetchOrders(); }).catch(() => {});
    pollIfood();
    const interval = setInterval(pollIfood, 30000);
    return () => clearInterval(interval);
  }, []);

  // Preferências de cada marca (aceite, etapas). Recarrega quando a loja
  // selecionada salva as Configurações.
  useEffect(() => {
    storeService.list().then(({ data }) => setStores(Array.isArray(data) ? data : [])).catch(() => {});
  }, [config.autoAccept, config.enabledDeliveryStages]);

  const multiBrand = stores.length > 1;
  const storeById = Object.fromEntries(stores.map(store => [store.id, store]));
  // Quadro combinado: aprovação manual se alguma marca usa; colunas de etapas
  // de qualquer marca. Os botões de cada pedido seguem a marca dele.
  const boardConfig = multiBrand ? {
    autoAccept: stores.every(store => store.autoAccept),
    enabledDeliveryStages: [...new Set(stores.flatMap(store => store.enabledDeliveryStages || []))],
  } : config;
  const stagesForOrder = (order) => storeById[order?.storeId]?.enabledDeliveryStages ?? config.enabledDeliveryStages;
  const keepBrand = (raw) => formatOrder({ ...raw, storeName: raw.storeName || storeById[raw.storeId]?.name });

  // 2. Busca de Pedidos (da loja do usuário logado)
  const fetchOrders = async () => {
    try {
      const response = await orderService.getAll();
      if (!response.data) return;

      const formattedOrders = response.data.map(formatOrder);

      setOrders(formattedOrders);
      setIsConnected(true);
    } catch (error) {
      console.error("Erro ao buscar pedidos:", error);
      setIsConnected(false);
    }
  };

  useEffect(() => {
    if (activeTab === 'orders' || activeTab === 'history') {
      fetchOrders();
      const interval = setInterval(fetchOrders, 5000);
      return () => clearInterval(interval);
    }
  }, [activeTab]);

  // 3. Mudar Status do Pedido
  const handleStatusChange = async (orderId, newStatus) => {
    let backendStatus = newStatus;
    if (newStatus === 'READY') backendStatus = 'READY_FOR_PICKUP';
    else if (newStatus === 'DISPATCHED') backendStatus = 'DELIVERY_IN_PROGRESS';
    else if (newStatus === 'CANCELED') backendStatus = 'CANCELED';
    else if (newStatus === 'COMPLETED') backendStatus = 'COMPLETED';

    try {
      await orderService.updateStatus(orderId, backendStatus);
      setSelectedOrder(null);  // fecha o modal e volta ao board
      fetchOrders();
    } catch (error) {
      alert("Erro ao atualizar pedido!");
    }
  };

  // 4. Etapa da entrega própria (entregador a caminho, na loja, coletado...)
  const handleStageChange = async (orderId, stage) => {
    try {
      const { data } = await orderService.updateDeliveryStage(orderId, stage);
      setSelectedOrder(keepBrand(data.order));
      fetchOrders();
      if (data.keeta?.warning) alert(data.keeta.warning);
    } catch (error) {
      alert(error.response?.data?.error || 'Erro ao atualizar a etapa da entrega.');
    }
  };

  const toggleStoreStatus = async (platform) => {
    const nextOpen = platform.isOpen !== true;
    if (!nextOpen && !confirm(`Fechar a loja no ${platform.name}? Ela para de receber pedidos de lá até você abrir de novo.`)) return;
    setStatusLoading(platform.key);
    try {
      const { data } = await api.post(platform.key === 'keeta' ? '/keeta/store-status' : '/ifood/store-status', { isOpen: nextOpen });
      setStoreStatus(prev => ({
        ...prev,
        [platform.key]: platform.key === 'ifood' && data?.status ? data.status : { ...prev[platform.key], isOpen: nextOpen },
      }));
    } catch (error) {
      alert(`Não foi possível ${nextOpen ? 'abrir' : 'fechar'} a loja no ${platform.name}: ` + (error.response?.data?.error || error.message));
    } finally {
      setStatusLoading(null);
    }
  };

  return (
    <div className="flex h-screen bg-slate-50 font-sans overflow-hidden text-slate-800">
      <Sidebar activeTab={activeTab} setActiveTab={setActiveTab} user={user} onLogout={logout} />

      <main className="flex-1 flex flex-col relative overflow-hidden bg-slate-100">
        <header className="h-20 px-8 flex items-center justify-between gap-4 bg-white/80 backdrop-blur-md sticky top-0 z-10 border-b border-slate-200">
          <div className="min-w-0">
            <h2 className="text-2xl font-bold text-slate-800 truncate">
              {activeTab === 'orders' ? 'Fluxo de Pedidos' : activeTab === 'history' ? 'Histórico' : activeTab === 'reports' ? 'Relatórios' : activeTab === 'menu' ? 'Cardápio' : 'Configurações'}
            </h2>
            <div className="flex items-center gap-2 mt-1 min-w-0">
              <span className={`w-2 h-2 rounded-full shrink-0 ${isConnected ? 'bg-green-500 animate-pulse' : 'bg-red-500'}`}></span>
              <p className="text-xs font-bold text-slate-500">{isConnected ? `Online` : 'Offline'}</p>
              {user?.storeName && (
                <span className="text-xs font-bold text-slate-400 ml-2 truncate">• {user.storeName}</span>
              )}
            </div>
          </div>

          <div className="flex items-center gap-4 shrink-0">
            <StoreStatusControls
              platforms={[
                { key: 'keeta', name: 'Keeta', ...storeStatus.keeta },
                { key: 'ifood', name: 'iFood', ...storeStatus.ifood },
              ]}
              loadingKey={statusLoading}
              onToggle={toggleStoreStatus}
            />

            <button
              onClick={logout}
              title="Sair da conta"
              className="p-2.5 rounded-full text-slate-400 hover:text-red-600 hover:bg-red-50 transition-all"
            >
              <LogOut className="w-5 h-5" />
            </button>
          </div>
        </header>

        {/* Só o quadro de pedidos rola na horizontal (colunas); as demais abas
            (Histórico, Cardápio, Configurações) rolam na vertical. min-h-0
            deixa a área encolher dentro do flex para a rolagem funcionar. */}
        <div className={`flex-1 min-h-0 p-8 ${activeTab === 'orders' ? 'overflow-x-auto overflow-y-hidden' : 'overflow-y-auto'}`}>
          {activeTab === 'orders' && <OrdersPage orders={orders} config={boardConfig} showBrand={multiBrand} onSelectOrder={setSelectedOrder} />}
          {activeTab === 'history' && <HistoryPage orders={orders} showBrand={multiBrand} onSelectOrder={setSelectedOrder} />}
          {activeTab === 'settings' && <SettingsPage config={config} setConfig={setConfig} />}
          {activeTab === 'menu' && <MenuPage />}
          {activeTab === 'reports' && <ReportsPage stores={stores} />}
        </div>
      </main>

      <OrderDetailModal
        order={selectedOrder}
        onClose={() => setSelectedOrder(null)}
        onStatusChange={handleStatusChange}
        onStageChange={handleStageChange}
        enabledStages={stagesForOrder(selectedOrder)}
        showBrand={multiBrand}
        onOrderUpdated={(raw) => { setSelectedOrder(keepBrand(raw)); fetchOrders(); }}
      />
    </div>
  );
}

export default PDVApp;
