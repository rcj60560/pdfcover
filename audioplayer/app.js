// audioplayer/app.js
import {
  parseBooks, parseTracks, sortTracks,
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
    } catch (_) {
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

/* ---------- 事件（播放相关在 Task 5 接入；本任务先绑导航与选曲占位）---------- */
function bind() {
  $("back-btn").addEventListener("click", showHome);

  $("book-grid").addEventListener("click", (e) => {
    const card = e.target.closest(".card");
    if (!card) return;
    openBook(card.dataset.book);
  });

  $("track-list").addEventListener("click", (e) => {
    const row = e.target.closest(".track");
    if (!row) return;
    // 播放逻辑在 Task 5；这里先标记选中行，便于本任务验证
    state.currentIndex = Number(row.dataset.index);
    renderTracks();
  });
}

bind();
showHome();
loadHome();
