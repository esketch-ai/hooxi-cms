import { useState } from 'react';

function App() {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [sidebarVisible, setSidebarVisible] = useState(true);
  const [privacyMode, setPrivacyMode] = useState(true);

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
          {['dashboard', 'clients', 'comm', 'assets'].map((tabId) => (
            <a
              key={tabId}
              href="#"
              data-target={tabId}
              onClick={(e) => { e.preventDefault(); setActiveTab(tabId); }}
              className={`flex items-center px-3 py-2.5 rounded-lg group transition-colors ${
                activeTab === tabId 
                  ? 'bg-slate-100 text-slate-900' 
                  : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
              }`}
            >
              <i className={`ph ${tabId === 'dashboard' ? 'ph-squares-four' : tabId === 'clients' ? 'ph-buildings' : tabId === 'comm' ? 'ph-chats-circle' : 'ph-folder'} text-xl mr-3`}></i>
              <span className="font-medium text-sm">{tabId === 'dashboard' ? '대시보드' : tabId === 'clients' ? '고객사 마스터' : tabId === 'comm' ? '커뮤니케이션' : '문서 자산'}</span>
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
          {activeTab === 'dashboard' && <Dashboard privacyMode={privacyMode} />}
          {activeTab === 'clients' && <Clients privacyMode={privacyMode} />}
          {activeTab === 'comm' && <Communication privacyMode={privacyMode} />}
          {activeTab === 'assets' && <Assets privacyMode={privacyMode} />}
          {activeTab === 'settings' && <Settings privacyMode={privacyMode} />}
        </div>
      </main>
    </div>
  );
}

// Dashboard View Component (Inline)
function Dashboard({ privacyMode }: { privacyMode: boolean }) {
  return (
    <div className="h-full overflow-y-auto p-4 sm:p-6 lg:p-8">
      <div className="mb-6 flex justify-between items-end">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">대시보드</h1>
          <p className="text-sm text-slate-500 mt-1">팀 전체 업무 현황입니다.</p>
        </div>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-6">
        <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
          <div className="flex justify-between items-start mb-4">
            <div className="p-2 bg-slate-50 rounded-lg">
              <i className="ph ph-car-profile text-xl text-slate-700"></i>
            </div>
            <span className="text-xs font-semibold px-2 py-1 bg-green-100 text-green-700 rounded-full">+12 대 (전일대비)</span>
          </div>
          <h3 className="text-slate-500 text-sm font-medium">통합 자산 현황</h3>
          <div className="mt-2 flex items-baseline space-x-2">
            <span className="text-2xl font-bold text-slate-900">1,600</span>
            <span className="text-sm text-slate-500">대 (차량)</span>
          </div>
        </div>

        <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
          <div className="flex justify-between items-start mb-4">
            <div className="p-2 bg-slate-50 rounded-lg">
              <i className="ph ph-coins text-xl text-slate-700"></i>
            </div>
          </div>
          <h3 className="text-slate-500 text-sm font-medium">당월 예상 정산액 (성공보수 {privacyMode ? '***%' : '15%'})</h3>
          <div className="mt-2 flex items-baseline space-x-2">
            <span className={`text-2xl font-bold ${privacyMode ? '' : 'text-slate-900'}`}>
              {privacyMode ? '₩ ***,***,***' : '₩ 214,000,000'}
            </span>
          </div>
        </div>

        <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
          <div className="flex justify-between items-start mb-4">
            <div className="p-2 bg-slate-50 rounded-lg">
              <i className="ph ph-database text-xl text-slate-700"></i>
            </div>
          </div>
          <h3 className="text-slate-500 text-sm font-medium">시스템 및 백업 상태</h3>
          <div className="mt-3 space-y-3">
            <div className="flex justify-between items-center text-sm">
              <span className="text-slate-600 flex items-center"><i className="ph-fill ph-check-circle text-green-500 mr-2"></i> 정오 백업 (12:00)</span>
              <span className="font-medium text-slate-900">완료</span>
            </div>
          </div>
        </div>
      </div>

      {/* Timeline & Issues */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm flex flex-col h-96">
          <div className="px-5 py-4 border-b border-slate-200 flex justify-between items-center">
            <h3 className="font-semibold text-slate-900">투데이 업무 타임라인</h3>
            <button className="text-xs font-medium text-slate-600 hover:text-slate-900 bg-slate-100 px-2 py-1 rounded">일정 추가</button>
          </div>
          <div className="p-5 overflow-y-auto flex-1">
            <div className="relative border-l border-slate-200 ml-3 space-y-6 pb-4">
              <div className="relative pl-6">
                <span className="absolute -left-1.5 top-1 w-3 h-3 rounded-full bg-slate-300 border-2 border-white"></span>
                <div className="text-xs text-slate-500 mb-1">10:00 AM · 완료</div>
                <div className="bg-slate-50 p-3 rounded-lg border border-slate-200">
                  <h4 className="text-sm font-medium text-slate-900">서울운수 (FMS 단말기 설치)</h4>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div className="bg-white rounded-xl border border-slate-200 shadow-sm flex flex-col h-96">
          <div className="px-5 py-4 border-b border-slate-200 flex justify-between items-center">
            <h3 className="font-semibold text-slate-900">오픈 이슈 보드</h3>
            <a href="#" className="text-xs font-medium text-slate-500 hover:text-slate-900">전체 보기</a>
          </div>
          <div className="p-0 overflow-y-auto flex-1">
            <table className="w-full text-sm text-left">
              <thead className="text-xs text-slate-500 bg-slate-50 border-b border-slate-200 sticky top-0">
                <tr>
                  <th className="px-5 py-3 font-medium">상태</th>
                  <th className="px-5 py-3 font-medium">내용</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200">
                <tr className="hover:bg-slate-50 cursor-pointer">
                  <td className="px-5 py-4"><span className="bg-red-100 text-red-700 px-2 py-1 rounded text-xs font-semibold">긴급</span></td>
                  <td className="px-5 py-4">대한로지스 정산 이의 제기</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}

// Clients View Component (Inline)
function Clients({ privacyMode }: { privacyMode: boolean }) {
  const clients = [
    { status: '진행중', type: '운수사', name: '대한로지스 (주)', assets: '총 120 대 (내연:100 / 전기:20)', pm: '송승헌', lastContact: '2026-06-29' },
    { status: '진행중', type: '건물', name: '스마트에코타워', assets: '히트펌프 2 대, 태양광 50kW', pm: '박지훈', lastContact: '2026-06-28' },
    { status: '보류', type: '운수사', name: '제일여객', assets: '총 45 대 (내연:45 / 전기:0)', pm: '김서연', lastContact: '2026-05-12' },
  ];

  return (
    <div className="h-full overflow-y-auto p-4 sm:p-6 lg:p-8">
      <div className="mb-6 flex justify-between items-end">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">고객사 마스터</h1>
          <p className="text-sm text-slate-500 mt-1">자산 제원 및 계약 정보를 관리합니다.</p>
        </div>
        <button className="bg-slate-900 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-slate-800 transition-colors">고객사 등록</button>
      </div>

      <div className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden flex flex-col">
        <div className="border-b border-slate-200 px-4 py-3 flex space-x-4 bg-slate-50">
          <button className="text-sm font-semibold text-slate-900 border-b-2 border-slate-900 pb-2">전체 고객사</button>
          <button className="text-sm font-medium text-slate-500 hover:text-slate-900 pb-2">모빌리티 (운수사)</button>
          <button className="text-sm font-medium text-slate-500 hover:text-slate-900 pb-2">고정원 (건물/농장)</button>
        </div>
        
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left whitespace-nowrap">
            <thead className="text-xs text-slate-500 bg-white border-b border-slate-200">
              <tr>
                <th className="px-6 py-4 font-medium">상태</th>
                <th className="px-6 py-4 font-medium">유형</th>
                <th className="px-6 py-4 font-medium">상호명</th>
                <th className="px-6 py-4 font-medium">핵심 자산 규모</th>
                <th className="px-6 py-4 font-medium">담당 PM</th>
                <th className="px-6 py-4 font-medium">최근 컨택일</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {clients.map((client, index) => (
                <tr key={index} className="hover:bg-slate-50 cursor-pointer">
                  <td className="px-6 py-4"><span className={`bg-${client.status === '진행중' ? 'green' : 'slate'}-100 text-${client.status === '진행중' ? 'green' : 'slate'}-700 px-2 py-1 rounded text-xs font-semibold`}>{client.status}</span></td>
                  <td className="px-6 py-4 text-slate-600">{client.type}</td>
                  <td className="px-6 py-4 font-medium text-slate-900">{client.name}</td>
                  <td className="px-6 py-4 text-slate-600">{client.assets}</td>
                  <td className="px-6 py-4 text-slate-600">{client.pm}</td>
                  <td className="px-6 py-4 text-slate-500 text-xs">{client.lastContact}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

// Communication View Component (Inline)
function Communication({ privacyMode }: { privacyMode: boolean }) {
  const [messages, setMessages] = useState([
    { id: 1, type: 'user', text: '이번 달 탄소 배출권 정산 금액이 예상보다 적게 나왔습니다. 확인 부탁드립니다.', time: '오후 2:10' },
    { id: 2, type: 'ai', text: '대한로지스 담당자님, 확인 결과 이달 중순 차량 5 대의 운행 기록 누락이 발생하여 베이스라인에서 제외되었습니다.', time: '오후 2:10' },
    { id: 3, type: 'user', text: '단말기 오류였습니다. 서류 제출할 테니 담당자 연결해 주세요. 정산 내역이 이상합니다.', time: '오후 2:15' },
  ]);

  return (
    <div className="h-full flex overflow-hidden bg-white">
      {/* Chat List */}
      <div className="w-80 border-r border-slate-200 flex flex-col bg-slate-50 flex-shrink-0">
        <div className="p-4 border-b border-slate-200 bg-white">
          <h2 className="font-bold text-slate-900">상담 채널</h2>
          <div className="mt-3 flex gap-2">
            <span className="text-xs bg-slate-200 px-2 py-1 rounded text-slate-700 cursor-pointer">전체</span>
            <span className="text-xs border border-red-200 bg-red-50 px-2 py-1 rounded text-red-700 font-medium cursor-pointer">직원 이관 대기 1</span>
          </div>
        </div>
        <div className="flex-1 overflow-y-auto">
          <div className="p-4 border-b border-slate-100 bg-white cursor-pointer border-l-4 border-red-500">
            <div className="flex justify-between items-start mb-1">
              <span className="font-medium text-sm text-slate-900">대한로지스 (주)</span>
              <span className="text-xs text-slate-400">방금</span>
            </div>
            <p className="text-xs text-slate-600 truncate mb-2">담당자 연결해 주세요. 정산 내역이 이상합니다.</p>
            <span className="text-[10px] font-bold bg-red-100 text-red-600 px-1.5 py-0.5 rounded">직원 이관 요청</span>
          </div>
        </div>
      </div>

      {/* Chat Window */}
      <div className="flex-1 flex flex-col bg-white">
        <div className="p-4 border-b border-slate-200 flex justify-between items-center bg-white shadow-sm z-10">
          <div>
            <h2 className="font-bold text-slate-900">대한로지스 (주)</h2>
            <p className="text-xs text-slate-500">최근 계약 갱신일: 2026-01-15</p>
          </div>
          <button className="bg-slate-100 text-slate-600 px-3 py-1.5 rounded text-sm font-medium hover:bg-slate-200">상담 종료 (AI 복귀)</button>
        </div>
        
        <div className="flex-1 overflow-y-auto p-6 space-y-4 bg-slate-50">
          {messages.map((msg) => (
            <div key={msg.id} className={`flex ${msg.type === 'user' ? 'justify-start' : 'justify-end'}`}>
              <div className={`${msg.type === 'user' ? 'bg-white' : 'bg-slate-100'} border border-slate-200 rounded-lg ${msg.type === 'user' ? 'rounded-tl-none' : 'rounded-tr-none'} p-3 max-w-md shadow-sm`}>
                {msg.type === 'ai' && (
                  <div className="flex items-center mb-1">
                    <i className="ph-fill ph-robot text-slate-500 mr-1"></i> 
                    <span className="text-xs font-bold text-slate-500">AI 어시스턴트</span>
                  </div>
                )}
                <p className={`text-sm ${msg.type === 'user' ? 'text-slate-800' : 'text-slate-700'}`}>{msg.text}</p>
                <span className="text-[10px] text-slate-400 mt-1 block">{msg.time}</span>
              </div>
            </div>
          ))}

          {privacyMode && (
            <div className="flex justify-center my-4">
              <span className="text-xs font-medium text-red-500 bg-red-50 px-3 py-1 rounded-full border border-red-100">직원 이관이 요청되었습니다. 텍스트 입력 시 담당자 모드로 전환됩니다.</span>
            </div>
          )}
        </div>

        <div className="p-4 border-t border-slate-200 bg-white">
          <div className="flex items-center border border-slate-300 rounded-lg overflow-hidden focus-within:ring-2 focus-within:ring-slate-400 focus-within:border-transparent">
            <button className="p-3 text-slate-400 hover:text-slate-600 bg-slate-50"><i className="ph ph-paperclip text-xl"></i></button>
            <input type="text" placeholder="메시지를 입력하여 담당자 응대 모드로 즉시 전환..." className="flex-1 py-3 px-2 text-sm focus:outline-none" />
            <button className="p-3 bg-slate-900 text-white hover:bg-slate-800 font-medium text-sm px-6">전송</button>
          </div>
        </div>
      </div>

      {/* Context Panel */}
      <div className="w-72 border-l border-slate-200 bg-slate-50 hidden lg:block overflow-y-auto">
        <div className="p-4 border-b border-slate-200 bg-white">
          <h3 className="font-bold text-slate-900">고객 정보 요약</h3>
        </div>
        <div className="p-4 space-y-5">
          <div>
            <h4 className="text-xs font-bold text-slate-500 mb-2">기본 정보</h4>
            <p className="text-sm text-slate-900 font-medium">대한로지스 (주)</p>
            <p className="text-xs text-slate-600 mt-1">담당 PM: 송승헌</p>
            <p className="text-xs text-slate-600">성공 보수율: {privacyMode ? '***%' : '15%'}</p>
          </div>
        </div>
      </div>
    </div>
  );
}

// Assets View Component (Inline)
function Assets({ privacyMode }: { privacyMode: boolean }) {
  const files = [
    { name: '대한로지스_계약서_v2.pdf', size: '2.4 MB', date: '2026-01-15', type: 'pdf' },
    { name: '현장실사_인버터사진.jpg', size: '4.1 MB', date: '2026-06-20', type: 'image' },
  ];

  return (
    <div className="h-full flex overflow-hidden bg-white">
      {/* Folder Tree */}
      <div className="w-64 border-r border-slate-200 bg-slate-50 flex flex-col">
        <div className="p-4 border-b border-slate-200">
          <h2 className="font-bold text-slate-900 text-sm">폴더 트리</h2>
        </div>
        <div className="p-2 flex-1 overflow-y-auto">
          <ul className="text-sm text-slate-700 space-y-1">
            <li>
              <div className="flex items-center p-2 hover:bg-slate-200 rounded cursor-pointer font-medium">
                <i className="ph-fill ph-folder text-slate-400 mr-2 text-lg"></i> 표준 양식 및 가이드
              </div>
            </li>
            <li>
              <div className="flex items-center p-2 hover:bg-slate-200 rounded cursor-pointer font-medium bg-slate-200 text-slate-900">
                <i className="ph-fill ph-folder-open text-slate-600 mr-2 text-lg"></i> 고객사별 아카이브
              </div>
              <ul className="ml-6 mt-1 space-y-1 border-l border-slate-300 pl-2">
                <li className="p-1.5 hover:text-slate-900 cursor-pointer flex items-center"><i className="ph ph-folder text-slate-400 mr-2"></i> 대한로지스</li>
                <li className="p-1.5 hover:text-slate-900 cursor-pointer flex items-center"><i className="ph ph-folder text-slate-400 mr-2"></i> 스마트에코타워</li>
              </ul>
            </li>
          </ul>
        </div>
      </div>

      {/* File List */}
      <div className="flex-1 flex flex-col">
        <div className="p-4 border-b border-slate-200 flex justify-between items-center bg-white">
          <div className="flex items-center text-sm text-slate-500">
            <span className="hover:text-slate-900 cursor-pointer">루트</span>
            <i className="ph ph-caret-right mx-2 text-xs"></i>
            <span className="hover:text-slate-900 cursor-pointer">고객사별 아카이브</span>
          </div>
          <button className="bg-slate-100 text-slate-800 px-3 py-1.5 rounded-lg text-sm font-medium hover:bg-slate-200 flex items-center">
            <i className="ph ph-upload-simple mr-2"></i> 업로드
          </button>
        </div>

        <div className="flex-1 p-6 overflow-y-auto bg-white">
          <table className="w-full text-sm text-left">
            <thead className="text-xs text-slate-500 border-b border-slate-200">
              <tr>
                <th className="pb-3 font-medium">파일명</th>
                <th className="pb-3 font-medium">크기</th>
                <th className="pb-3 font-medium">업로드 일시</th>
                <th className="pb-3 font-medium text-right">관리</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {files.map((file, index) => (
                <tr key={index} className="hover:bg-slate-50 group">
                  <td className="py-3 flex items-center font-medium text-slate-800">
                    <i className={`ph-fill ph-file-${file.type === 'pdf' ? 'pdf' : file.type === 'image' ? 'image' : 'text'} text-${file.type === 'pdf' ? 'red' : file.type === 'image' ? 'blue' : 'slate'}-500 text-lg mr-3`}></i>
                    {file.name}
                  </td>
                  <td className="py-3 text-slate-500">{file.size}</td>
                  <td className="py-3 text-slate-500">{file.date}</td>
                  <td className="py-3 text-right">
                    <button className="text-slate-400 hover:text-slate-800 mr-2"><i className="ph ph-download-simple text-lg"></i></button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

// Settings View Component (Inline)
function Settings({ privacyMode }: { privacyMode: boolean }) {
  return (
    <div className="h-full overflow-y-auto p-4 sm:p-6 lg:p-8">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-900">환경 설정</h1>
        <p className="text-sm text-slate-500 mt-1">시스템 계정 및 인프라 백업 상태를 관리합니다.</p>
      </div>
      
      <div className="max-w-4xl space-y-6">
        {/* Account Info */}
        <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-sm">
          <h2 className="text-lg font-bold text-slate-900 mb-4 border-b border-slate-100 pb-2">나의 계정 정보</h2>
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <span className="block text-xs text-slate-500 mb-1">이름</span>
              <span className="font-medium text-slate-900">송승헌</span>
            </div>
            <div>
              <span className="block text-xs text-slate-500 mb-1">직무 권한</span>
              <span className="font-medium text-slate-900">실무 담당 PM (전체 조회 및 수정)</span>
            </div>
            <div>
              <span className="block text-xs text-slate-500 mb-1">이메일</span>
              <span className="font-medium text-slate-900">{privacyMode ? '***@carbonfleet.com' : 'song@carbonfleet.com'}</span>
            </div>
          </div>
        </div>

        {/* Backup Status */}
        <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-sm">
          <h2 className="text-lg font-bold text-slate-900 mb-4 border-b border-slate-100 pb-2">데이터 백업 상태 모니터링</h2>
          <div className="space-y-4 text-sm">
            <div className="flex justify-between items-center p-3 bg-slate-50 rounded border border-slate-100">
              <div>
                <p className="font-medium text-slate-900">최근 백업 내역 (자동 스냅샷)</p>
                <p className="text-xs text-slate-500">2026-06-30 12:00:05 완료</p>
              </div>
              <span className="bg-green-100 text-green-700 px-3 py-1 rounded-full text-xs font-bold">정상</span>
            </div>
          </div>
        </div>

        {/* API Configuration */}
        <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-sm">
          <h2 className="text-lg font-bold text-slate-900 mb-4 border-b border-slate-100 pb-2">API 설정</h2>
          <div className="space-y-4">
            <div>
              <span className="block text-xs text-slate-500 mb-1">Backend API URL</span>
              <input type="text" value={privacyMode ? 'http://***:8000' : 'http://localhost:8000/api'} readOnly className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded text-sm" />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default App;
