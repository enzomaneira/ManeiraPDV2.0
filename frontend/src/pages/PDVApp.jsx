import { useState, useEffect } from 'react';
import api from '../services/api';
import { Power, Loader2, LogOut } from 'lucide-react';

import Sidebar from '../components/Sidebar';
import OrderDetailModal from '../components/OrderDetailModal';
import OrdersPage from './OrdersPage';
import HistoryPage from './HistoryPage';
import SettingsPage from './SettingsPage';
import { orderService } from '../services/api';
import { useAuth } from '../context/AuthContext';

function PDVApp() {
  const { user, logout } = useAuth();

  const [orders, setOrders] = useState([]);
  const [selectedOrder, setSelectedOrder] = useState(null);
  const [activeTab, setActiveTab] = useState("orders");
  const [isStoreOpen, setIsStoreOpen] = useState(true);
  const [isConnected, setIsConnected] = useState(false);
  const [isStatusLoading, setIsStatusLoading] = useState(false);

  const [config, setConfig] = useState({
    autoAccept: true,
    keetaId: "",
    keetaStatus: "DISCONNECTED",
  });

  // 1. Busca a configuração da loja do usuário logado
  useEffect(() => {
    const fetchConfig = async () => {
      try {
        const res = await api.get('/config');
        if (res.data) {
          setConfig(prev => ({
            ...prev,
            autoAccept: res.data.autoAccept,
            keetaId: res.data.keetaMerchantId || "",
            keetaStatus: res.data.keetaMerchantId ? "CONNECTED" : "DISCONNECTED",
          }));
          if (res.data.isStoreOpen !== undefined) {
            setIsStoreOpen(res.data.isStoreOpen);
          }
        }
        setIsConnected(true);
      } catch (error) {
        console.error("Erro ao buscar configurações do backend:", error);
        setIsConnected(false);
      }
    };

    fetchConfig();
  }, []);

  // 2. Busca de Pedidos (da loja do usuário logado)
  const fetchOrders = async () => {
    try {
      const response = await orderService.getAll();
      if (!response.data) return;

      const formattedOrders = response.data.map(order => {
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
          keetaId: order.externalId,
          displayId: order.pickupCode || order.displayId || order.id,
          customer: order.customerName,
          platform: "Keeta",
          status: displayStatus,
          total: order.totalPrice,
          itemsPrice: order.itemsPrice || 0,
          otherFeesTotal: order.otherFeesTotal || 0,
          discount: order.discount || 0,
          subtotal: processedItems.reduce((acc, i) => acc + i.total, 0),
          paymentType: order.paymentType,
          address: order.deliveryAddress,
          createdAt: order.createdAt,
          items: processedItems,
          fees: order.fees || [],
          discounts: order.discounts || []
        };
      });

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
      fetchOrders();
    } catch (error) {
      alert("Erro ao atualizar pedido!");
    }
  };

  const toggleStoreStatus = async () => {
    const nextStatus = !isStoreOpen;
    setIsStatusLoading(true);

    try {
      const response = await api.post('/keeta/store-status', {
        isOpen: nextStatus,
      });

      setIsStoreOpen(nextStatus);
      alert(`Loja agora está ${nextStatus ? 'ABERTA' : 'FECHADA'}.`);
    } catch (error) {
      console.error("Erro na requisição:", error);
      alert("ERRO NO BACKEND: " + (error.response?.data?.error || error.message));
    } finally {
      setIsStatusLoading(false);
    }
  };

  return (
    <div className="flex h-screen bg-slate-50 font-sans overflow-hidden text-slate-800">
      <Sidebar activeTab={activeTab} setActiveTab={setActiveTab} user={user} onLogout={logout} />

      <main className="flex-1 flex flex-col relative overflow-hidden bg-slate-100">
        <header className="h-20 px-8 flex items-center justify-between bg-white/80 backdrop-blur-md sticky top-0 z-10 border-b border-slate-200">
          <div>
            <h2 className="text-2xl font-bold text-slate-800">
              {activeTab === 'orders' ? 'Fluxo de Pedidos' : activeTab === 'history' ? 'Histórico' : activeTab === 'menu' ? 'Cardápio' : 'Configurações'}
            </h2>
            <div className="flex items-center gap-2 mt-1">
              <span className={`w-2 h-2 rounded-full ${isConnected ? 'bg-green-500 animate-pulse' : 'bg-red-500'}`}></span>
              <p className="text-xs font-bold text-slate-500">{isConnected ? `Online` : 'Offline'}</p>
              {user?.storeName && (
                <span className="text-xs font-bold text-slate-400 ml-2">• {user.storeName}</span>
              )}
            </div>
          </div>

          <div className="flex items-center gap-4">
            <button
              onClick={toggleStoreStatus}
              disabled={isStatusLoading}
              className={`flex items-center gap-2 px-5 py-2.5 rounded-full font-bold transition-all shadow-sm border ${isStatusLoading ? 'opacity-70 cursor-not-allowed' : 'active:scale-95'
                } ${isStoreOpen
                  ? 'bg-green-50 text-green-700 border-green-200 hover:bg-green-100'
                  : 'bg-red-50 text-red-700 border-red-200 hover:bg-red-100'
                }`}
            >
              {isStatusLoading ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Power className="w-4 h-4" />
              )}
              {isStatusLoading ? 'PROCESSANDO...' : isStoreOpen ? 'LOJA ABERTA' : 'LOJA FECHADA'}
            </button>

            <button
              onClick={logout}
              title="Sair da conta"
              className="p-2.5 rounded-full text-slate-400 hover:text-red-600 hover:bg-red-50 transition-all"
            >
              <LogOut className="w-5 h-5" />
            </button>
          </div>
        </header>

        <div className={`flex-1 p-8 ${activeTab === 'history' ? 'overflow-y-auto' : 'overflow-x-auto overflow-y-hidden'}`}>
          {activeTab === 'orders' && <OrdersPage orders={orders} config={config} onSelectOrder={setSelectedOrder} />}
          {activeTab === 'history' && <HistoryPage orders={orders} />}
          {activeTab === 'settings' && <SettingsPage config={config} setConfig={setConfig} />}
          {activeTab === 'menu' && <div className="flex items-center justify-center h-full text-slate-400 font-medium">Em construção...</div>}
        </div>
      </main>

      <OrderDetailModal
        order={selectedOrder}
        onClose={() => setSelectedOrder(null)}
        onStatusChange={handleStatusChange}
      />
    </div>
  );
}

export default PDVApp;
