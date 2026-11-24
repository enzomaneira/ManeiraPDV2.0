import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Store, User, Loader2, AlertCircle, ArrowRight } from 'lucide-react';
import GoogleButton from './GoogleButton';
import { useAuth } from '../context/AuthContext';

const inputClass = 'w-full pl-10 pr-4 py-3 bg-slate-50 border border-slate-200 rounded-xl focus:ring-2 focus:ring-indigo-400 focus:outline-none font-medium text-slate-700';

// "ou Entrar com Google" nas telas de login e cadastro. Conta Google sem conta
// no PDV: pede o nome do restaurante e cria a conta. onStepChange(true) avisa
// a página para esconder o formulário de e-mail e senha nesse passo.
export default function GoogleAuthSection({ text = 'signin_with', onStepChange }) {
  const { loginWithGoogle, registerWithGoogle } = useAuth();
  const navigate = useNavigate();
  const [available, setAvailable] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [signup, setSignup] = useState(null); // { signupToken, name, email }
  const [name, setName] = useState('');
  const [storeName, setStoreName] = useState('');

  const handleCredential = async (credential) => {
    setError(null);
    setBusy(true);
    try {
      const result = await loginWithGoogle(credential);
      if (result.needsSignup) {
        setSignup(result);
        setName(result.name || '');
        onStepChange?.(true);
      } else {
        navigate('/', { replace: true });
      }
    } catch (err) {
      setError(err.response?.data?.error || 'Não foi possível entrar com o Google.');
    } finally {
      setBusy(false);
    }
  };

  const finishSignup = async (e) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await registerWithGoogle(signup.signupToken, storeName.trim(), name.trim());
      navigate('/', { replace: true });
    } catch (err) {
      setError(err.response?.data?.error || 'Não foi possível criar sua conta.');
    } finally {
      setBusy(false);
    }
  };

  const cancel = () => { setSignup(null); setError(null); onStepChange?.(false); };

  if (signup) {
    return (
      <form onSubmit={finishSignup} className="space-y-5">
        <div>
          <h2 className="text-xl font-bold text-slate-800">Falta só o seu restaurante</h2>
          <p className="text-sm text-slate-500 mt-1">Você entrou com o Google como <b>{signup.email}</b>. Essa ainda não é uma conta do PDV.</p>
        </div>
        {error && (
          <div className="p-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm font-medium flex items-center gap-2">
            <AlertCircle className="w-4 h-4 shrink-0" />{error}
          </div>
        )}
        <div>
          <label className="block text-sm font-bold text-slate-600 mb-2" htmlFor="google-name">Seu nome</label>
          <div className="relative">
            <User className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
            <input id="google-name" required maxLength={120} value={name} onChange={e => setName(e.target.value)} className={inputClass} />
          </div>
        </div>
        <div>
          <label className="block text-sm font-bold text-slate-600 mb-2" htmlFor="google-store">Nome do restaurante</label>
          <div className="relative">
            <Store className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
            <input id="google-store" required maxLength={150} value={storeName} onChange={e => setStoreName(e.target.value)} placeholder="Ex.: Burguer do Bairro" className={inputClass} autoFocus />
          </div>
        </div>
        <button type="submit" disabled={busy}
          className={`w-full flex items-center justify-center gap-2 py-3 rounded-xl font-bold transition-all shadow-md ${busy ? 'bg-slate-300 text-slate-500 cursor-not-allowed' : 'bg-indigo-600 hover:bg-indigo-700 text-white shadow-indigo-200'}`}>
          {busy ? <Loader2 className="w-5 h-5 animate-spin" /> : <ArrowRight className="w-5 h-5" />}{busy ? 'Criando conta...' : 'Criar conta e entrar'}
        </button>
        <button type="button" onClick={cancel} className="w-full text-sm font-bold text-slate-500 hover:text-slate-700">Voltar</button>
      </form>
    );
  }

  if (!available) return null;
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3 text-xs font-bold uppercase tracking-wider text-slate-400">
        <span className="h-px flex-1 bg-slate-200" />ou<span className="h-px flex-1 bg-slate-200" />
      </div>
      <GoogleButton onCredential={handleCredential} text={text} onUnavailable={() => setAvailable(false)} />
      {busy && <p className="flex items-center justify-center gap-2 text-sm text-slate-500"><Loader2 className="w-4 h-4 animate-spin" />Conferindo com o Google...</p>}
      {error && (
        <div className="p-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm font-medium flex items-center gap-2">
          <AlertCircle className="w-4 h-4 shrink-0" />{error}
        </div>
      )}
    </div>
  );
}
