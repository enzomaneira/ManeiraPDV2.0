import { useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, ChefHat, Loader2, Mail, Send } from 'lucide-react';
import { authService } from '../services/api';

export default function ForgotPasswordPage() {
    const [email, setEmail] = useState('');
    const [loading, setLoading] = useState(false);
    const [message, setMessage] = useState(null);
    const [error, setError] = useState(null);

    const handleSubmit = async (event) => {
        event.preventDefault();
        setLoading(true);
        setMessage(null);
        setError(null);

        try {
            const response = await authService.requestPasswordReset(email);
            setMessage(response.data.message);
        } catch (requestError) {
            setError(requestError.response?.data?.error || 'Não foi possível enviar o pedido. Tente novamente.');
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
                        <h2 className="text-xl font-bold text-slate-800">Recuperar senha</h2>
                        <p className="text-sm text-slate-500 mt-2">
                            Informe seu e-mail e enviaremos um link para criar uma nova senha.
                        </p>
                    </div>

                    {message && <div className="p-3 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-700 text-sm font-medium">{message}</div>}
                    {error && <div className="p-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm font-medium">{error}</div>}

                    <div>
                        <label className="block text-sm font-bold text-slate-600 mb-2">E-mail</label>
                        <div className="relative">
                            <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
                            <input
                                type="email"
                                required
                                value={email}
                                onChange={(event) => setEmail(event.target.value)}
                                placeholder="voce@exemplo.com"
                                className="w-full pl-10 pr-4 py-3 bg-slate-50 border border-slate-200 rounded-xl focus:ring-2 focus:ring-indigo-400 focus:outline-none font-medium text-slate-700"
                            />
                        </div>
                    </div>

                    <button
                        type="submit"
                        disabled={loading}
                        className={`w-full flex items-center justify-center gap-2 py-3 rounded-xl font-bold transition-all shadow-md ${loading ? 'bg-slate-300 text-slate-500 cursor-not-allowed' : 'bg-indigo-600 hover:bg-indigo-700 text-white shadow-indigo-200'}`}
                    >
                        {loading ? <Loader2 className="w-5 h-5 animate-spin" /> : <Send className="w-5 h-5" />}
                        {loading ? 'Enviando...' : 'Enviar link de recuperação'}
                    </button>

                    <Link to="/login" className="flex items-center justify-center gap-2 text-sm text-indigo-600 font-bold hover:underline">
                        <ArrowLeft className="w-4 h-4" /> Voltar para o login
                    </Link>
                </form>
            </div>
        </div>
    );
}
