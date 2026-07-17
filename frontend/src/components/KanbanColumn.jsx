export default function KanbanColumn({ title, count, colorTheme, icon, children }) {
    const themes = {
      blue: { border: "border-blue-500", bgIcon: "bg-blue-100 text-blue-600" },
      orange: { border: "border-orange-500", bgIcon: "bg-orange-100 text-orange-600" },
      green: { border: "border-green-500", bgIcon: "bg-green-100 text-green-600" },
      purple: { border: "border-purple-500", bgIcon: "bg-purple-100 text-purple-600" },
    };
    const theme = themes[colorTheme] || themes.orange;
  
    return (
      <div className="w-96 flex flex-col h-full bg-white rounded-2xl shadow-sm border border-slate-100 overflow-hidden">
        <div className={`p-4 border-b-2 ${theme.border} bg-slate-50/50 flex justify-between items-center`}>
          <div className="flex items-center gap-3 font-bold text-slate-700">
              <div className={`p-2 rounded-lg ${theme.bgIcon}`}>{icon}</div>
              {title}
          </div>
          <span className="bg-white border border-slate-200 text-slate-600 text-sm font-bold px-3 py-1 rounded-full">{count}</span>
        </div>
        <div className="flex-1 overflow-y-auto p-3 space-y-3 bg-slate-50/30 custom-scrollbar">
          {children}
        </div>
      </div>
    );
}