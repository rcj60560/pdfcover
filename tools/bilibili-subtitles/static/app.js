const $ = (id) => document.getElementById(id);

const state = {
  jobId: "",
  rows: [],
  fontScale: 1,
};

let transcribeTimer = null;

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

function resetTranscribePanel() {
  if (transcribeTimer) { window.clearTimeout(transcribeTimer); transcribeTimer = null; }
  $("transcribe-progress").hidden = true;
  $("transcribe-phase").textContent = "准备中…";
  $("transcribe-log").textContent = "";
  renderStepTrack(null);
}

function renderStepTrack(stage) {
  // 步骤条三步：下载音频 → Whisper 转写 → 完成；服务端 step≥3 一律落到「完成」
  const active = stage ? Math.min(Number(stage.step) || 0, 3) : 0;
  document.querySelectorAll("#transcribe-steps .step").forEach((step) => {
    const order = Number(step.dataset.step);
    step.classList.toggle("active", order === active);
    step.classList.toggle("done", order < active);
  });
  const detail = $("transcribe-phase");
  if (stage && stage.detail) detail.textContent = stage.detail;
}

async function inspect(event) {
  event.preventDefault();
  const url = $("video-url").value.trim();
  if (!url) return;
  localStorage.setItem("bili-subtitle-url", url);
  localStorage.setItem("bili-subtitle-browser", $("browser").value);
  $("fetch-panel").hidden = true;
  $("reader").hidden = true;
  setStatus("正在连接 B 站读取视频信息，通常需要几秒…", "loading");
  const button = $("inspect-button");
  button.disabled = true;
  try {
    const data = await api("/api/inspect", { url, browser: $("browser").value });
    await startFetch(data);
  } catch (error) {
    setStatus(error.message, "error");
  } finally {
    button.disabled = false;
  }
}

async function startFetch(data) {
  state.jobId = data.job_id;
  const video = data.video;
  $("video-title").textContent = video.title;
  $("video-title").href = video.source_url;
  $("video-detail").textContent = [video.uploader, video.duration ? video.duration_text : ""].filter(Boolean).join(" · ");
  const warnings = $("warnings");
  warnings.hidden = !data.warnings.length;
  warnings.textContent = data.warnings.join("\n");
  resetTranscribePanel();
  $("fetch-panel").hidden = false;
  $("fetch-panel").scrollIntoView({ behavior: "smooth", block: "start" });
  if (data.can_transcribe) {
    beginTranscribe();
  } else if ((data.tracks || []).length) {
    generateFromTrack(data);
  } else {
    setStatus("这个视频没有可用的字幕轨，也无法语音识别。", "error");
  }
}

async function generateFromTrack(data) {
  // 有字幕轨的视频：自动用推荐的英文轨生成（仅英文，中文走词典精翻）
  setStatus("使用视频英文字幕轨生成英文原文…", "loading");
  const tracks = data.tracks || [];
  let track = tracks.find((item) => item.id === (data.suggested && data.suggested.english));
  if (!track) track = tracks.find((item) => item.family === "english" || item.family === "bilingual");
  try {
    const result = await api("/api/generate", {
      job_id: state.jobId,
      english_track: track ? track.id : "",
      chinese_track: "",
    });
    renderRows(result);
    setStatus("已用英文字幕轨生成，点「📋 复制英文全文」去词典精翻。", "success");
  } catch (error) {
    setStatus(error.message, "error");
  }
}

const TRANSCRIBE_PHASE_TEXT = {
  running: "识别中：下载音频 → Whisper 转写（仅英文，约几分钟，请保持页面打开）",
  done: "识别完成",
  error: "识别失败",
};

async function beginTranscribe() {
  $("transcribe-progress").hidden = false;
  $("transcribe-phase").textContent = TRANSCRIBE_PHASE_TEXT.running;
  $("transcribe-log").textContent = "正在启动语音识别（仅拉英文，跳过机翻）…\n";
  try {
    await api(`/api/jobs/${state.jobId}/transcribe`, {
      browser: localStorage.getItem("bili-subtitle-browser") || "none",
      translate: false,
    });
    transcribeTimer = window.setTimeout(pollTranscribe, 1500);
  } catch (error) {
    $("transcribe-phase").textContent = "启动失败";
    $("transcribe-log").textContent += `${error.message}\n`;
  }
}

async function pollTranscribe() {
  let data = null;
  try {
    const response = await fetch(`/api/jobs/${state.jobId}/transcribe/status`);
    data = await response.json().catch(() => ({ ok: false, error: `HTTP ${response.status}` }));
    if (!response.ok || !data.ok) throw new Error(data.error || "查询进度失败");
    $("transcribe-phase").textContent = TRANSCRIBE_PHASE_TEXT[data.phase] || data.phase;
    renderStepTrack(data.stage);
    if (data.log && data.log.length) {
      const logBox = $("transcribe-log");
      logBox.textContent = data.log.join("\n") + "\n";
      logBox.scrollTop = logBox.scrollHeight;
    }
    if (data.phase === "running") {
      transcribeTimer = window.setTimeout(pollTranscribe, 2500);
      return;
    }
    if (data.phase === "done") {
      renderRows({
        rows: data.rows,
        count: data.count,
        notice: data.notice,
      });
      setStatus("英文原文已就绪：点「📋 复制英文全文」丢给词典，中文粘到右侧一键排版。", "success");
      return;
    }
    if (data.phase === "error") {
      setStatus(`识别失败：${data.error}`, "error");
      $("transcribe-log").textContent += `${data.error}\n`;
    }
  } catch (error) {
    setStatus(error.message, "error");
    $("transcribe-log").textContent += `${error.message}\n`;
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
  $("subtitle-search").value = "";
  $("no-match").hidden = true;
  $("reader").hidden = false;
  $("reader").scrollIntoView({ behavior: "smooth", block: "start" });
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

async function copyEnglish() {
  const button = $("copy-en");
  try {
    const response = await fetch(`/api/jobs/${state.jobId}/plain-text`);
    if (!response.ok) throw new Error("读取失败");
    const { english } = await response.json();
    if (!english) throw new Error("无英文内容");
    await navigator.clipboard.writeText(english);
    button.textContent = "已复制 ✓ 丢词典吧";
  } catch {
    button.textContent = "复制失败";
  }
  window.setTimeout(() => { button.textContent = "📋 复制英文全文"; }, 2200);
}

function alignStatus(message, kind) {
  const status = $("align-status");
  status.textContent = message;
  status.className = "align-status " + kind;
  status.hidden = false;
}

async function autoAlign() {
  const button = $("auto-align");
  setBusy(button, true, "排版中…约 1-2 分钟", "🤖 一键排版");
  alignStatus("排版中：本机模型正在切分对齐，请勿关闭页面…", "ok");
  try {
    const data = await api(`/api/jobs/${state.jobId}/auto-align`, { text: $("raw-chinese-text").value });
    renderRows(data);
    alignStatus(`一键排版完成：已回填 ${data.count} 块中文，点「下载 Markdown」即为最终双语稿。`, "ok");
  } catch (error) {
    alignStatus(`${error.message}\n可重试，或点「保存，交给 Claude 排版」走对话兜底。`, "err");
  } finally {
    setBusy(button, false, "排版中…约 1-2 分钟", "🤖 一键排版");
  }
}

async function saveRawChinese() {
  const button = $("save-raw-ch");
  setBusy(button, true, "保存中…", "保存，交给 Claude 排版");
  try {
    const data = await api(`/api/jobs/${state.jobId}/raw-chinese`, { text: $("raw-chinese-text").value });
    alignStatus(`已保存 ${data.saved_chars} 字。现在对 Claude 说「排版」，完成后回来点「⟳ 应用排版结果」。`, "ok");
  } catch (error) {
    alignStatus(error.message, "err");
  } finally {
    setBusy(button, false, "保存中…", "保存，交给 Claude 排版");
  }
}

async function applyAlignedResult() {
  const button = $("apply-align");
  setBusy(button, true, "刷新中…", "⟳ 应用排版结果");
  try {
    const response = await fetch(`/api/jobs/${state.jobId}/rows`);
    if (!response.ok) throw new Error("读取失败");
    const data = await response.json();
    renderRows(data);
    const filled = data.rows.filter((row) => row.chinese).length;
    if (!filled) {
      alignStatus("还没有排版结果——先保存词典中文，再让 Claude 排版。", "err");
    } else {
      alignStatus(`已回填 ${filled}/${data.count} 块中文${filled === data.count ? "" : "（尚有缺块）"}；点「下载 Markdown」即为最终双语稿。`, "ok");
    }
  } catch (error) {
    alignStatus(error.message, "err");
  } finally {
    setBusy(button, false, "刷新中…", "⟳ 应用排版结果");
  }
}

async function stopServer() {
  const confirmed = window.confirm(
    "确定停止服务？进行中的任务会中断；已完成的转写会保留在本地缓存。");
  if (!confirmed) return;
  const button = $("stop-server");
  button.disabled = true;
  button.textContent = "停止中…";
  try {
    await api("/api/shutdown", {});
  } catch { /* 进程退出导致连接断开属预期 */ }
  // 验证真的停了：探测到连不上才算数，避免"以为重启了其实没关"
  const deadline = Date.now() + 5000;
  let stopped = false;
  while (Date.now() < deadline) {
    await new Promise((resolve) => window.setTimeout(resolve, 500));
    try {
      await fetch("/api/health", { cache: "no-store" });
    } catch {
      stopped = true;
      break;
    }
  }
  if (transcribeTimer) { window.clearTimeout(transcribeTimer); transcribeTimer = null; }
  if (stopped) {
    button.textContent = "已停止";
    $("server-started").textContent = "";
    setStatus("服务已停止（已确认进程退出），可以关闭本页。", "success");
    window.close();
  } else {
    button.disabled = false;
    button.textContent = "停止服务";
    setStatus("服务似乎仍在运行：请到启动它的终端按 Ctrl+C 结束进程。", "error");
  }
}

async function loadServerStarted() {
  try {
    const response = await fetch("/api/health", { cache: "no-store" });
    const data = await response.json();
    if (data.ok && data.started_at) {
      $("server-started").textContent = `服务启动于 ${data.started_at}`;
    }
  } catch { /* 健康检查失败不打扰页面 */ }
}

function restoreForm() {
  const savedUrl = localStorage.getItem("bili-subtitle-url");
  const savedBrowser = localStorage.getItem("bili-subtitle-browser");
  if (savedUrl) $("video-url").value = savedUrl;
  if (["none", "edge", "chrome", "firefox"].includes(savedBrowser)) $("browser").value = savedBrowser;
}

$("inspect-form").addEventListener("submit", inspect);
$("stop-server").addEventListener("click", stopServer);
$("subtitle-search").addEventListener("input", filterRows);
$("font-smaller").addEventListener("click", () => changeFont(-.1));
$("font-larger").addEventListener("click", () => changeFont(.1));
$("copy-en").addEventListener("click", copyEnglish);
$("auto-align").addEventListener("click", autoAlign);
$("save-raw-ch").addEventListener("click", saveRawChinese);
$("apply-align").addEventListener("click", applyAlignedResult);
$("to-top").addEventListener("click", () => $("reader").scrollIntoView({ behavior: "smooth" }));
restoreForm();
loadServerStarted();
