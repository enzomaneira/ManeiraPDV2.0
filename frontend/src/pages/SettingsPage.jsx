import { useState } from 'react';
import api from '../services/api';
import { Save, Store, Globe, Wifi, RefreshCw, CheckCircle, AlertCircle, ExternalLink } from 'lucide-react';

export default function SettingsPage({ config, setConfig }) {
  
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState(null);

  const handleSave = async () => {
    setSaving(true);
    setMessage(null);
    try {
        await api.post('/config', {
            id: 1,
            autoAccept: config.autoAccept,
            keetaMerchantId: config.keetaId
        });
        
        setMessage({ type: 'success', text: 'Configurações salvas com sucesso!' });
        setTimeout(() => setMessage(null), 3000);
    } catch (error) {
        console.error("Erro ao salvar:", error);
        setMessage({ type: 'error', text: 'Erro ao salvar. Verifique o backend.' });
    } finally {
        setSaving(false);
    }
  };

  const handleConnectKeeta = async () => {
    try {
        console.log("Solicitando link de autenticação...");
        const response = await api.get('/keeta/generate-auth-url');
        console.log("Resposta do Backend:", response.data);

        let targetUrl = "";

        // CASO 1: Texto puro
        if (typeof response.data === 'string') {
            targetUrl = response.data;
        } 
        // CASO 2: JSON (Objeto) - Lê a propriedade correta da Keeta
        else if (typeof response.data === 'object') {
            targetUrl = response.data.merchantAuthorizationUrl || response.data.url;
        }

        // Validação e Abertura em Nova Aba
        if (targetUrl && targetUrl.includes('http')) {
            console.log("Abrindo em nova aba:", targetUrl);
            window.open(targetUrl, '_blank'); // <--- AQUI MUDOU PARA NOVA ABA
        } else {
            console.error("Formato não reconhecido:", response.data);
            alert("Erro: O backend retornou um formato inesperado. Verifique o console.");
        }
    } catch (error) {
        console.error("Erro de conexão:", error);
        alert("Não foi possível conectar ao servidor. Verifique se o Backend está rodando.");
    }
  };

  return (
    <div className="max-w-4xl mx-auto animate-in fade-in slide-in-from-bottom-4 space-y-6 pb-10">
      
      {/* Cabeçalho */}
      <div className="flex items-center justify-between">
        <div>
            <h2 className="text-2xl font-bold text-slate-800">Configurações da Loja</h2>
            <p className="text-slate-500">Gerencie sua integração e preferências do PDV.</p>
        </div>
        <button 
            onClick={handleSave} 
            disabled={saving}
            className={`flex items-center gap-2 px-6 py-2.5 rounded-xl font-bold transition-all shadow-md ${saving ? 'bg-slate-300 text-slate-500 cursor-not-allowed' : 'bg-indigo-600 hover:bg-indigo-700 text-white shadow-indigo-200'}`}
        >
            {saving ? <RefreshCw className="w-5 h-5 animate-spin"/> : <Save className="w-5 h-5" />} 
            {saving ? 'Salvando...' : 'Salvar Alterações'}
        </button>
      </div>

      {/* Mensagem de Feedback */}
      {message && (
          <div className={`p-4 rounded-xl flex items-center gap-2 font-bold ${message.type === 'success' ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}`}>
              {message.type === 'success' ? <CheckCircle className="w-5 h-5"/> : <AlertCircle className="w-5 h-5"/>}
              {message.text}
          </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          
          {/* Card 1: Integração Keeta */}
          <div className="bg-white p-6 rounded-2xl shadow-sm border border-slate-200 space-y-6">
              <div className="flex items-center gap-3 border-b border-slate-100 pb-4">
                  <div className="p-2 bg-yellow-100 text-yellow-700 rounded-lg">
                    <Globe className="w-6 h-6" />
                  </div>
                  <div>
                    <h3 className="font-bold text-lg text-slate-800">Integração Keeta</h3>
                    <p className="text-xs text-slate-400">Status da conexão com a plataforma</p>
                  </div>
                  <div className={`ml-auto px-3 py-1 rounded-full text-xs font-bold ${config.keetaStatus === 'CONNECTED' ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}`}>
                      {config.keetaStatus === 'CONNECTED' ? 'CONECTADO' : 'DESCONECTADO'}
                  </div>
              </div>

              <div className="space-y-4">
                  
                  {/* Campo de ID */}
                  <div>
                      <label className="block text-sm font-bold text-slate-600 mb-2">ID da Loja na Keeta</label>
                      <div className="relative">
                          <Store className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
                          <input 
                            type="text" 
                            value={config.keetaId || ''} 
                            onChange={(e) => setConfig({...config, keetaId: e.target.value})}
                            placeholder="Ex: 285076..."
                            className="w-full pl-10 pr-4 py-3 bg-slate-50 border border-slate-200 rounded-xl focus:ring-2 focus:ring-yellow-400 focus:outline-none font-medium text-slate-700"
                          />
                      </div>
                      <p className="text-[10px] text-slate-400 mt-1 ml-1">
                        O ID da sua loja dentro do portal do parceiro Keeta.
                      </p>
                  </div>

                  {/* Botão de Redirecionamento (Nova Aba) */}
                  <button 
                    onClick={handleConnectKeeta} 
                    className="w-full py-3 bg-yellow-400 hover:bg-yellow-500 text-yellow-900 font-bold rounded-xl transition-all flex items-center justify-center gap-2 shadow-sm shadow-yellow-100"
                  >
                      <Wifi className="w-5 h-5" /> 
                      Ativar Integração / Autenticar
                      <ExternalLink className="w-4 h-4 opacity-50 ml-1" />
                  </button>
                  
              </div>
          </div>

          {/* Card 2: Preferências */}
          <div className="bg-white p-6 rounded-2xl shadow-sm border border-slate-200 h-fit">
              <div className="flex items-center gap-3 border-b border-slate-100 pb-4">
                  <div className="p-2 bg-indigo-100 text-indigo-700 rounded-lg">
                    <Store className="w-6 h-6" />
                  </div>
                  <div>
                    <h3 className="font-bold text-lg text-slate-800">Preferências do PDV</h3>
                    <p className="text-xs text-slate-400">Comportamento do sistema</p>
                  </div>
              </div>

              <div className="pt-4">
                  {/* TOGGLE ACEITE AUTOMÁTICO */}
                  <div 
                    onClick={() => setConfig({...config, autoAccept: !config.autoAccept})}
                    className={`flex items-center justify-between p-4 rounded-xl border transition-all cursor-pointer ${config.autoAccept ? 'bg-green-50 border-green-200' : 'bg-slate-50 border-slate-200'}`}
                  >
                      <div>
                          <p className={`font-bold ${config.autoAccept ? 'text-green-800' : 'text-slate-700'}`}>
                              {config.autoAccept ? 'Aceite Automático ATIVADO' : 'Aceite Manual ATIVADO'}
                          </p>
                          <p className="text-xs text-slate-500 mt-1">
                              {config.autoAccept 
                                ? 'Pedidos novos vão direto para "Em Preparo"' 
                                : 'Pedidos novos aparecem em "Novo" para você aprovar'
                              }
                          </p>
                      </div>
                      
                      {/* Toggle Visual */}
                      <div className={`w-14 h-8 flex items-center rounded-full p-1 transition-colors duration-300 ${config.autoAccept ? 'bg-green-500' : 'bg-slate-300'}`}>
                          <div className={`bg-white w-6 h-6 rounded-full shadow-md transform transition-transform duration-300 ${config.autoAccept ? 'translate-x-6' : 'translate-x-0'}`}></div>
                      </div>
                  </div>
              </div>
          </div>
      </div>
    </div>
  );
}