// audioplayer/app.js
import {
  parseBooks, parseTracks, sortTracks,
  cycleLoop, cycleSpeed, nextTrack, clampSeek, formatTime,
  renderBookCard, renderTrackRow,
} from "./core.js";

const BOOKS = "books/"; // 相对页面：prod 解析为 /script/books/，本地为 /books/
const $ = (id) => document.getElementById(id);
const audio = $("audio");

const state = {
  books: [],          // [{ name, tracks: [filename,...] }]
  currentBook: null,  // 当前书名
  currentIndex: -1,   // 当前曲目下标
  loop: "off",
  speed: 1,
};

function currentBook() {
  return state.books.find((b) => b.name === state.currentBook);
}

async function fetchJson(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error("HTTP " + res.status);
  return res.json();
}

/* ---------- 视图切换 ---------- */
function showHome() {
  $("detail-view").hidden = true;
  $("home-view").hidden = false;
  $("back-btn").hidden = true;
  $("view-title").textContent = "📚 我的书库";
}
function showDetail(name) {
  $("home-view").hidden = true;
  $("detail-view").hidden = false;
  $("back-btn").hidden = false;
  $("view-title").textContent = name;
}

/* ---------- 首页 ---------- */
async function loadHome() {
  const msg = $("home-msg");
  msg.hidden = true;
  try {
    const names = parseBooks(await fetchJson(BOOKS));
    const books = [];
    for (const name of names) {
      try {
        const tracks = sortTracks(parseTracks(await fetchJson(BOOKS + encodeURIComponent(name) + "/")));
        if (tracks.length) books.push({ name, tracks });
      } catch (_) {
        /* 单本拉取失败不影响整体 */
      }
    }
    state.books = books;
    $("book-grid").innerHTML = books.map((b) => renderBookCard(b.name, b.tracks.length)).join("");
    if (!books.length) {
      msg.textContent = "暂无书目";
      msg.hidden = false;
    }
  } catch (e) {
    console.error("loadHome failed:", e);
    msg.textContent = "加载失败，请检查服务或 nginx 配置";
    msg.hidden = false;
  }
}

/* ---------- 详情 ---------- */
async function openBook(name) {
  if (!state.books.find((b) => b.name === name)) {
    try {
      const tracks = sortTracks(parseTracks(await fetchJson(BOOKS + encodeURIComponent(name) + "/")));
      if (tracks.length) state.books.push({ name, tracks });
    } catch (e) {
      console.error("openBook failed:", e);
      /* ignore */
    }
  }
  state.currentBook = name;
  state.currentIndex = -1;
  showDetail(name);
  renderTracks();
  const b = currentBook();
  const m = $("detail-msg");
  m.hidden = true;
  if (!b || !b.tracks.length) {
    m.textContent = "暂无音频";
    m.hidden = false;
  }
}

function renderTracks() {
  const b = currentBook();
  const tracks = b ? b.tracks : [];
  $("track-list").innerHTML = tracks
    .map((f, i) => renderTrackRow(f, i, i === state.currentIndex))
    .join("");
}

/* ---------- 播放 ---------- */
function trackUrl(book, file) {
  return BOOKS + encodeURIComponent(book) + "/" + encodeURIComponent(file);
}

function playIndex(i) {
  const b = currentBook();
  if (!b || i < 0 || i >= b.tracks.length) return;
  state.currentIndex = i;
  audio.src = trackUrl(b.name, b.tracks[i]);
  audio.playbackRate = state.speed;
  audio.load();
  audio.play().catch(() => {}); // 加载失败的兜底在 'error' 事件处理（Task 6）
  $("player").hidden = false;
  updateNowPlaying();
  updateMediaMetadata();
  updateMediaState();
  renderTracks();
}

function updateNowPlaying() {
  const b = currentBook();
  if (!b || state.currentIndex < 0) return;
  $("now-title").textContent = b.tracks[state.currentIndex] + " · " + b.name;
}

function togglePlay() {
  const b = currentBook();
  if (!audio.src) {
    if (b && b.tracks.length) playIndex(state.currentIndex < 0 ? 0 : state.currentIndex);
    return;
  }
  if (audio.paused) audio.play().catch(() => {});
  else audio.pause();
}

function gotoNext() {
  const b = currentBook();
  if (!b) return;
  const n = nextTrack(state.currentIndex, b.tracks.length, state.loop);
  if (n === null) {
    audio.pause();
    return;
  }
  playIndex(n);
}

function updateLoopButton() {
  const btn = $("loop");
  btn.textContent = state.loop === "one" ? "🔂" : "🔁";
  btn.classList.toggle("active", state.loop !== "off");
  btn.title = "循环：" + (state.loop === "off" ? "关" : state.loop === "one" ? "单曲" : "整本");
}

/* ---------- Media Session：锁屏/后台继续播放 + 系统媒体控制 ---------- */
function setupMediaSession() {
  if (!("mediaSession" in navigator)) return;
  const ms = navigator.mediaSession;
  const safe = (action, fn) => { try { ms.setActionHandler(action, fn); } catch (_) { /* 该 action 不支持时忽略 */ } };
  safe("play", () => audio.play().catch(() => {}));
  safe("pause", () => audio.pause());
  safe("previoustrack", () => playIndex(Math.max(0, state.currentIndex - 1)));
  safe("nexttrack", () => gotoNext());
  safe("seekbackward", () => { audio.currentTime = clampSeek(audio.currentTime - 10, audio.duration); });
  safe("seekforward", () => { audio.currentTime = clampSeek(audio.currentTime + 10, audio.duration); });
}

function updateMediaMetadata() {
  if (!("mediaSession" in navigator)) return;
  const b = currentBook();
  if (!b || state.currentIndex < 0) return;
  const file = b.tracks[state.currentIndex];
  const m = String(file).match(/^T(\d+)(?:-P(\d+))?\.mp3$/i);
  const title = m ? `Test ${Number(m[1])}${m[2] ? ` · Part ${Number(m[2])}` : ""}` : file;
  try {
    navigator.mediaSession.metadata = new MediaMetadata({ title, artist: b.name, album: "雅思听力" });
  } catch (_) { /* MediaMetadata 不可用时忽略 */ }
}

function updateMediaState() {
  if (!("mediaSession" in navigator)) return;
  navigator.mediaSession.playbackState = audio.paused ? "paused" : "playing";
}

function updateMediaPosition() {
  if (!("mediaSession" in navigator)) return;
  const d = audio.duration;
  if (!Number.isFinite(d) || d <= 0) return;
  try {
    navigator.mediaSession.setPositionState({
      duration: d,
      position: Math.min(audio.currentTime, d),
      playbackRate: audio.playbackRate || 1,
    });
  } catch (_) { /* 无效值时忽略 */ }
}

function bind() {
  let scrubbing = false;
  $("back-btn").addEventListener("click", showHome);

  $("book-grid").addEventListener("click", (e) => {
    const card = e.target.closest(".card");
    if (!card) return;
    openBook(card.dataset.book);
  });

  $("track-list").addEventListener("click", (e) => {
    const row = e.target.closest(".track");
    if (!row) return;
    playIndex(Number(row.dataset.index));
  });

  $("play").addEventListener("click", togglePlay);

  $("prev").addEventListener("click", () => {
    playIndex(Math.max(0, state.currentIndex - 1));
  });
  $("next").addEventListener("click", gotoNext);

  $("back5").addEventListener("click", () => {
    audio.currentTime = clampSeek(audio.currentTime - 5, audio.duration);
  });
  $("fwd5").addEventListener("click", () => {
    audio.currentTime = clampSeek(audio.currentTime + 5, audio.duration);
  });

  $("loop").addEventListener("click", () => {
    state.loop = cycleLoop(state.loop);
    updateLoopButton();
  });

  $("speed").addEventListener("click", () => {
    state.speed = cycleSpeed(state.speed);
    audio.playbackRate = state.speed;
    $("speed").textContent = state.speed + "x";
  });

  $("mute").addEventListener("click", () => {
    audio.muted = !audio.muted;
    $("mute").textContent = audio.muted ? "🔇" : "🔊";
  });

  $("seek").addEventListener("pointerdown", () => { scrubbing = true; });
  $("seek").addEventListener("pointerup", () => { scrubbing = false; });
  $("seek").addEventListener("input", () => {
    if (audio.duration) audio.currentTime = ($("seek").value / 1000) * audio.duration;
  });

  audio.addEventListener("timeupdate", () => {
    $("cur-time").textContent = formatTime(audio.currentTime);
    if (audio.duration && !scrubbing) $("seek").value = (audio.currentTime / audio.duration) * 1000;
    updateMediaPosition();
  });
  audio.addEventListener("loadedmetadata", () => {
    $("dur-time").textContent = formatTime(audio.duration);
    updateMediaPosition();
  });
  audio.addEventListener("play", () => { $("play").textContent = "⏸"; updateMediaState(); updateMediaPosition(); });
  audio.addEventListener("pause", () => { $("play").textContent = "▶"; updateMediaState(); });
  audio.addEventListener("ended", gotoNext);
  audio.addEventListener("error", () => {
    const row = document.querySelector(`.track[data-index="${state.currentIndex}"]`);
    if (row) row.classList.add("is-broken");
    const b = currentBook();
    if (!b) return;
    // 跳过损坏的源；绝不重播刚出错的源，避免 loop=one/all 下死循环
    if (state.currentIndex < b.tracks.length - 1) playIndex(state.currentIndex + 1);
    else audio.pause();
  });
}

bind();
setupMediaSession();
showHome();
loadHome();
updateLoopButton();
