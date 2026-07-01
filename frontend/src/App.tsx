import { useState } from 'react';
import DashboardView from './views/Dashboard';
import ClientsView from './views/Clients';
import CommunicationView from './views/Communication';
import AssetsView from './views/Assets';
import SettingsView from './views/Settings';

function App() {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [sidebarVisible, setSidebarVisible] = useState(true);
  const [privacyMode, setPrivacyMode] = useState(true);

  const tabs = [
    { id: 'dashboard', label: '대시보드', icon: 'ph-squares-four' },
    { id: 'clients', label: '고객사 마스터', icon: 'ph-buildings' },
    { id: 'comm', label: '커뮤니케이션', icon: 'ph-chats-circle' },
    { id: 'assets', label: '문서 자산', icon: 'ph-folder' },
  ];

  return (
    <div className="h-screen flex bg-slate-50">
      {/* Sidebar */}
      <aside 
        className={`bg-white border-r border-slate-200 w-64 flex-shrink-0 transition-all duration-300 flex flex-col ${sidebarVisible ? '' : 'hidden md:hidden'}`}
      >
        <div className="h-16 flex items-center px-6 border-b border-slate-200">
          <i className="ph-fill ph-leaf text-2xl text-slate-800 mr-2"></i>
          <span className="text-lg font-bold tracking-tight">Carbon Fleet</span>
        </div>
        
        <nav className="flex-1 overflow-y-auto py-4 px-3 space-y-1">
          {tabs.map((tab) => (
            <a
              key={tab.id}
              href="#"
              data-target={tab.id}
              onClick={(e) => { e.preventDefault(); setActiveTab(tab.id); }}
              className={`flex items-center px-3 py-2.5 rounded-lg group transition-colors ${
                activeTab === tab.id 
                  ? 'bg-slate-100 text-slate-900' 
                  : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
              }`}
            >
              <i className={`ph ${tab.icon} text-xl mr-3`}></i>
              <span className="font-medium text-sm">{tab.label}</span>
            </a>
          ))}
        </nav>

        <div className="p-3 border-t border-slate-200">
          <a href="#" data-target="settings" onClick={(e) => { e.preventDefault(); setActiveTab('settings'); }} className="menu-item flex items-center px-3 py-2 text-slate-600 hover:bg-slate-50 hover:text-slate-900 rounded-lg transition-colors">
            <i className="ph ph-gear text-xl mr-3"></i>
            <span className="font-medium text-sm">환경 설정</span>
          </a>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 flex flex-col h-screen overflow-hidden relative">
        {/* Header */}
        <header className="h-16 bg-white border-b border-slate-200 flex items-center justify-between px-4 sm:px-6 z-10 flex-shrink-0">
          <div className="flex items-center flex-1">
            <button 
              id="mobile-menu-btn" 
              onClick={() => setSidebarVisible(!sidebarVisible)}
              className="md:hidden mr-4 text-slate-500 hover:text-slate-900"
            >
              <i className="ph ph-list text-2xl"></i>
            </button>
            <div className="relative w-full max-w-md hidden sm:block">
              <i className="ph ph-magnifying-glass absolute left-3 top-1/2 transform -translate-y-1/2 text-slate-400"></i>
              <input 
                type="text" 
                placeholder="고객사명, 연락처, 사업자번호 검색..." 
                className="w-full pl-10 pr-4 py-2 bg-slate-50 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-slate-300 focus:bg-white transition-all"
              />
            </div>
          </div>
          
          <div className="flex items-center space-x-4">
            {/* Privacy Mode Toggle */}
            <div className="flex items-center mr-2 border-r border-slate-200 pr-4 hidden sm:flex">
              <span className="text-xs font-medium text-slate-500 mr-2">보안 모드</span>
              <label className="relative inline-flex items-center cursor-pointer">
                <input 
                  type="checkbox" 
                  id="privacy-toggle" 
                  checked={privacyMode}
                  onChange={(e) => setPrivacyMode(e.target.checked)}
                  className="sr-only peer"
                />
                <div className={`w-9 h-5 rounded-full peer-checked:bg-slate-800 ${privacyMode ? 'after:translate-x-full' : ''}`}>
                  <span className="absolute top-[2px] left-[2px] w-4 h-4 bg-white rounded-full transition-all"></span>
                </div>
              </label>
            </div>

            {/* Notifications */}
            <button className="relative p-2 text-slate-500 hover:text-slate-900 transition-colors">
              <i className="ph ph-bell text-xl"></i>
              <span className="absolute top-1.5 right-1.5 w-2 h-2 bg-red-500 rounded-full border-2 border-white"></span>
            </button>

            {/* User Profile */}
            <div className="flex items-center space-x-2 pl-4 border-l border-slate-200 cursor-pointer">
              <div className="w-8 h-8 rounded-full bg-slate-200 flex items-center justify-center text-slate-600 font-bold text-sm">송</div>
              <span className="text-sm font-medium hidden sm:block">송승헌 PM</span>
            </div>
          </div>
        </header>

        {/* Dynamic Content */}
        <div className="flex-1 overflow-hidden relative bg-slate-50">
          {activeTab === 'dashboard' && <DashboardView privacyMode={privacyMode} />}
          {activeTab === 'clients' && <ClientsView privacyMode={privacyMode} />}
          {activeTab === 'comm' && <CommunicationView privacyMode={privacyMode} />}
          {activeTab === 'assets' && <AssetsView privacyMode={privacyMode} />}
          {activeTab === 'settings' && <SettingsView privacyMode={privacyMode} />}
        </div>
      </main>
    </div>
  );
}

export default App;
