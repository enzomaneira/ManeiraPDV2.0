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

export const categoryService = {
    getAll: () => api.get('/stores/me/categories'),
    create: (data) => api.post('/stores/me/categories', data),
    update: (categoryId, data) => api.put(`/stores/me/categories/${categoryId}`, data),
    delete: (categoryId) => api.delete(`/stores/me/categories/${categoryId}`),
};

export const menuService = {
    getAll: (categoryId) => {
        const params = categoryId ? { categoryId } : {};
        return api.get('/stores/me/menu', { params });
    },
    create: (data) => api.post('/stores/me/menu', data),
    update: (itemId, data) => api.put(`/stores/me/menu/${itemId}`, data),
    delete: (itemId) => api.delete(`/stores/me/menu/${itemId}`),
    // OptionGroups
    linkOptionGroup: (itemId, optionGroupId) => api.post(`/stores/me/menu/${itemId}/option-groups`, { optionGroupId }),
    unlinkOptionGroup: (itemId, groupId) => api.delete(`/stores/me/menu/${itemId}/option-groups/${groupId}`),
    // Availabilities
    linkAvailability: (itemId, availabilityId) => api.post(`/stores/me/menu/${itemId}/availabilities`, { availabilityId }),
    unlinkAvailability: (itemId, availId) => api.delete(`/stores/me/menu/${itemId}/availabilities/${availId}`),
};

export const optionGroupService = {
    getAll: () => api.get('/stores/me/option-groups'),
    create: (data) => api.post('/stores/me/option-groups', data),
    update: (groupId, data) => api.put(`/stores/me/option-groups/${groupId}`, data),
    delete: (groupId) => api.delete(`/stores/me/option-groups/${groupId}`),
    // Options
    createOption: (groupId, data) => api.post(`/stores/me/option-groups/${groupId}/options`, data),
    deleteOption: (groupId, optionId) => api.delete(`/stores/me/option-groups/${groupId}/options/${optionId}`),
};

export const availabilityService = {
    getAll: () => api.get('/stores/me/availabilities'),
    create: (data) => api.post('/stores/me/availabilities', data),
    update: (availId, data) => api.put(`/stores/me/availabilities/${availId}`, data),
    delete: (availId) => api.delete(`/stores/me/availabilities/${availId}`),
};

export const keetaSyncService = {
    syncMenu: () => api.post('/keeta/sync-menu'),
};

export default api;
