import { useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { ArrowLeft, ChefHat, KeyRound, Loader2, Lock } from 'lucide-react';
import { authService } from '../services/api';

export default function ResetPasswordPage() {
    const [searchParams] = useSearchParams();
    const navigate = useNavigate();
    const token = searchParams.get('token') || '';
    const [password, setPassword] = useState('');
    const [confirmation, setConfirmation] = useState('');
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(token ? null : 'O link de recuperação está incompleto.');
    const [message, setMessage] = useState(null);

    const handleSubmit = async (event) => {
        event.preventDefault();
        setError(null);
        setMessage(null);

        if (password.length < 6) {
            setError('A senha deve ter pelo menos 6 caracteres.');
            return;
        }
        if (password !== confirmation) {
            setError('As senhas não coincidem.');
            return;
        }

        setLoading(true);
        try {
            const response = await authService.resetPassword(token, password);
            setMessage(response.data.message);
            setTimeout(() => navigate('/login', { replace: true }), 1200);
        } catch (requestError) {
            setError(requestError.response?.data?.error || 'Não foi possível redefinir a senha.');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="min-h-screen flex items-center justify-center bg-slate-100 px-4">
            <div className="w-full max-w-md">
                <div className="flex flex-col items-center mb-8">
                    <div className="w-16 h-16 bg-indigo-500 rounded-2xl flex items-center justify-center shadow-lg shadow-indigo-500/40 mb-4">
                        <ChefHat className="text-white w-8 h-8" />
                    </div>
                    <h1 className="text-2xl font-bold text-slate-800 tracking-tight">
                        Maneira<span className="text-indigo-500">PDV</span>
                    </h1>
                </div>

                <form onSubmit={handleSubmit} className="bg-white p-8 rounded-2xl shadow-sm border border-slate-200 space-y-5">
                    <div>
                        <h2 className="text-xl font-bold text-slate-800">Criar nova senha</h2>
                        <p className="text-sm text-slate-500 mt-2">Escolha uma senha com pelo menos 6 caracteres.</p>
                    </div>

                    {message && <div className="p-3 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-700 text-sm font-medium">{message}</div>}
                    {error && <div className="p-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm font-medium">{error}</div>}

                    <div>
                        <label className="block text-sm font-bold text-slate-600 mb-2">Nova senha</label>
                        <div className="relative">
                            <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
                            <input
                                type="password"
                                required
                                minLength={6}
                                value={password}
                                onChange={(event) => setPassword(event.target.value)}
                                placeholder="••••••••"
                                className="w-full pl-10 pr-4 py-3 bg-slate-50 border border-slate-200 rounded-xl focus:ring-2 focus:ring-indigo-400 focus:outline-none font-medium text-slate-700"
                            />
                        </div>
                    </div>

                    <div>
                        <label className="block text-sm font-bold text-slate-600 mb-2">Confirmar nova senha</label>
                        <div className="relative">
                            <KeyRound className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
                            <input
                                type="password"
                                required
                                minLength={6}
                                value={confirmation}
                                onChange={(event) => setConfirmation(event.target.value)}
                                placeholder="••••••••"
                                className="w-full pl-10 pr-4 py-3 bg-slate-50 border border-slate-200 rounded-xl focus:ring-2 focus:ring-indigo-400 focus:outline-none font-medium text-slate-700"
                            />
                        </div>
                    </div>

                    <button
                        type="submit"
                        disabled={loading || !token}
                        className={`w-full flex items-center justify-center gap-2 py-3 rounded-xl font-bold transition-all shadow-md ${loading || !token ? 'bg-slate-300 text-slate-500 cursor-not-allowed' : 'bg-indigo-600 hover:bg-indigo-700 text-white shadow-indigo-200'}`}
                    >
                        {loading ? <Loader2 className="w-5 h-5 animate-spin" /> : <KeyRound className="w-5 h-5" />}
                        {loading ? 'Salvando...' : 'Redefinir senha'}
                    </button>

                    <Link to="/login" className="flex items-center justify-center gap-2 text-sm text-indigo-600 font-bold hover:underline">
                        <ArrowLeft className="w-4 h-4" /> Voltar para o login
                    </Link>
                </form>
            </div>
        </div>
    );
}
