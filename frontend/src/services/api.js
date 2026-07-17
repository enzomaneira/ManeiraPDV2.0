import axios from 'axios';

// Em desenvolvimento (npm run dev): usa o proxy do Vite → chama /api diretamente
// Em produção (Railway):           usa a variável VITE_API_URL configurada no Railway
//   Ex: VITE_API_URL = https://maneira-backend-production.up.railway.app
//
// Se VITE_API_URL não estiver definida, usa caminho relativo (proxy do Vite)
const BASE_URL = import.meta.env.VITE_API_URL
    ? `${import.meta.env.VITE_API_URL}/api`
    : '/api';

const api = axios.create({
    baseURL: BASE_URL,
});

export const orderService = {
    getAll: (storeId) => api.get(`/orders/store/${storeId}`),
    
    updateStatus: (orderId, newStatus) => api.patch(`/orders/${orderId}/status`, { 
        status: newStatus 
    }),
    
    // Auth URL 
    getKeetaAuthUrl: () => 'https://merchant.mykeeta.com/m/web/openapi/authorize?locale=en®ion=BR&cityId=110200008&risk_cost_id=&responseType=client_credentials&appId=2816859805&redirectUri=http://localhost:8080/api/keeta/callback&state=&scope=all/#/app-activation'
};

export default api;