import { ChefHat, ShoppingBag, History, Utensils, Settings, LogOut } from 'lucide-react';

export default function Sidebar({ activeTab, setActiveTab, user, onLogout }) {
  const initials = user?.name
    ? user.name.split(' ').filter(Boolean).slice(0, 2).map(n => n[0].toUpperCase()).join('')
    : '?';

  return (
    <aside className="w-20 md:w-64 bg-slate-900 text-white flex flex-col justify-between shadow-2xl z-20 transition-all">
      <div>
        <div className="h-20 flex items-center justify-center border-b border-slate-700 bg-slate-800">
          <div className="w-10 h-10 bg-indigo-500 rounded-xl flex items-center justify-center shadow-lg shadow-indigo-500/50">
            <ChefHat className="text-white w-6 h-6" />
          </div>
          <h1 className="hidden md:block ml-3 text-xl font-bold tracking-tight">
            Maneira<span className="text-indigo-400">PDV</span>
          </h1>
        </div>

        <nav className="p-4 space-y-2">
          <SidebarItem icon={<ShoppingBag />} label="Pedidos" id="orders" activeTab={activeTab} onClick={setActiveTab} />
          <SidebarItem icon={<History />} label="Histórico" id="history" activeTab={activeTab} onClick={setActiveTab} />
          <SidebarItem icon={<Utensils />} label="Menu" id="menu" activeTab={activeTab} onClick={setActiveTab} />
          <SidebarItem icon={<Settings />} label="Configurações" id="settings" activeTab={activeTab} onClick={setActiveTab} />
        </nav>
      </div>

      <div className="p-4 border-t border-slate-700 bg-slate-800/50">
        <div className="flex items-center gap-3 px-2 py-2">
           <div className="w-10 h-10 rounded-full bg-indigo-600 flex items-center justify-center font-bold shrink-0">{initials}</div>
           <div className="hidden md:block flex-1 min-w-0">
             <p className="text-sm font-semibold truncate">{user?.name || 'Usuário'}</p>
             <p className="text-xs text-slate-400 truncate">{user?.storeName || 'Sem restaurante'}</p>
           </div>
           <button
             onClick={onLogout}
             title="Sair"
             className="hidden md:flex p-2 rounded-lg text-slate-400 hover:text-red-400 hover:bg-slate-700 transition-all"
           >
             <LogOut className="w-4 h-4" />
           </button>
        </div>
      </div>
    </aside>
  );
}

function SidebarItem({ icon, label, id, activeTab, onClick }) {
    const active = activeTab === id;
    return (
      <button onClick={() => onClick(id)} className={`w-full flex items-center justify-center md:justify-start gap-4 px-4 py-3 rounded-xl transition-all duration-200 group relative ${active ? 'text-white bg-indigo-600 shadow-lg shadow-indigo-900/50' : 'text-slate-400 hover:bg-slate-800 hover:text-white'}`}>
        {active && <div className="absolute left-0 w-1 h-8 bg-white rounded-r-full"></div>}
        <span className={active ? 'text-white' : 'text-slate-400 group-hover:text-white'}>{icon}</span>
        <span className="hidden md:block font-medium">{label}</span>
      </button>
    );
}