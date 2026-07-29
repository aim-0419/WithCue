// 자세 검사 단계별 오디오 스크립트 정의 및 순차 재생 유틸리티

const B = "/audio";

// label: 좌상단에 표시할 단계 텍스트. 없으면 표시하지 않음.
function s(dir, name, delay, phase, label) {
  return {
    file: `${B}/${dir}/${name}`,
    delay,
    ...(label ? { label } : {}),
    ...(phase ? { phase } : {}),
  };
}

// ─── 어깨 ───
export const SHOULDER_SCRIPT = [
  s("shoulder", "01_어깨_가동범위_검사를_시작합니다.mp3",                                       1500, null, "Start"),
  s("shoulder", "02_정면을_바라보고_편안하게_서주세요.mp3",                                      2500, null, "Prepare"),
  s("shoulder", "03_양팔을_앞으로_천천히_최대한_높이_들어올려_주세요.mp3",                       500,  null, "Ascent"),
  s("shoulder", "04_통증이_없는_범위에서_진행해주세요_양_팔_높이가_달라도_괜찮습니다.mp3",        4000, null, "Ascent"),
  s("shoulder", "05_그_자세_그대로_잠시_유지해주세요.mp3",                                       3000, null, "Hold"),
  s("shoulder", "06_팔을_천천히_내려주세요.mp3",                                                 2000, null, "Descent"),
  s("shoulder", "07_어깨_검사가_완료되었습니다.mp3",                                             500,  null, "End"),
];

// ─── 목 ───
export const NECK_SCRIPT = [
  s("neck", "01_목_가동범위_검사를_시작합니다.mp3",                                              1500, null, "Start"),
  s("neck", "02_정면을_바라보고_편안하게_서주세요.mp3",                                           2000, null, "Prepare"),
  s("neck", "03_고개를_천천히_왼쪽으로_최대한_돌려주세요.mp3",                                    2500, null, "Left"),
  s("neck", "04_그_자세_그대로_잠시_유지해주세요.mp3",                                            3000, null, "Hold"),
  s("neck", "05_이번엔_고개를_천천히_오른쪽으로_최대한_돌려주세요.mp3",                            2500, null, "Right"),
  s("neck", "06_그_자세_그대로_잠시_유지해주세요.mp3",                                            3000, null, "Hold"),
  s("neck", "07_고개를_천천히_정면으로_돌아와_주세요.mp3",                                        2000, null, "Front"),
  s("neck", "08_목_검사가_완료되었습니다.mp3",                                                    500,  null, "End"),
];

// ─── 무릎 ───
export const KNEE_SCRIPT = [
  s("knee", "01_무릎_가동범위_검사를_시작합니다.mp3",                                           1500, null,                "Start"),
  s("knee", "02_의자에_앉아서_준비해주세요.mp3",                                                3500, null,                "Sit"),
  s("knee", "03_왼쪽_다리를_천천히_최대한_펴주세요.mp3",                                        3000, "KNEE_LEFT_EXTEND",  "Left_Up"),
  s("knee", "04_다시_무릎을_구부려_원래_자세로_돌아와_주세요.mp3",                               2500, null,                "Left_Down"),
  s("knee", "05_이번엔_오른쪽_다리를_천천히_최대한_펴주세요.mp3",                                3000, "KNEE_RIGHT_EXTEND", "Right_Up"),
  s("knee", "06_다시_무릎을_구부려_원래_자세로_돌아와_주세요.mp3",                               2500, null,                "Right_Down"),
  s("knee", "07_천천히_일어서주세요.mp3",                                                        4000, null,                "Stand"),
  s("knee", "08_왼쪽_무릎을_최대한_높이_들어올려주세요.mp3",                                     3000, "KNEE_LEFT_RAISE",   "Left_Up"),
  s("knee", "09_천천히_내려주세요.mp3",                                                          2000, null,                "Left_Down"),
  s("knee", "10_이번엔_오른쪽_무릎을_최대한_높이_들어올려주세요.mp3",                            3000, "KNEE_RIGHT_RAISE",  "Right_Up"),
  s("knee", "11_천천히_내려주세요.mp3",                                                          2000, null,                "Right_Down"),
  s("knee", "12_무릎_검사가_완료되었습니다.mp3",                                                 500,  null,                "End"),
];

// ─── 전체 정밀검사 (어깨 → 목 → 무릎) ───
export const FULL_BODY_SCRIPT = [
  s("full-body", "01_전신_가동범위_검사를_시작합니다_검사는_어깨_목_무릎_순서로_진행됩니다.mp3", 1500),
  ...SHOULDER_SCRIPT,
  ...NECK_SCRIPT,
  ...KNEE_SCRIPT,
  s("full-body", "02_전신_가동범위_검사가_모두_완료되었습니다..mp3", 500),
];

export function getScript(part) {
  switch (part) {
    case "shoulder": return SHOULDER_SCRIPT;
    case "neck":     return NECK_SCRIPT;
    case "knee":     return KNEE_SCRIPT;
    default:         return FULL_BODY_SCRIPT;
  }
}

// ─── 순차 재생 ───
export async function playScript(script, { onPhase, onStep, signal } = {}) {
  for (const item of script) {
    if (signal?.aborted) break;
    if (item.label && onStep) onStep(item.label);
    if (item.phase && onPhase) onPhase(item.phase);
    if (item.file) await playAudio(item.file, signal);
    if (signal?.aborted) break;
    if (item.delay) await waitMs(item.delay, signal);
  }
}

function playAudio(src, signal) {
  return new Promise((resolve) => {
    if (signal?.aborted) return resolve();
    const audio = new Audio(src);
    const done = () => { cleanup(); resolve(); };
    const onAbort = () => { audio.pause(); done(); };
    function cleanup() {
      audio.removeEventListener("ended", done);
      audio.removeEventListener("error", done);
      signal?.removeEventListener("abort", onAbort);
    }
    audio.addEventListener("ended", done);
    audio.addEventListener("error", done);
    signal?.addEventListener("abort", onAbort);
    audio.play().catch(done);
  });
}

function waitMs(ms, signal) {
  return new Promise((resolve) => {
    if (signal?.aborted) return resolve();
    const t = setTimeout(resolve, ms);
    signal?.addEventListener("abort", () => { clearTimeout(t); resolve(); });
  });
}
