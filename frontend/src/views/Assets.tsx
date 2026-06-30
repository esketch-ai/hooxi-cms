import React from 'react';

interface AssetsViewProps {
  privacyMode: boolean;
}

const AssetsView: React.FC<AssetsViewProps> = ({ privacyMode }) => {
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
                <li className="p-1.5 hover:text-slate-900 cursor-pointer flex items-center"><i className="ph ph-folder text-slate-400 mr-2"></i> 해찬농장</li>
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
};

export default AssetsView;
