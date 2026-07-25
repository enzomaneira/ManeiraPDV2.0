import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ChefHat, Mail, Lock, User, Store, UserPlus, Loader2, AlertCircle } from 'lucide-react';
import { useAuth } from '../context/AuthContext';

export default function RegisterPage() {
    const { register } = useAuth();
    const navigate = useNavigate();

    const [name, setName] = useState('');
    const [storeName, setStoreName] = useState('');
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [confirmPassword, setConfirmPassword] = useState('');
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);

    const handleSubmit = async (e) => {
        e.preventDefault();
        setError(null);

        if (password !== confirmPassword) {
            setError('As senhas não coincidem.');
            return;
        }

        setLoading(true);
        try {
            await register(name, email, password, storeName);
            navigate('/', { replace: true });
        } catch (err) {
            setError(err.response?.data?.error || 'Não foi possível criar sua conta. Tente novamente.');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="min-h-screen flex items-center justify-center bg-slate-100 px-4 py-10">
            <div className="w-full max-w-md">
                {/* Logo */}
                <div className="flex flex-col items-center mb-8">
                    <div className="w-16 h-16 bg-indigo-500 rounded-2xl flex items-center justify-center shadow-lg shadow-indigo-500/40 mb-4">
                        <ChefHat className="text-white w-8 h-8" />
                    </div>
                    <h1 className="text-2xl font-bold text-slate-800 tracking-tight">
                        Maneira<span className="text-indigo-500">PDV</span>
                    </h1>
                    <p className="text-slate-500 text-sm mt-1">Crie sua conta e cadastre seu restaurante</p>
                </div>

                <form onSubmit={handleSubmit} className="bg-white p-8 rounded-2xl shadow-sm border border-slate-200 space-y-5">
                    <h2 className="text-xl font-bold text-slate-800">Criar conta</h2>

                    {error && (
                        <div className="p-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm font-medium flex items-center gap-2">
                            <AlertCircle className="w-4 h-4 shrink-0" />
                            {error}
                        </div>
                    )}

                    <div>
                        <label className="block text-sm font-bold text-slate-600 mb-2">Seu nome</label>
                        <div className="relative">
                            <User className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
                            <input
                                type="text"
                                required
                                value={name}
                                onChange={(e) => setName(e.target.value)}
                                placeholder="Enzo Maneira"
                                className="w-full pl-10 pr-4 py-3 bg-slate-50 border border-slate-200 rounded-xl focus:ring-2 focus:ring-indigo-400 focus:outline-none font-medium text-slate-700"
                            />
                        </div>
                    </div>

                    <div>
                        <label className="block text-sm font-bold text-slate-600 mb-2">Nome do restaurante</label>
                        <div className="relative">
                            <Store className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
                            <input
                                type="text"
                                required
                                value={storeName}
                                onChange={(e) => setStoreName(e.target.value)}
                                placeholder="Restaurante do Enzo"
                                className="w-full pl-10 pr-4 py-3 bg-slate-50 border border-slate-200 rounded-xl focus:ring-2 focus:ring-indigo-400 focus:outline-none font-medium text-slate-700"
                            />
                        </div>
                        <p className="text-[10px] text-slate-400 mt-1 ml-1">
                            Este será o restaurante vinculado à sua conta e integrado com a Keeta.
                        </p>
                    </div>

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

                    <div className="grid grid-cols-2 gap-4">
                        <div>
                            <label className="block text-sm font-bold text-slate-600 mb-2">Senha</label>
                            <div className="relative">
                                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
                                <input
                                    type="password"
                                    required
                                    minLength={6}
                                    value={password}
                                    onChange={(e) => setPassword(e.target.value)}
                                    placeholder="••••••••"
                                    className="w-full pl-10 pr-4 py-3 bg-slate-50 border border-slate-200 rounded-xl focus:ring-2 focus:ring-indigo-400 focus:outline-none font-medium text-slate-700"
                                />
                            </div>
                        </div>

                        <div>
                            <label className="block text-sm font-bold text-slate-600 mb-2">Confirmar</label>
                            <div className="relative">
                                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
                                <input
                                    type="password"
                                    required
                                    minLength={6}
                                    value={confirmPassword}
                                    onChange={(e) => setConfirmPassword(e.target.value)}
                                    placeholder="••••••••"
                                    className="w-full pl-10 pr-4 py-3 bg-slate-50 border border-slate-200 rounded-xl focus:ring-2 focus:ring-indigo-400 focus:outline-none font-medium text-slate-700"
                                />
                            </div>
                        </div>
                    </div>

                    <button
                        type="submit"
                        disabled={loading}
                        className={`w-full flex items-center justify-center gap-2 py-3 rounded-xl font-bold transition-all shadow-md ${loading ? 'bg-slate-300 text-slate-500 cursor-not-allowed' : 'bg-indigo-600 hover:bg-indigo-700 text-white shadow-indigo-200'}`}
                    >
                        {loading ? <Loader2 className="w-5 h-5 animate-spin" /> : <UserPlus className="w-5 h-5" />}
                        {loading ? 'Criando conta...' : 'Criar conta'}
                    </button>

                    <p className="text-center text-sm text-slate-500">
                        Já tem uma conta?{' '}
                        <Link to="/login" className="text-indigo-600 font-bold hover:underline">
                            Entrar
                        </Link>
                    </p>
                </form>
            </div>
        </div>
    );
}
