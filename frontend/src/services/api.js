import axios from 'axios';

// Em desenvolvimento (npm run dev): usa o proxy do Vite → chama /api diretamente
// Em produção (Railway):           usa a variável VITE_API_URL configurada no Railway
//   Ex: VITE_API_URL = https://backend-production-818f.up.railway.app
//
// Se VITE_API_URL não estiver definida, usa caminho relativo (proxy do Vite)
const BASE_URL = import.meta.env.VITE_API_URL
    ? `${import.meta.env.VITE_API_URL}/api`
    : '/api';

const api = axios.create({
    baseURL: BASE_URL,
});

// Chave usada para guardar o token JWT no navegador
export const TOKEN_KEY = 'maneirapdv_token';

// --- Interceptor: injeta o token JWT em toda requisição, se existir ---
api.interceptors.request.use((config) => {
    const token = localStorage.getItem(TOKEN_KEY);
    if (token) {
        config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
});

// --- Interceptor: se o backend responder 401 (token inválido/expirado),
//     limpa o token salvo e manda o usuário de volta para o login ---
api.interceptors.response.use(
    (response) => response,
    (error) => {
        if (error.response?.status === 401) {
            localStorage.removeItem(TOKEN_KEY);
            if (window.location.pathname !== '/login') {
                window.location.href = '/login';
            }
        }
        return Promise.reject(error);
    }
);

export const authService = {
    login: (email, password) => api.post('/auth/login', { email, password }),
    register: (name, email, password, storeName) =>
        api.post('/auth/register', { name, email, password, storeName }),
    me: () => api.get('/auth/me'),
};

export const orderService = {
    getAll: () => api.get('/orders/'),

    updateStatus: (orderId, newStatus) => api.patch(`/orders/${orderId}/status`, {
        status: newStatus
    }),
};

export const menuService = {
    getAll: () => api.get('/stores/me/menu'),
    create: (name, price) => api.post('/stores/me/menu', { name, price }),
    delete: (itemId) => api.delete(`/stores/me/menu/${itemId}`),
};

export default api;
