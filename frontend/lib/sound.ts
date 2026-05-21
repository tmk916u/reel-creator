// frontend/lib/sound.ts
// Web Audio API で合成する完了通知音。音声ファイル不要。
//
// ブラウザの autoplay 制限対策で、最初に user gesture（処理開始ボタン押下など）が
// あった時点で primeAudio() を呼んでおくと、後で playCompletionSound() が
// 確実に再生される。

let audioCtx: AudioContext | null = null;

type WebkitWindow = Window & { webkitAudioContext?: typeof AudioContext };

function getCtx(): AudioContext | null {
  if (typeof window === "undefined") return null;
  if (audioCtx) return audioCtx;
  const Ctor = window.AudioContext || (window as WebkitWindow).webkitAudioContext;
  if (!Ctor) return null;
  try {
    audioCtx = new Ctor();
  } catch {
    return null;
  }
  return audioCtx;
}

/**
 * user gesture 内で呼んで AudioContext を起こす。
 * 以後 playCompletionSound() が autoplay 制限を回避して再生できる。
 */
export function primeAudio(): void {
  const ctx = getCtx();
  if (!ctx) return;
  if (ctx.state === "suspended") {
    void ctx.resume().catch(() => {});
  }
}

/**
 * 完了通知音を再生する（2音のチャイム、約 400ms）。
 * AudioContext が未起動なら無音で何もしない。
 */
export function playCompletionSound(): void {
  const ctx = getCtx();
  if (!ctx) return;
  if (ctx.state === "suspended") {
    void ctx.resume().catch(() => {});
  }
  const now = ctx.currentTime;
  const master = ctx.createGain();
  master.gain.value = 0.3;
  master.connect(ctx.destination);

  const playNote = (freq: number, start: number, dur: number) => {
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = "sine";
    osc.frequency.value = freq;
    gain.gain.setValueAtTime(0, now + start);
    gain.gain.linearRampToValueAtTime(1, now + start + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.001, now + start + dur);
    osc.connect(gain).connect(master);
    osc.start(now + start);
    osc.stop(now + start + dur);
  };

  // A5 → E6 の上昇チャイム（明るい完了感）
  playNote(880, 0, 0.18);
  playNote(1320, 0.12, 0.28);
}
