import { useState } from 'react';
import { User, Lock, Save, RefreshCw, CheckCircle, AlertCircle } from 'lucide-react';
import { authService, storeService, TOKEN_KEY } from '../services/api';
import { useAuth } from '../context/AuthContext';

const inputClass = 'w-full px-4 py-3 bg-slate-50 border border-slate-200 rounded-xl focus:ring-2 focus:ring-indigo-400 focus:outline-none font-medium text-slate-700';
const labelClass = 'block text-sm font-bold text-slate-600 mb-2';

function Feedback({ message }) {
    if (!message) return null;
    const success = message.type === 'success';
    return (
        <div className={`p-3 rounded-xl flex items-center gap-2 text-sm font-bold ${success ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}`}>
            {success ? <CheckCircle className="w-4 h-4 shrink-0" /> : <AlertCircle className="w-4 h-4 shrink-0" />}
            {message.text}
        </div>
    );
}

// Cards de "Conta e restaurante" e "Alterar senha" da página de Configurações.
export default function AccountSettings() {
    const { user, setUser } = useAuth();

    const [name, setName] = useState(user?.name || '');
    const [email, setEmail] = useState(user?.email || '');
    const [storeName, setStoreName] = useState(user?.storeName || '');
    const [emailPassword, setEmailPassword] = useState('');
    const [savingProfile, setSavingProfile] = useState(false);
    const [profileMessage, setProfileMessage] = useState(null);

    const [currentPassword, setCurrentPassword] = useState('');
    const [newPassword, setNewPassword] = useState('');
    const [confirmPassword, setConfirmPassword] = useState('');
    const [savingPassword, setSavingPassword] = useState(false);
    const [passwordMessage, setPasswordMessage] = useState(null);

    const emailChanged = email.trim().toLowerCase() !== (user?.email || '');

    const handleSaveProfile = async (e) => {
        e.preventDefault();
        setSavingProfile(true);
        setProfileMessage(null);
        try {
            const payload = { name };
            if (emailChanged) {
                payload.email = email;
                payload.currentPassword = emailPassword;
            }
            const userResponse = await authService.updateMe(payload);
            let updatedUser = userResponse.data;

            if (storeName.trim() !== (user?.storeName || '')) {
                const storeResponse = await storeService.rename(storeName);
                updatedUser = { ...updatedUser, storeName: storeResponse.data.name };
            }

            setUser(updatedUser);
            setEmailPassword('');
            setProfileMessage({ type: 'success', text: 'Dados atualizados com sucesso!' });
        } catch (error) {
            setProfileMessage({ type: 'error', text: error?.response?.data?.error || 'Não foi possível salvar os dados.' });
        } finally {
            setSavingProfile(false);
        }
    };

    const handleChangePassword = async (e) => {
        e.preventDefault();
        setPasswordMessage(null);
        if (newPassword !== confirmPassword) {
            setPasswordMessage({ type: 'error', text: 'As senhas não coincidem.' });
            return;
        }
        setSavingPassword(true);
        try {
            const response = await authService.changePassword(currentPassword, newPassword);
            // A troca de senha encerra as sessões antigas; guardamos o token novo.
            localStorage.setItem(TOKEN_KEY, response.data.token);
            setUser(response.data.user);
            setCurrentPassword('');
            setNewPassword('');
            setConfirmPassword('');
            setPasswordMessage({ type: 'success', text: 'Senha alterada. Outros dispositivos precisarão entrar de novo.' });
        } catch (error) {
            setPasswordMessage({ type: 'error', text: error?.response?.data?.error || 'Não foi possível alterar a senha.' });
        } finally {
            setSavingPassword(false);
        }
    };

    const buttonClass = (busy) => `w-full py-3 font-bold rounded-xl transition-all flex items-center justify-center gap-2 shadow-sm ${busy ? 'bg-slate-300 text-slate-500 cursor-not-allowed' : 'bg-indigo-600 hover:bg-indigo-700 text-white'}`;

    return (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <form onSubmit={handleSaveProfile} className="bg-white p-6 rounded-2xl shadow-sm border border-slate-200 space-y-4">
                <div className="flex items-center gap-3 border-b border-slate-100 pb-4">
                    <div className="p-2 bg-indigo-100 text-indigo-700 rounded-lg">
                        <User className="w-6 h-6" />
                    </div>
                    <div>
                        <h3 className="font-bold text-lg text-slate-800">Conta e restaurante</h3>
                        <p className="text-xs text-slate-400">Seus dados de acesso e o nome da loja</p>
                    </div>
                </div>

                <Feedback message={profileMessage} />

                <div>
                    <label className={labelClass}>Seu nome</label>
                    <input type="text" required maxLength={120} value={name} onChange={(e) => setName(e.target.value)} className={inputClass} />
                </div>
                <div>
                    <label className={labelClass}>Nome do restaurante</label>
                    <input type="text" required maxLength={150} value={storeName} onChange={(e) => setStoreName(e.target.value)} className={inputClass} />
                </div>
                <div>
                    <label className={labelClass}>E-mail</label>
                    <input type="email" required maxLength={254} value={email} onChange={(e) => setEmail(e.target.value)} className={inputClass} />
                </div>
                {emailChanged && (
                    <div>
                        <label className={labelClass}>Senha atual (para trocar o e-mail)</label>
                        <input type="password" required value={emailPassword} onChange={(e) => setEmailPassword(e.target.value)} className={inputClass} />
                    </div>
                )}

                <button type="submit" disabled={savingProfile} className={buttonClass(savingProfile)}>
                    {savingProfile ? <RefreshCw className="w-5 h-5 animate-spin" /> : <Save className="w-5 h-5" />}
                    {savingProfile ? 'Salvando...' : 'Salvar dados'}
                </button>
            </form>

            <form onSubmit={handleChangePassword} className="bg-white p-6 rounded-2xl shadow-sm border border-slate-200 space-y-4 h-fit">
                <div className="flex items-center gap-3 border-b border-slate-100 pb-4">
                    <div className="p-2 bg-slate-100 text-slate-700 rounded-lg">
                        <Lock className="w-6 h-6" />
                    </div>
                    <div>
                        <h3 className="font-bold text-lg text-slate-800">Alterar senha</h3>
                        <p className="text-xs text-slate-400">Encerra o acesso em outros dispositivos</p>
                    </div>
                </div>

                <Feedback message={passwordMessage} />

                <div>
                    <label className={labelClass}>Senha atual</label>
                    <input type="password" required value={currentPassword} onChange={(e) => setCurrentPassword(e.target.value)} className={inputClass} />
                </div>
                <div>
                    <label className={labelClass}>Nova senha</label>
                    <input type="password" required minLength={6} maxLength={128} value={newPassword} onChange={(e) => setNewPassword(e.target.value)} className={inputClass} />
                </div>
                <div>
                    <label className={labelClass}>Confirmar nova senha</label>
                    <input type="password" required minLength={6} maxLength={128} value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} className={inputClass} />
                </div>

                <button type="submit" disabled={savingPassword} className={buttonClass(savingPassword)}>
                    {savingPassword ? <RefreshCw className="w-5 h-5 animate-spin" /> : <Lock className="w-5 h-5" />}
                    {savingPassword ? 'Alterando...' : 'Alterar senha'}
                </button>
            </form>
        </div>
    );
}
