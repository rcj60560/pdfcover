const $ = (id) => document.getElementById(id);

const state = {
  jobId: "",
  rows: [],
  fontScale: 1,
};

let transcribeTimer = null;
let ttsTimer = null;
let retranscribing = false;

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

function resetTranscribePanel() {
  if (transcribeTimer) { window.clearTimeout(transcribeTimer); transcribeTimer = null; }
  retranscribing = false;
  const button = $("transcribe-button");
  button.disabled = false;
  $("retranslate-button").hidden = true;
  $("retranslate-button").disabled = false;
  $("transcribe-progress").hidden = true;
  $("transcribe-phase").textContent = "准备中…";
  $("transcribe-log").textContent = "";
  renderStepTrack(null);
}

function renderStepTrack(stage) {
  const active = stage ? Number(stage.step) || 0 : 0;
  document.querySelectorAll("#transcribe-steps .step").forEach((step) => {
    const order = Number(step.dataset.step);
    step.classList.toggle("active", order === active);
    step.classList.toggle("done", order < active);
  });
  const detail = $("transcribe-phase");
  if (stage && stage.detail) detail.textContent = stage.detail;
}

function resetTtsPanel() {
  if (ttsTimer) { window.clearTimeout(ttsTimer); ttsTimer = null; }
  $("tts-panel").hidden = true;
  $("tts-start").disabled = false;
  $("tts-progress").hidden = true;
  $("tts-log").textContent = "";
  $("tts-download").hidden = true;
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

  const canTranscribe = Boolean(data.can_transcribe);
  document.querySelector(".track-grid").hidden = canTranscribe;
  document.querySelector("#generate-button").hidden = canTranscribe;
  $("transcribe-offer").hidden = !canTranscribe;
  resetTranscribePanel();
  resetTtsPanel();

  $("tracks-panel").hidden = false;
  $("reader").hidden = true;
  setStatus(canTranscribe
    ? "这个视频没有字幕轨。如果是英文口播，可用语音识别生成双语字幕。"
    : `已找到 ${data.tracks.length} 条字幕轨，请确认中英文选择。`, canTranscribe ? "loading" : "success");
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
  $("download-srt").href = `/api/jobs/${state.jobId}/download/srt`;
  $("subtitle-search").value = "";
  $("no-match").hidden = true;
  $("reader").hidden = false;
  $("reader").scrollIntoView({ behavior: "smooth", block: "start" });
}

const TRANSCRIBE_PHASE_TEXT = {
  running: "识别中：下载音频 → Whisper 转写 → 机器翻译（约几分钟，请保持页面打开）",
  done: "识别完成",
  error: "识别失败",
};

async function startTranscribe() {
  const button = $("transcribe-button");
  const noTranslate = $("no-translate").checked;
  button.disabled = true;
  $("transcribe-progress").hidden = false;
  $("transcribe-phase").textContent = noTranslate
    ? "识别中：下载音频 → Whisper 转写（仅英文，约几分钟，请保持页面打开）"
    : TRANSCRIBE_PHASE_TEXT.running;
  $("transcribe-log").textContent = "正在启动识别任务…\n";
  try {
    await api(`/api/jobs/${state.jobId}/transcribe`, {
      browser: localStorage.getItem("bili-subtitle-browser") || "none",
      translate: !noTranslate,
    });
    transcribeTimer = window.setTimeout(pollTranscribe, 1500);
  } catch (error) {
    $("transcribe-phase").textContent = "启动失败";
    $("transcribe-log").textContent += `${error.message}\n`;
    button.disabled = false;
  }
}

async function startRetranslate() {
  const button = $("retranslate-button");
  button.disabled = true;
  retranscribing = true;
  $("transcribe-progress").hidden = false;
  $("transcribe-phase").textContent = "重试翻译中…";
  $("transcribe-log").textContent = "正在启动重试翻译（无需重跑语音识别）…\n";
  try {
    await api(`/api/jobs/${state.jobId}/retranslate`, {});
    transcribeTimer = window.setTimeout(pollTranscribe, 1000);
  } catch (error) {
    $("transcribe-phase").textContent = "重试翻译启动失败";
    $("transcribe-log").textContent += `${error.message}\n`;
    button.disabled = false;
  }
}

async function stopServer() {
  const confirmed = window.confirm(
    "确定停止服务？进行中的任务会中断。已完成的转写和成功译文会保留在本地缓存；未下载的 MP3 会丢失。");
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
  if (ttsTimer) { window.clearTimeout(ttsTimer); ttsTimer = null; }
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
      const emailStatus = data.translation_email_configured ? "MyMemory 邮箱已配置" : "MyMemory 未配置邮箱";
      $("server-started").textContent = `服务启动于 ${data.started_at} · ${emailStatus}`;
    }
  } catch { /* 健康检查失败不打扰页面 */ }
}

async function pollTranscribe() {
  let data = null;
  try {
    const response = await fetch(`/api/jobs/${state.jobId}/transcribe/status`);
    data = await response.json().catch(() => ({ ok: false, error: `HTTP ${response.status}` }));
    if (!response.ok || !data.ok) throw new Error(data.error || "查询进度失败");
    $("transcribe-phase").textContent = (retranscribing && data.phase === "running")
      ? "重试翻译中…"
      : TRANSCRIBE_PHASE_TEXT[data.phase] || data.phase;
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
      const translationMissing = Boolean(data.translation_missing);
      retranscribing = false;
      $("retranslate-button").hidden = !translationMissing;
      if (translationMissing) {
        setStatus("已有内容已保留，部分字幕尚未翻译；可稍后点『重试翻译』补齐缺失部分。", "error");
      } else {
        setStatus("语音识别完成，双语字幕已生成。", "success");
      }
      renderRows({
        rows: data.rows,
        count: data.count,
        notice: data.notice,
      });
      return;
    }
    if (data.phase === "error") {
      retranscribing = false;
      setStatus(`识别失败：${data.error}`, "error");
      $("transcribe-log").textContent += `${data.error}\n`;
    }
  } catch (error) {
    setStatus(error.message, "error");
    $("transcribe-log").textContent += `${error.message}\n`;
  } finally {
    if (!data || data.phase !== "running") {
      $("transcribe-button").disabled = false;
      $("retranslate-button").disabled = false;
    }
  }
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

function restoreForm() {
  const savedUrl = localStorage.getItem("bili-subtitle-url");
  const savedBrowser = localStorage.getItem("bili-subtitle-browser");
  if (savedUrl) $("video-url").value = savedUrl;
  if (["none", "edge", "chrome", "firefox"].includes(savedBrowser)) $("browser").value = savedBrowser;
}

$("inspect-form").addEventListener("submit", inspect);
$("generate-button").addEventListener("click", generate);
$("transcribe-button").addEventListener("click", startTranscribe);
$("retranslate-button").addEventListener("click", startRetranslate);
$("stop-server").addEventListener("click", stopServer);
$("subtitle-search").addEventListener("input", filterRows);
$("font-smaller").addEventListener("click", () => changeFont(-.1));
$("font-larger").addEventListener("click", () => changeFont(.1));
$("copy-md").addEventListener("click", copyMarkdown);
$("copy-en").addEventListener("click", copyEnglish);
$("save-raw-ch").addEventListener("click", saveRawChinese);
$("apply-align").addEventListener("click", applyAlignedResult);
$("to-top").addEventListener("click", () => $("reader").scrollIntoView({ behavior: "smooth" }));
$("tts-button").addEventListener("click", async () => {
  $("tts-panel").hidden = false;
  $("tts-panel").scrollIntoView({ behavior: "smooth", block: "start" });
  await loadTtsVoices();
});
$("tts-start").addEventListener("click", startTts);
restoreForm();
loadServerStarted();

async function loadTtsVoices() {
  const select = $("tts-voice");
  if (select.options.length) return;
  const hint = $("tts-hint");
  try {
    const response = await fetch("/api/tts/voices");
    const data = await response.json().catch(() => ({ ok: false }));
    if (!response.ok || !data.ok) throw new Error(data.error || `HTTP ${response.status}`);
    for (const voice of data.voices) {
      const option = document.createElement("option");
      option.value = voice.id;
      option.textContent = voice.label;
      select.append(option);
    }
    hint.hidden = true;
  } catch (error) {
    hint.hidden = false;
    hint.textContent = `语音列表加载失败：${error.message}`;
    $("tts-start").disabled = true;
  }
}

async function startTts() {
  const start = $("tts-start");
  start.disabled = true;
  $("tts-progress").hidden = false;
  $("tts-download").hidden = true;
  $("tts-phase").textContent = "正在启动合成…";
  $("tts-log").textContent = "";
  try {
    await api(`/api/jobs/${state.jobId}/tts`, {
      lang: $("tts-lang").value,
      voice: $("tts-voice").value,
      rate: Number($("tts-rate").value),
    });
    ttsTimer = window.setTimeout(pollTts, 1200);
  } catch (error) {
    $("tts-phase").textContent = "启动失败";
    $("tts-log").textContent = `${error.message}\n`;
    start.disabled = false;
  }
}

async function pollTts() {
  let data = null;
  try {
    const response = await fetch(`/api/jobs/${state.jobId}/tts/status`);
    data = await response.json().catch(() => ({ ok: false, error: `HTTP ${response.status}` }));
    if (!response.ok || !data.ok) throw new Error(data.error || "查询进度失败");
    if (data.phase === "running") {
      $("tts-phase").textContent = `合成中 · 第 ${data.done}/${data.total} 段`;
      if (data.log && data.log.length) {
        const logBox = $("tts-log");
        logBox.textContent = data.log.join("\n") + "\n";
        logBox.scrollTop = logBox.scrollHeight;
      }
      ttsTimer = window.setTimeout(pollTts, 2000);
      return;
    }
    if (data.phase === "done") {
      $("tts-phase").textContent = "合成完成";
      const download = $("tts-download");
      download.href = `/api/jobs/${state.jobId}/download/mp3`;
      download.hidden = false;
      return;
    }
    if (data.phase === "error") {
      $("tts-phase").textContent = "合成失败";
      $("tts-log").textContent += `${data.error}\n`;
    }
  } catch (error) {
    $("tts-phase").textContent = "查询失败";
    $("tts-log").textContent += `${error.message}\n`;
  } finally {
    if (!data || data.phase !== "running") $("tts-start").disabled = false;
  }
}
