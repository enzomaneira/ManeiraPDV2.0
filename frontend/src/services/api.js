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
    requestPasswordReset: (email) => api.post('/auth/request-password-reset', { email }),
    resetPassword: (token, password) => api.post('/auth/reset-password', { token, password }),
    me: () => api.get('/auth/me'),
    updateMe: (data) => api.put('/auth/me', data),
    changePassword: (currentPassword, newPassword) =>
        api.post('/auth/change-password', { currentPassword, newPassword }),
};

export const storeService = {
    rename: (name) => api.put('/stores/me', { name }),
};

export const imageService = {
    status: () => api.get('/stores/me/images/status'),
    // Envia a foto; o backend ajusta (4:3, até 1200×900, JPG) e manda ao Cloudflare R2.
    upload: (file, name) => {
        const form = new FormData();
        form.append('image', file);
        if (name) form.append('name', name);
        return api.post('/stores/me/images', form);
    },
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
    // { sync: false } não avisa a Keeta nesta chamada (a tela faz um envio só no fim)
    create: (data, { sync = true } = {}) => api.post('/stores/me/option-groups', data, { params: sync ? {} : { sync: 0 } }),
    update: (groupId, data, { sync = true } = {}) => api.put(`/stores/me/option-groups/${groupId}`, data, { params: sync ? {} : { sync: 0 } }),
    delete: (groupId) => api.delete(`/stores/me/option-groups/${groupId}`),
    // Options
    createOption: (groupId, data, { sync = true } = {}) => api.post(`/stores/me/option-groups/${groupId}/options`, data, { params: sync ? {} : { sync: 0 } }),
    updateOption: (groupId, optionId, data, { sync = true } = {}) => api.put(`/stores/me/option-groups/${groupId}/options/${optionId}`, data, { params: sync ? {} : { sync: 0 } }),
    deleteOption: (groupId, optionId, { sync = true } = {}) => api.delete(`/stores/me/option-groups/${groupId}/options/${optionId}`, { params: sync ? {} : { sync: 0 } }),
    // Define de uma vez quais produtos usam o grupo (um único envio para a Keeta)
    setItems: (groupId, itemIds) => api.put(`/stores/me/option-groups/${groupId}/items`, { itemIds }),
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
