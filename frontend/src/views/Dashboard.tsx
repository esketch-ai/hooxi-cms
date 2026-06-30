import React, { useState } from 'react';

interface DashboardProps {
  privacyMode: boolean;
}

const DashboardView: React.FC<DashboardProps> = ({ privacyMode }) => {
  const [currentTime] = useState(new Date());
  
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
          <div className="mt-3 text-xs text-slate-500 flex justify-between border-t border-slate-100 pt-3">
            <span>내연기관: 1,250 대</span>
            <span>전기차: 350 대</span>
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
          <div className="mt-3 text-xs text-slate-500 flex justify-between border-t border-slate-100 pt-3">
            <span>발행 예정 배출권: {privacyMode ? '*** tCO2' : '12,400 tCO2'}</span>
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
            <div className="flex justify-between items-center text-sm">
              <span className="text-slate-600 flex items-center"><i className="ph ph-circle text-slate-300 mr-2"></i> 자정 백업 (24:00)</span>
              <span className="font-medium text-slate-500">대기</span>
            </div>
          </div>
        </div>
      </div>

      {/* Timeline & Issues */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Today's Timeline */}
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
                  <div className="flex justify-between items-start">
                    <h4 className="text-sm font-medium text-slate-900">서울운수 (FMS 단말기 설치)</h4>
                    <span className="text-xs bg-slate-200 text-slate-700 px-2 py-0.5 rounded">미팅</span>
                  </div>
                </div>
              </div>
              <div className="relative pl-6">
                <span className="absolute -left-1.5 top-1 w-3 h-3 rounded-full bg-blue-500 border-2 border-white"></span>
                <div className="text-xs font-medium text-blue-600 mb-1">14:00 PM · 예정</div>
                <div className="bg-white p-3 rounded-lg border border-slate-200 shadow-sm">
                  <div className="flex justify-between items-start">
                    <h4 className="text-sm font-medium text-slate-900">경기교통 (재계약 논의)</h4>
                    <span className="text-xs bg-slate-200 text-slate-700 px-2 py-0.5 rounded">통화</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Open Issues Board */}
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
                <tr className="hover:bg-slate-50 cursor-pointer">
                  <td className="px-5 py-4"><span className="bg-yellow-100 text-yellow-700 px-2 py-1 rounded text-xs font-semibold">접수</span></td>
                  <td className="px-5 py-4">해찬농장 태양광 센서 누락</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
};

export default DashboardView;
