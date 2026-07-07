# 音频播放器（audioplayer）

纯静态网页音频播放器：卡片网格书库 → 书本音频列表 → 底部常驻播放条。
靠 nginx `autoindex json` 自动发现书与音频，无后台进程。

## 本地开发

```bash
cd audioplayer
python dev_server.py 8000        # 浏览器打开 http://127.0.0.1:8000/
```

`dev_server.py` 把 `/books/` 映射到 `fixtures/books/`，并返回与 nginx 一致格式的目录 JSON。
要听到声音，把真实 mp3 放进 `fixtures/books/<某书>/` 替换占位空文件。

## 单元测试

```bash
cd audioplayer && node --test                 # core.js 纯逻辑
pytest audioplayer/tests/test_dev_server.py -v       # dev_server autoindex 格式
```

## 目录结构

- `index.html / app.js / style.css` —— 上线要传的 3 个文件
- `core.js` —— 纯逻辑（解析/排序/循环/倍速/渲染），单测覆盖
- `books/` —— 音频根目录（上线后由你创建并放书）
- `fixtures/` —— 本地测试假数据（不上线）
- `dev_server.py` —— 本地开发服务器（不上线）
- `nginx.conf.example` —— nginx 配置示例

## 部署到服务器（公网 47.108.230.162）

1. **上传 3 个前端文件**到 nginx 静态根下的某个目录（设为 `<script根>`）：

   ```bash
   scp index.html app.js style.css root@47.108.230.162:<script根>/
   ```

2. **创建音频根目录并放书**：

   ```bash
   ssh root@47.108.230.162 'mkdir -p <script根>/books'
   scp -r 剑桥雅思10 root@47.108.230.162:<script根>/books/
   ```

   每本书一个文件夹，里面是 `001.mp3`、`002.mp3`… 命名规律即可。

3. **配 nginx**：把 `nginx.conf.example` 里的 `/path/to/script-root/` 改成 `<script根>` 的实际路径，加进现有 `server { }` 块，然后：

   ```bash
   ssh root@47.108.230.162 'nginx -t && nginx -s reload'
   ```

4. **访问** `http://47.108.230.162/script/`。

## 加一本书

```bash
scp -r 新书名 root@47.108.230.162:<script根>/books/
```

刷新网页，新卡片自动出现。无需任何命令或脚本。
