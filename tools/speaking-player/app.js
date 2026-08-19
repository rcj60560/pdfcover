// speaking-player/app.js
import {
  parseTracks, sortTracks, currentWordIndex, currentSentenceIndex,
  sentenceRange, clampSeek, formatTime, renderTrackRow, renderSentence,
} from "./core.js";

const TRACKS = "tracks/";
const $ = (id) => document.getElementById(id);
const audio = $("audio");

const state = {
  tracks: [], current: -1,
  timeline: null,          // {words, sentences, translation} | null
  sentIdx: -1, wordIdx: -1,
  loopSent: false, speed: 1, showZh: false,
};

/* ---------- 视图 ---------- */
function showHome() {
  $("player-view").hidden = true; $("home-view").hidden = false;
  $("back-btn").hidden = true; $("view-title").textContent = "🎧 口语跟读";
}

async function fetchJson(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error("HTTP " + res.status);
  return res.json();
}

async function loadHome() {
  const msg = $("home-msg"); msg.hidden = true;
  try {
    state.tracks = sortTracks(parseTracks(await fetchJson(TRACKS)));
    $("track-list").innerHTML = state.tracks
      .map((t, i) => renderTrackRow(t, i, i === state.current)).join("");
    if (!state.tracks.length) { msg.textContent = "暂无曲目"; msg.hidden = false; }
  } catch (e) {
    console.error("loadHome failed:", e);
    msg.textContent = "曲目加载失败，请检查服务或 nginx 配置"; msg.hidden = false;
  }
}

/* ---------- 打开曲目 ---------- */
async function playIndex(i) {
  const t = state.tracks[i];
  if (!t) return;
  state.current = i;
  state.timeline = null; state.sentIdx = -1; state.wordIdx = -1;
  $("home-view").hidden = true; $("player-view").hidden = false;
  $("back-btn").hidden = false; $("view-title").textContent = t.name;
  $("no-sub-msg").hidden = true; $("translation").hidden = true;
  $("sentence").textContent = t.name;   // 加载期间先显示曲名
  audio.src = TRACKS + encodeURIComponent(t.file);
  audio.playbackRate = state.speed;
  audio.play().catch(() => {});
  if (t.hasSubtitle) {
    try {
      const tl = await fetchJson(TRACKS + encodeURIComponent(t.name + ".json"));
      if (state.current !== i) return;   // 已切到别的曲目，丢弃过期响应
      state.timeline = tl;
      $("no-sub-msg").hidden = !!tl.words.length;
      updateZh();
    } catch (e) {
      console.error("timeline 加载失败:", e);
      if (state.current === i) $("no-sub-msg").hidden = false;   // 过期失败不覆盖新曲目
    }
  } else {
    $("no-sub-msg").hidden = false;
  }
  loadHome();   // 刷新列表高亮（home 隐藏时安全）
}

/* ---------- 字幕渲染（rAF 驱动） ---------- */
function tick() {
  if (state.timeline && !audio.paused) {
    const tMs = audio.currentTime * 1000;
    const sIdx = currentSentenceIndex(state.timeline.sentences, tMs);
    const range = sentenceRange(state.timeline.sentences, sIdx);
    // 单句循环：句尾前 30ms 回句头
    if (state.loopSent && range && tMs >= range.end - 30) {
      audio.currentTime = range.start / 1000;
      return scheduleTick();
    }
    if (sIdx !== state.sentIdx) {
      state.sentIdx = sIdx; state.wordIdx = -1;
      const s = state.timeline.sentences[sIdx];
      if (s) $("sentence").innerHTML =
        renderSentence(state.timeline.words, s.i, s.j, -1);
    }
    const wIdx = currentWordIndex(state.timeline.words, tMs);
    if (wIdx !== state.wordIdx) {
      state.wordIdx = wIdx;
      const s = state.timeline.sentences[Math.max(sIdx, 0)];
      if (s) $("sentence").innerHTML =
        renderSentence(state.timeline.words, s.i, s.j, wIdx);
    }
  }
  scheduleTick();
}
function scheduleTick() { requestAnimationFrame(tick); }

/* ---------- 控件 ---------- */
function seekSentence(delta) {
  if (!state.timeline) return;
  const idx = clampSentIdx(state.sentIdx + delta);
  const range = sentenceRange(state.timeline.sentences, idx);
  if (range) { audio.currentTime = range.start / 1000; state.sentIdx = -1; }
}
function clampSentIdx(i) {
  const n = state.timeline ? state.timeline.sentences.length : 0;
  return Math.max(0, Math.min(i, n - 1));
}
function updateZh() {
  const show = state.showZh && state.timeline && state.timeline.translation;
  $("translation").hidden = !show;
  if (show) $("translation").textContent = state.timeline.translation;
}

function bind() {
  let scrubbing = false;
  $("back-btn").addEventListener("click", showHome);
  $("track-list").addEventListener("click", (e) => {
    const row = e.target.closest(".track");
    if (row) playIndex(Number(row.dataset.index));
  });
  $("sentence").addEventListener("click", (e) => {
    const w = e.target.closest(".w");
    if (w && state.timeline) {
      const word = state.timeline.words[Number(w.dataset.w)];
      if (word) audio.currentTime = clampSeek(word.s / 1000, audio.duration);
    }
  });
  $("play").addEventListener("click", () => {
    if (audio.paused) audio.play().catch(() => {}); else audio.pause();
  });
  $("prev-sent").addEventListener("click", () => seekSentence(-1));
  $("next-sent").addEventListener("click", () => seekSentence(1));
  $("replay-sent").addEventListener("click", () => seekSentence(0));
  $("loop-sent").addEventListener("click", () => {
    state.loopSent = !state.loopSent;
    $("loop-sent").classList.toggle("active", state.loopSent);
  });
  $("speed").addEventListener("click", () => {
    const SPEEDS = [0.6, 0.8, 1, 1.25];
    state.speed = SPEEDS[(SPEEDS.indexOf(state.speed) + 1) % SPEEDS.length] || 1;
    audio.playbackRate = state.speed;
    $("speed").textContent = state.speed + "x";
  });
  $("zh").addEventListener("click", () => {
    state.showZh = !state.showZh;
    $("zh").classList.toggle("active", state.showZh);
    updateZh();
  });
  $("seek").addEventListener("pointerdown", () => { scrubbing = true; });
  $("seek").addEventListener("pointerup", () => { scrubbing = false; });
  $("seek").addEventListener("input", () => {
    if (audio.duration) audio.currentTime = ($("seek").value / 1000) * audio.duration;
  });
  audio.addEventListener("timeupdate", () => {
    $("cur-time").textContent = formatTime(audio.currentTime);
    if (audio.duration && !scrubbing) $("seek").value = (audio.currentTime / audio.duration) * 1000;
  });
  audio.addEventListener("loadedmetadata", () => {
    $("dur-time").textContent = formatTime(audio.duration);
  });
  audio.addEventListener("play", () => { $("play").textContent = "⏸"; });
  audio.addEventListener("pause", () => { $("play").textContent = "▶"; });
  audio.addEventListener("error", () => { $("sentence").textContent = "⚠ 音频加载失败"; });
}

bind();
showHome();
loadHome();
scheduleTick();
