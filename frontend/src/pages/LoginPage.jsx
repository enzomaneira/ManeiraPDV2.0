import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ChefHat, Mail, Lock, LogIn, Loader2, AlertCircle } from 'lucide-react';
import { useAuth } from '../context/AuthContext';

export default function LoginPage() {
    const { login } = useAuth();
    const navigate = useNavigate();

    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);

    const handleSubmit = async (e) => {
        e.preventDefault();
        setError(null);
        setLoading(true);
        try {
            await login(email, password);
            navigate('/', { replace: true });
        } catch (err) {
            setError(err.response?.data?.error || 'Não foi possível entrar. Tente novamente.');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="min-h-screen flex items-center justify-center bg-slate-100 px-4">
            <div className="w-full max-w-md">
                {/* Logo */}
                <div className="flex flex-col items-center mb-8">
                    <div className="w-16 h-16 bg-indigo-500 rounded-2xl flex items-center justify-center shadow-lg shadow-indigo-500/40 mb-4">
                        <ChefHat className="text-white w-8 h-8" />
                    </div>
                    <h1 className="text-2xl font-bold text-slate-800 tracking-tight">
                        Maneira<span className="text-indigo-500">PDV</span>
                    </h1>
                    <p className="text-slate-500 text-sm mt-1">Acesse o painel do seu restaurante</p>
                </div>

                <form onSubmit={handleSubmit} className="bg-white p-8 rounded-2xl shadow-sm border border-slate-200 space-y-5">
                    <h2 className="text-xl font-bold text-slate-800">Entrar</h2>

                    {error && (
                        <div className="p-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm font-medium flex items-center gap-2">
                            <AlertCircle className="w-4 h-4 shrink-0" />
                            {error}
                        </div>
                    )}

                    <div>
                        <label className="block text-sm font-bold text-slate-600 mb-2">E-mail</label>
                        <div className="relative">
                            <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
                            <input
                                type="email"
                                required
                                value={email}
                                onChange={(e) => setEmail(e.target.value)}
                                placeholder="voce@exemplo.com"
                                className="w-full pl-10 pr-4 py-3 bg-slate-50 border border-slate-200 rounded-xl focus:ring-2 focus:ring-indigo-400 focus:outline-none font-medium text-slate-700"
                            />
                        </div>
                    </div>

                    <div>
                        <label className="block text-sm font-bold text-slate-600 mb-2">Senha</label>
                        <div className="relative">
                            <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
                            <input
                                type="password"
                                required
                                value={password}
                                onChange={(e) => setPassword(e.target.value)}
                                placeholder="••••••••"
                                className="w-full pl-10 pr-4 py-3 bg-slate-50 border border-slate-200 rounded-xl focus:ring-2 focus:ring-indigo-400 focus:outline-none font-medium text-slate-700"
                            />
                        </div>
                    </div>

                    <button
                        type="submit"
                        disabled={loading}
                        className={`w-full flex items-center justify-center gap-2 py-3 rounded-xl font-bold transition-all shadow-md ${loading ? 'bg-slate-300 text-slate-500 cursor-not-allowed' : 'bg-indigo-600 hover:bg-indigo-700 text-white shadow-indigo-200'}`}
                    >
                        {loading ? <Loader2 className="w-5 h-5 animate-spin" /> : <LogIn className="w-5 h-5" />}
                        {loading ? 'Entrando...' : 'Entrar'}
                    </button>

                    <p className="text-center text-sm text-slate-500">
                        Ainda não tem uma conta?{' '}
                        <Link to="/register" className="text-indigo-600 font-bold hover:underline">
                            Cadastre seu restaurante
                        </Link>
                    </p>
                </form>
            </div>
        </div>
    );
}
