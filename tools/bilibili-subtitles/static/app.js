const $ = (id) => document.getElementById(id);

const state = {
  jobId: "",
  rows: [],
  fontScale: 1,
};

function setStatus(message, type = "loading") {
  const box = $("status");
  box.hidden = !message;
  box.className = "status " + type;
  box.textContent = message;
}

function setBusy(button, busy, busyText, normalText) {
  button.disabled = busy;
  button.textContent = busy ? busyText : normalText;
}

async function api(path, body) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  let data;
  try { data = await response.json(); } catch { data = { ok: false, error: `HTTP ${response.status}` }; }
  if (!response.ok || !data.ok) throw new Error(data.error || "操作失败");
  return data;
}

function fillTrackSelect(select, tracks, family, suggested) {
  select.replaceChildren();
  const blank = document.createElement("option");
  blank.value = "";
  blank.textContent = family === "english" ? "— 不使用英文轨 —" : "— 不使用中文轨 —";
  select.append(blank);
  const allowed = tracks.filter((track) =>
    track.family === family || track.family === "bilingual" || track.family === "unknown"
  );
  for (const track of allowed) {
    const option = document.createElement("option");
    option.value = track.id;
    const kind = track.kind === "automatic" ? "自动" : "字幕";
    option.textContent = `${track.label} · ${track.cue_count} 条 · ${kind}`;
    select.append(option);
  }
  if (allowed.some((track) => track.id === suggested)) select.value = suggested;
}

function renderInspection(data) {
  state.jobId = data.job_id;
  const video = data.video;
  $("video-title").textContent = video.title;
  $("video-title").href = video.source_url;
  $("video-detail").textContent = [video.uploader, video.duration ? video.duration_text : ""].filter(Boolean).join(" · ");

  const chips = $("track-chips");
  chips.replaceChildren();
  for (const track of data.tracks) {
    const chip = document.createElement("span");
    chip.className = "track-chip";
    chip.textContent = `${track.label} · ${track.cue_count} 条`;
    chip.title = track.sample;
    chips.append(chip);
  }
  fillTrackSelect($("english-track"), data.tracks, "english", data.suggested.english);
  fillTrackSelect($("chinese-track"), data.tracks, "chinese", data.suggested.chinese);

  const warnings = $("warnings");
  warnings.hidden = !data.warnings.length;
  warnings.textContent = data.warnings.join("\n");
  $("tracks-panel").hidden = false;
  $("reader").hidden = true;
  setStatus(`已找到 ${data.tracks.length} 条字幕轨，请确认中英文选择。`, "success");
  $("tracks-panel").scrollIntoView({ behavior: "smooth", block: "start" });
}

async function inspect(event) {
  event.preventDefault();
  const button = $("inspect-button");
  const url = $("video-url").value.trim();
  if (!url) return;
  localStorage.setItem("bili-subtitle-url", url);
  localStorage.setItem("bili-subtitle-browser", $("browser").value);
  $("tracks-panel").hidden = true;
  $("reader").hidden = true;
  setStatus("正在连接 B 站并读取字幕轨，通常需要几秒…", "loading");
  setBusy(button, true, "读取中…", "读取字幕 →");
  try {
    const data = await api("/api/inspect", { url, browser: $("browser").value });
    renderInspection(data);
  } catch (error) {
    setStatus(error.message, "error");
  } finally {
    setBusy(button, false, "读取中…", "读取字幕 →");
    button.replaceChildren();
    button.innerHTML = "<span>读取字幕</span><span aria-hidden=\"true\">→</span>";
  }
}

function makeCue(row, index) {
  const article = document.createElement("article");
  article.className = "subtitle-card";
  article.dataset.search = `${row.english} ${row.chinese}`.toLowerCase();

  const time = document.createElement("div");
  time.className = "cue-time";
  time.append(document.createTextNode(`${row.start_text} → ${row.end_text}`));
  const number = document.createElement("span");
  number.className = "cue-num";
  number.textContent = `#${String(index + 1).padStart(3, "0")}`;
  time.append(number);

  const copy = document.createElement("div");
  copy.className = "cue-copy";
  const english = document.createElement("p");
  english.className = "cue-en" + (row.english ? "" : " empty");
  english.textContent = row.english || "No English subtitle";
  const chinese = document.createElement("p");
  chinese.className = "cue-zh" + (row.chinese ? "" : " empty");
  chinese.textContent = row.chinese || "无中文字幕";
  copy.append(english, chinese);
  article.append(time, copy);
  return article;
}

function renderRows(data) {
  state.rows = data.rows;
  const list = $("subtitle-list");
  const fragment = document.createDocumentFragment();
  data.rows.forEach((row, index) => fragment.append(makeCue(row, index)));
  list.replaceChildren(fragment);
  $("reader-summary").textContent = `${data.count} 条时间轴字幕 · 可搜索、调字号或导出`;
  $("reader-notice").hidden = !data.notice;
  $("reader-notice").textContent = data.notice;
  $("download-md").href = `/api/jobs/${state.jobId}/download/md`;
  $("download-xlsx").href = `/api/jobs/${state.jobId}/download/xlsx`;
  $("subtitle-search").value = "";
  $("no-match").hidden = true;
  $("reader").hidden = false;
  $("reader").scrollIntoView({ behavior: "smooth", block: "start" });
}

async function generate() {
  const button = $("generate-button");
  setBusy(button, true, "正在对齐时间轴…", "生成对照字幕");
  try {
    const data = await api("/api/generate", {
      job_id: state.jobId,
      english_track: $("english-track").value,
      chinese_track: $("chinese-track").value,
    });
    renderRows(data);
  } catch (error) {
    setStatus(error.message, "error");
  } finally {
    setBusy(button, false, "正在对齐时间轴…", "生成对照字幕");
  }
}

function filterRows() {
  const query = $("subtitle-search").value.trim().toLowerCase();
  let visible = 0;
  document.querySelectorAll(".subtitle-card").forEach((card) => {
    const show = !query || card.dataset.search.includes(query);
    card.hidden = !show;
    if (show) visible += 1;
  });
  $("no-match").hidden = visible > 0;
}

function changeFont(delta) {
  state.fontScale = Math.min(1.35, Math.max(.8, state.fontScale + delta));
  document.documentElement.style.setProperty("--subtitle-scale", state.fontScale.toFixed(2));
}

async function copyMarkdown() {
  const button = $("copy-md");
  try {
    const response = await fetch(`/api/jobs/${state.jobId}/download/md`);
    if (!response.ok) throw new Error(await response.text());
    await navigator.clipboard.writeText(await response.text());
    button.textContent = "已复制 ✓";
  } catch {
    button.textContent = "复制失败，请下载";
  }
  window.setTimeout(() => { button.textContent = "复制 Markdown"; }, 1800);
}

function restoreForm() {
  const savedUrl = localStorage.getItem("bili-subtitle-url");
  const savedBrowser = localStorage.getItem("bili-subtitle-browser");
  if (savedUrl) $("video-url").value = savedUrl;
  if (["none", "edge", "chrome", "firefox"].includes(savedBrowser)) $("browser").value = savedBrowser;
}

$("inspect-form").addEventListener("submit", inspect);
$("generate-button").addEventListener("click", generate);
$("subtitle-search").addEventListener("input", filterRows);
$("font-smaller").addEventListener("click", () => changeFont(-.1));
$("font-larger").addEventListener("click", () => changeFont(.1));
$("copy-md").addEventListener("click", copyMarkdown);
$("to-top").addEventListener("click", () => $("reader").scrollIntoView({ behavior: "smooth" }));
restoreForm();
