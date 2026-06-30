import React from 'react';

interface SettingsViewProps {
  privacyMode: boolean;
}

const SettingsView: React.FC<SettingsViewProps> = ({ privacyMode }) => {
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
            <div className="flex justify-between items-center p-3 bg-slate-50 rounded border border-slate-100">
              <div>
                <p className="font-medium text-slate-900">보조 저장소 (NAS) 동기화</p>
                <p className="text-xs text-slate-500">2026-06-29 24:00:12 완료</p>
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
            <div>
              <span className="block text-xs text-slate-500 mb-1">Database Connection</span>
              <input type="text" value={privacyMode ? 'postgresql://***:***@localhost:5432/hooxi_cms' : 'postgresql://hooxi:hooxi_secret123@localhost:5432/hooxi_cms'} readOnly className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded text-sm" />
            </div>
          </div>
        </div>

        {/* System Info */}
        <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-sm">
          <h2 className="text-lg font-bold text-slate-900 mb-4 border-b border-slate-100 pb-2">시스템 정보</h2>
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <span className="block text-xs text-slate-500 mb-1">Node.js Version</span>
              <span className="font-medium text-slate-900">v20.18.0</span>
            </div>
            <div>
              <span className="block text-xs text-slate-500 mb-1">Python Version</span>
              <span className="font-medium text-slate-900">3.9.21</span>
            </div>
            <div>
              <span className="block text-xs text-slate-500 mb-1">PostgreSQL Version</span>
              <span className="font-medium text-slate-900">15.4</span>
            </div>
            <div>
              <span className="block text-xs text-slate-500 mb-1">Build Time</span>
              <span className="font-medium text-slate-900">{new Date().toLocaleDateString()}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default SettingsView;
