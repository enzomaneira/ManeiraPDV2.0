import { createContext, useContext, useState, useEffect } from 'react';
import { authService, TOKEN_KEY, selectStore } from '../services/api';

// Contexto global de autenticação. Guarda o usuário logado e expõe
// as funções de login/cadastro/logout para o restante do app.
const AuthContext = createContext(null);

export function AuthProvider({ children }) {
    const [user, setUser] = useState(null);
    const [loading, setLoading] = useState(true); // true enquanto validamos o token salvo

    // Ao carregar o app, se já existir um token salvo, valida ele
    // chamando /api/auth/me. Isso mantém o usuário logado ao recarregar a página.
    useEffect(() => {
        const token = localStorage.getItem(TOKEN_KEY);

        if (!token) {
            setLoading(false);
            return;
        }

        authService.me()
            .then((res) => setUser(res.data))
            .catch(() => {
                localStorage.removeItem(TOKEN_KEY);
                setUser(null);
            })
            .finally(() => setLoading(false));
    }, []);

    const login = async (email, password) => {
        const res = await authService.login(email, password);
        selectStore(null);  // começa no primeiro restaurante da conta
        localStorage.setItem(TOKEN_KEY, res.data.token);
        setUser(res.data.user);
        return res.data.user;
    };

    const register = async (name, email, password, storeName) => {
        const res = await authService.register(name, email, password, storeName);
        selectStore(null);
        localStorage.setItem(TOKEN_KEY, res.data.token);
        setUser(res.data.user);
        return res.data.user;
    };

    // Google: entra direto ou devolve { needsSignup, signupToken, name, email }
    const loginWithGoogle = async (credential) => {
        const res = await authService.googleLogin(credential);
        if (res.data.needsSignup) return res.data;
        selectStore(null);
        localStorage.setItem(TOKEN_KEY, res.data.token);
        setUser(res.data.user);
        return res.data;
    };

    const registerWithGoogle = async (signupToken, storeName, name) => {
        const res = await authService.googleRegister(signupToken, storeName, name);
        selectStore(null);
        localStorage.setItem(TOKEN_KEY, res.data.token);
        setUser(res.data.user);
        return res.data.user;
    };

    const logout = () => {
        localStorage.removeItem(TOKEN_KEY);
        selectStore(null);
        setUser(null);
    };

    return (
        <AuthContext.Provider value={{ user, setUser, loading, login, register, loginWithGoogle, registerWithGoogle, logout }}>
            {children}
        </AuthContext.Provider>
    );
}

// Hook de conveniência para consumir o contexto em qualquer componente
export function useAuth() {
    const context = useContext(AuthContext);
    if (!context) {
        throw new Error('useAuth precisa ser usado dentro de um <AuthProvider>');
    }
    return context;
}
