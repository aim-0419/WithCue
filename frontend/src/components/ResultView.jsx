import React from 'react';
import {
  CheckCircle2,
  AlertTriangle,
  Share2,
  RefreshCw,
  ChevronRight,
  Download,
  AlertOctagon,
} from 'lucide-react';
import {
  RadialBarChart,
  RadialBar,
  ResponsiveContainer,
  PolarAngleAxis,
} from 'recharts';

export function ResultView({ mode, onClose, onRetry }) {
  const isCheck = mode === 'check';

  // 타이틀/라벨
  const title = isCheck ? '자세 분석 결과 리포트' : '운동 수행 결과 리포트';
  const scoreLabel = isCheck ? '신체 밸런스 점수' : '운동 수행 점수';
  const scoreValue = isCheck ? 78 : 85;
  const scoreColor = isCheck ? '#eab308' : '#3b82f6';
  const scoreGrade = isCheck ? '주의 필요' : '양호';

  const scoreData = [{ name: '점수', value: scoreValue, fill: scoreColor }];

  return (
    <div className="w-full h-full bg-slate-950 text-white flex flex-col relative overflow-hidden">
      {/* 배경 효과 */}
      <div
        className={`absolute top-0 left-0 w-full h-64 bg-gradient-to-b ${
          isCheck ? 'from-amber-900/20' : 'from-blue-900/20'
        } to-transparent pointer-events-none`}
      />
      <div
        className={`absolute bottom-0 right-0 w-96 h-96 ${
          isCheck ? 'bg-amber-600/10' : 'bg-blue-600/10'
        } rounded-full blur-3xl pointer-events-none`}
      />

      {/* 헤더 */}
      <header className="flex items-center justify-between px-8 py-6 z-10">
        <div className="flex items-center gap-3">
          <div
            className={`w-2 h-8 ${
              isCheck ? 'bg-amber-500' : 'bg-blue-600'
            } rounded-full`}
          />
          <h1 className="text-2xl font-bold tracking-tight">{title}</h1>
        </div>
        <div className="text-slate-400 text-sm font-medium">
          2026. 01. 30 • 14:45
        </div>
      </header>

      {/* 메인 */}
      <main className="flex-1 grid grid-cols-12 gap-6 px-8 pb-8 z-10">
        {/* 좌측: 점수 */}
        <div className="col-span-4 flex flex-col gap-6">
          <div className="flex-1 bg-slate-900/50 border border-slate-800 rounded-3xl p-6 flex flex-col items-center justify-center">
            <h2 className="text-slate-400 font-bold mb-4 text-xs tracking-widest uppercase">
              {scoreLabel}
            </h2>

            <div className="relative w-48 h-48 flex items-center justify-center">
              <ResponsiveContainer width="100%" height="100%">
                <RadialBarChart
                  innerRadius="80%"
                  outerRadius="100%"
                  barSize={10}
                  data={scoreData}
                  startAngle={90}
                  endAngle={-270}
                >
                  <PolarAngleAxis
                    type="number"
                    domain={[0, 100]}
                    angleAxisId={0}
                    tick={false}
                  />
                  <RadialBar background dataKey="value" cornerRadius={30} />
                </RadialBarChart>
              </ResponsiveContainer>

              <div className="absolute inset-0 flex flex-col items-center justify-center">
                <span className="text-6xl font-black">{scoreValue}</span>
                <span
                  className={`font-bold text-lg ${
                    isCheck ? 'text-amber-500' : 'text-blue-500'
                  }`}
                >
                  {scoreGrade}
                </span>
              </div>
            </div>

            <p className="text-center text-slate-300 text-sm mt-4 px-4 leading-relaxed">
              {isCheck ? (
                <>
                  왼쪽 어깨가 오른쪽보다{' '}
                  <span className="text-amber-400 font-bold">1.5cm</span> 높게
                  측정되었습니다. 경미한 자세 불균형이 관찰됩니다.
                </>
              ) : (
                <>
                  이전 세션 대비{' '}
                  <span className="text-green-400 font-bold">12%</span> 안정성이
                  향상되었습니다. 매우 좋은 수행입니다.
                </>
              )}
            </p>
          </div>

          {/* 요약 지표 */}
          <div className="grid grid-cols-2 gap-4 h-32">
            <div className="bg-slate-900/50 border border-slate-800 rounded-2xl p-4 flex flex-col items-center justify-center">
              <span className="text-slate-500 text-xs font-bold mb-1">
                {isCheck ? '목 각도' : '운동 시간'}
              </span>
              <span className="text-2xl font-bold">
                {isCheck ? '15°' : '12:30'}
              </span>
            </div>

            <div className="bg-slate-900/50 border border-slate-800 rounded-2xl p-4 flex flex-col items-center justify-center">
              <span className="text-slate-500 text-xs font-bold mb-1">
                {isCheck ? '어깨 기울기' : '반복 횟수'}
              </span>
              <span
                className={`text-2xl font-bold flex items-center gap-1 ${
                  isCheck ? 'text-amber-500' : ''
                }`}
              >
                {isCheck ? '4.2°' : '15'}
                {isCheck ? (
                  <AlertTriangle size={16} />
                ) : (
                  <span className="text-sm text-slate-500 font-normal">
                    /15
                  </span>
                )}
              </span>
            </div>
          </div>
        </div>

        {/* 중앙: 상세 피드백 */}
        <div className="col-span-5">
          <div className="h-full bg-slate-900/50 border border-slate-800 rounded-3xl p-6">
            <h3 className="text-lg font-bold mb-6">
              {isCheck ? '상세 진단 결과' : '운동 수행 피드백'}
            </h3>

            <div className="space-y-4">
              {/* 긍정 */}
              <div className="flex gap-4 p-4 bg-green-500/10 border border-green-500/20 rounded-2xl">
                <div className="bg-green-500/20 p-2 rounded-lg text-green-400">
                  <CheckCircle2 size={20} />
                </div>
                <div>
                  <h4 className="font-bold text-sm mb-1">
                    {isCheck ? '골반 정렬 안정적' : '척추 안정성 우수'}
                  </h4>
                  <p className="text-xs text-green-200/70 leading-relaxed">
                    {isCheck
                      ? '좌우 골반 높이 차이가 거의 없으며 하체 밸런스가 양호합니다.'
                      : '동작 수행 중 척추 중립 상태가 대부분 유지되었습니다.'}
                  </p>
                </div>
              </div>

              {/* 경고 */}
              <div className="flex gap-4 p-4 bg-amber-500/10 border border-amber-500/20 rounded-2xl">
                <div className="bg-amber-500/20 p-2 rounded-lg text-amber-400">
                  {isCheck ? (
                    <AlertOctagon size={20} />
                  ) : (
                    <AlertTriangle size={20} />
                  )}
                </div>
                <div>
                  <h4 className="font-bold text-sm mb-1">
                    {isCheck ? '라운드 숄더 경향' : '무릎 안쪽 쏠림 감지'}
                  </h4>
                  <p className="text-xs text-amber-200/70 leading-relaxed">
                    {isCheck
                      ? '어깨 위치가 전방으로 이동해 있어 흉곽 스트레칭이 필요합니다.'
                      : '스쿼트 동작 중 무릎 정렬이 반복적으로 흐트러졌습니다.'}
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* 우측: 액션 */}
        <div className="col-span-3">
          <div className="h-full bg-gradient-to-br from-slate-800 to-slate-900 border border-slate-700 p-6 rounded-3xl flex flex-col justify-between">
            <div>
              <h3 className="text-lg font-bold mb-4">
                {isCheck ? '진단 완료' : '세션 완료'}
              </h3>
              <p className="text-slate-400 text-sm leading-relaxed">
                {isCheck
                  ? '현재 자세 상태가 저장되었습니다. 권장 운동을 꾸준히 수행해 주세요.'
                  : '운동 기록이 저장되었습니다. 추후 변화 추이를 확인할 수 있습니다.'}
              </p>
            </div>

            <div className="flex flex-col gap-3">
              <button
                onClick={onClose}
                className="w-full py-4 bg-blue-600 hover:bg-blue-500 rounded-xl font-bold flex items-center justify-center gap-2"
              >
                {isCheck ? '메인으로 이동' : '결과 저장'}
                <ChevronRight size={18} />
              </button>

              <button
                onClick={onRetry}
                className="w-full py-4 bg-slate-800 hover:bg-slate-700 rounded-xl font-bold flex items-center justify-center gap-2"
              >
                <RefreshCw size={18} />
                {isCheck ? '재측정' : '다시 운동'}
              </button>

              <div className="flex gap-3 mt-2">
                <button className="flex-1 py-3 bg-slate-900 border border-slate-700 rounded-xl flex items-center justify-center">
                  <Share2 size={18} />
                </button>
                <button className="flex-1 py-3 bg-slate-900 border border-slate-700 rounded-xl flex items-center justify-center">
                  <Download size={18} />
                </button>
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
