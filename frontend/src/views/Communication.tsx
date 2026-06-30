import React, { useState } from 'react';

interface CommunicationViewProps {
  privacyMode: boolean;
}

const CommunicationView: React.FC<CommunicationViewProps> = ({ privacyMode }) => {
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
          <div className="p-4 border-b border-slate-100 hover:bg-white cursor-pointer transition-colors">
            <div className="flex justify-between items-start mb-1">
              <span className="font-medium text-sm text-slate-900">제일여객</span>
              <span className="text-xs text-slate-400">1 시간 전</span>
            </div>
            <p className="text-xs text-slate-600 truncate mb-2">단말기 교체 방법 안내 바랍니다.</p>
            <span className="text-[10px] font-bold bg-slate-200 text-slate-600 px-1.5 py-0.5 rounded">AI 응대 중</span>
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
          <div className="flex justify-center mb-6">
            <span className="text-xs text-slate-400 bg-slate-200 px-2 py-1 rounded-full">2026 년 6 월 30 일</span>
          </div>
          
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
          <div className="border-t border-slate-200 pt-4">
            <h4 className="text-xs font-bold text-slate-500 mb-2">모빌리티 자산 현황</h4>
            <div className="bg-white p-2 border border-slate-200 rounded text-sm">
              <div className="flex justify-between mb-1"><span className="text-slate-600">내연기관</span><span className="font-medium text-slate-900">100 대</span></div>
              <div className="flex justify-between"><span className="text-slate-600">전기차</span><span className="font-medium text-slate-900">20 대</span></div>
            </div>
          </div>
          <div className="border-t border-slate-200 pt-4">
            <h4 className="text-xs font-bold text-slate-500 mb-2">최근 활동 이력</h4>
            <ul className="text-xs space-y-2 text-slate-600">
              <li className="flex gap-2"><span className="bg-slate-200 px-1 rounded">미팅</span><span className="truncate">단말기 점검 및 수리</span></li>
              <li className="flex gap-2"><span className="bg-slate-200 px-1 rounded">메일</span><span className="truncate">정산 리포트 발송</span></li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
};

export default CommunicationView;
