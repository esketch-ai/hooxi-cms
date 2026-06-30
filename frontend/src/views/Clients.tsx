import React, { useState } from 'react';

interface ClientsViewProps {
  privacyMode: boolean;
}

const ClientsView: React.FC<ClientsViewProps> = ({ privacyMode }) => {
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
};

export default ClientsView;
