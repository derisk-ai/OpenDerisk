#!/usr/bin/env python3
"""项目预览看板：本地 Web 服务，实时查看流水线进度、预览各阶段产出、提交反馈。

纯标准库实现（http.server），零第三方依赖。

用法：
  # 多项目模式（推荐）：自动扫描目录下所有项目，列表页点进去看
  python3 pv_dashboard.py [--root <扫描根>] [--depth 3] [--port 8620]
  # 单项目模式（兼容）：只看指定项目
  python3 pv_dashboard.py --dir <项目目录> [--port 8620] [--bind 127.0.0.1]

功能：
  /               多项目模式=项目列表页；单项目模式=看板页面
  /api/projects   项目列表 JSON（标题/模式/进度/待处理反馈/更新时间）
  /p/<slug>/      单个项目的看板页面（多项目模式）
  /api/status     全量状态 JSON（项目/阶段/分镜/验证/成本/反馈/产物）
  /api/feedback   POST 提交反馈（json: {stage, shot, content}）
  /files/<路径>   项目目录静态资源（音频/图片/片段/成片，防目录穿越）
  /page/<shot_id> webanim 动画页面实时回放版（注入回放驱动，不改动源文件）
  /libs/<name>.min.js  内置动画库（回放页注入的脚本依赖此路由）

反馈闭环：用户在看板提交反馈 → 写入 production.db(feedback 表) →
agent 用 `pv_db.py feedback-list --pending` 读取并处理 →
`pv_db.py feedback-resolve --id N` 标记完成 → 看板自动显示。

webanim 动画回放说明：模板页面是 __seek(t) 纯函数，静止在 t=0；
本服务在响应时注入 rAF 回放驱动（循环播放）。注入只发生在预览副本，
源文件保持确定性（不影响 weblint/渲染）。
"""
import argparse
import html
import json
import os
import re
import sys
import time
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pv_db
import pv_common

INJECT_REPLAY = """
<script>
/* lite-video dashboard 注入：动画回放驱动（仅预览副本，源文件不受影响） */
(function () {
  function start() {
    var s0 = null;
    function loop(ts) {
      if (s0 === null) s0 = ts;
      var D = window.__duration || 6;
      var t = ((ts - s0) / 1000) % D;
      if (typeof window.__seek === "function") { try { window.__seek(t); } catch (e) {} }
      requestAnimationFrame(loop);
    }
    requestAnimationFrame(loop);
  }
  /* 按容器宽度缩放固定画布页面，使整页在预览框内铺满可见（横/竖屏均按项目比例）*/
  function fit(){
    var bw=parseFloat(getComputedStyle(document.body).width)||1080;
    var iw=window.innerWidth||bw;
    if(iw>0&&bw>0){var s=iw/bw;document.body.style.transformOrigin="top left";
      document.body.style.transform="scale("+s+")";document.documentElement.style.overflow="hidden";}
  }
  /* 等待页面异步初始化（如 Mermaid 渲染、GSAP timeline 构建）*/
  Promise.resolve()
    .then(function () { if (typeof window.__ready === "function") return window.__ready(); })
    .catch(function () {})
    .then(function(){ fit(); window.addEventListener("resize",fit); start(); });
})();
</script>
"""

INDEX_HTML = r"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>lite-video 预览看板</title>
<style>
  :root{
    --bg:#070b14; --panel:rgba(18,25,42,.94); --panel2:#0e1524; --line:#223052;
    --txt:#e9effc; --mut:#8fa2c4; --acc:#5b8cff; --acc2:#22d3ee; --ok:#34d399;
    --warn:#fbbf24; --bad:#f87171; --pend:#c084fc;
    --mono:ui-monospace,Menlo,Consolas,monospace;
    --shadow:0 10px 30px rgba(0,0,0,.35);
  }
  *{box-sizing:border-box}
  body{margin:0;color:var(--txt);
    background:radial-gradient(1200px 500px at 80% -10%,#14204a55,transparent),
               radial-gradient(900px 400px at -10% 20%,#0d2c3a44,transparent),var(--bg);
    font:14px/1.6 -apple-system,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif}
  a{color:var(--acc)}
  .wrap{max-width:1560px;margin:0 auto;padding:18px}
  header{position:sticky;top:0;z-index:20;display:flex;flex-wrap:wrap;gap:10px;align-items:center;
    justify-content:space-between;padding:13px 20px;
    background:rgba(10,15,28,.82);backdrop-filter:blur(10px);
    border-bottom:1px solid var(--line)}
  header h1{font-size:17px;margin:0;display:flex;gap:10px;align-items:center;letter-spacing:.3px}
  .badges{display:flex;gap:8px;flex-wrap:wrap}
  .chip{padding:4px 11px;border-radius:20px;font-size:12px;background:#16203a;
    border:1px solid var(--line);color:var(--mut)}
  .chip b{color:var(--txt)}
  .chip.acc{background:linear-gradient(135deg,#1d3a75,#16305c);color:#cfe0ff;border-color:#2f5aa8}
  .chip.pend{background:#3a2350;color:#e9d5ff;border-color:#6b3fa0;cursor:pointer}
  /* 反馈横幅 */
  .banner{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin:14px 0 0;
    padding:11px 16px;border-radius:12px;border:1px solid #6b3fa0;
    background:linear-gradient(90deg,#33204dcc,#1d1533cc);font-size:13px}
  .banner .cmd{font-family:var(--mono);font-size:11px;color:#e9d5ff;background:#00000055;
    padding:3px 8px;border-radius:6px;word-break:break-all}
  .grid{display:grid;grid-template-columns:360px 1fr 340px;gap:14px;margin-top:14px}
  @media(max-width:1200px){.grid{grid-template-columns:1fr}}
  .col{display:flex;flex-direction:column;gap:14px;min-width:0}
  .card{background:var(--panel);border:1px solid var(--line);border-radius:14px;
    overflow:hidden;box-shadow:var(--shadow)}
  .card h2{margin:0;font-size:12px;font-weight:600;padding:11px 14px;background:var(--panel2);
    border-bottom:1px solid var(--line);color:var(--mut);letter-spacing:.6px;
    text-transform:uppercase;display:flex;justify-content:space-between;align-items:center;gap:8px}
  .card .bd{padding:12px 14px}
  /* 流水线 */
  .pipe{display:flex;flex-wrap:wrap;gap:8px;align-items:stretch}
  .stage{flex:1;min-width:118px;padding:10px 12px;border-radius:12px;background:var(--panel2);
    border:1px solid var(--line);position:relative;transition:border-color .15s}
  .stage.done{border-color:#1f5c40}
  .stage .nm{font-size:11px;color:var(--mut)}
  .stage .lb{font-size:14px;font-weight:600;margin-top:2px}
  .stage .st{font-size:11px;margin-top:6px;display:inline-block;padding:2px 9px;border-radius:10px}
  .st.pending{background:#232c44;color:var(--mut)}
  .st.in_progress{background:#33415e;color:#bcd4ff}
  .st.awaiting_human{background:#4a2b66;color:#e9d5ff}
  .st.completed{background:#123a2b;color:var(--ok)}
  .gate{position:absolute;top:8px;right:8px;font-size:10px;color:var(--warn)}
  /* 分镜卡片 */
  .shots{display:grid;grid-template-columns:repeat(auto-fill,minmax(235px,1fr));gap:12px}
  .shot{background:var(--panel2);border:1px solid var(--line);border-radius:14px;
    overflow:hidden;display:flex;flex-direction:column;transition:border-color .15s,transform .15s}
  .shot:hover{border-color:#31518f}
  .shot .ph{aspect-ratio:var(--shot-aspect,9/16);max-height:340px;background:#0a0e18;position:relative;
    display:flex;align-items:center;justify-content:center}
  .shot .ph iframe{width:100%;height:100%;border:0}
  .shot .ph img,.shot .ph video{width:100%;height:100%;object-fit:cover}
  .shot .empty{color:#3c4a6e;font-size:12px;text-align:center;padding:20px}
  .zoom{position:absolute;top:8px;right:8px;z-index:2;cursor:pointer;border:0;
    width:30px;height:30px;border-radius:9px;background:#00000099;color:#fff;font-size:15px;
    opacity:0;transition:opacity .15s}
  .shot .ph:hover .zoom{opacity:1}
  .shot .bt{padding:10px 12px;border-top:1px solid var(--line)}
  .shot .tt{font-size:13px;font-weight:700;display:flex;justify-content:space-between;align-items:center}
  .shot .tt .id{color:var(--mut);font-family:var(--mono);font-weight:400;font-size:12px}
  .shot .nr{font-size:12px;color:#b8c6e2;margin-top:6px;line-height:1.65;
    display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
  .shot.full .nr{-webkit-line-clamp:unset;display:block}
  .shot audio{width:100%;margin-top:8px;height:32px}
  .shot .brief{font-size:11px;color:#b9a4e0;margin-top:8px;line-height:1.6;
    border-top:1px dashed #2b2344;padding-top:7px;display:none}
  .shot.open .brief{display:block}
  .shot .tools{display:flex;gap:6px;margin-top:9px;flex-wrap:wrap}
  .btn{cursor:pointer;border:1px solid var(--line);background:#1b2438;color:var(--txt);
    border-radius:8px;padding:4px 10px;font-size:12px;transition:background .15s}
  .btn:hover{background:#263352}
  .btn.pri{background:linear-gradient(135deg,#3566e0,#2b5bd7);border-color:#3a6fe8;color:#fff}
  .btn.danger{background:#4a1c2a;border-color:#6b2c40;color:#ffd2dc}
  /* Markdown 文档排版 */
  .md{font-size:13px;line-height:1.75;color:#cfdaf0;word-break:break-word}
  .md h1{font-size:19px;margin:14px 0 8px;padding-bottom:6px;border-bottom:1px solid var(--line);color:#fff}
  .md h2{font-size:16px;margin:14px 0 7px;color:#dfe8fb;
    border-left:3px solid var(--acc);padding-left:9px}
  .md h3{font-size:14px;margin:12px 0 6px;color:#d5e0f5}
  .md h4,.md h5,.md h6{font-size:13px;margin:10px 0 5px;color:var(--mut)}
  .md p{margin:6px 0}
  .md ul,.md ol{margin:6px 0;padding-left:22px}
  .md li{margin:3px 0}
  .md strong{color:#fff}
  .md code{font-family:var(--mono);font-size:12px;background:#1a2340;color:#9fd0ff;
    padding:1px 6px;border-radius:5px}
  .md pre{background:#0a0f1e;border:1px solid #1c2742;border-radius:9px;padding:11px 13px;
    overflow:auto;margin:8px 0}
  .md pre code{background:none;padding:0;color:#c9d6ef}
  .md blockquote{margin:8px 0;padding:6px 13px;border-left:3px solid var(--pend);
    background:#1a1530;border-radius:0 8px 8px 0;color:#d9c9f2}
  .md table{border-collapse:collapse;margin:9px 0;width:100%;font-size:12px}
  .md th{background:#16203a;color:#bcd4ff;font-weight:600}
  .md td,.md th{border:1px solid #223052;padding:5px 9px;text-align:left}
  .md hr{border:0;border-top:1px solid var(--line);margin:12px 0}
  .md a{color:var(--acc2)}
  .doc-scroll{max-height:440px;overflow:auto;padding:10px 14px}
  .doc-scroll::-webkit-scrollbar,.md::-webkit-scrollbar{width:8px}
  .doc-scroll::-webkit-scrollbar-thumb,.md::-webkit-scrollbar-thumb{background:#26345a;border-radius:4px}
  details>summary{cursor:pointer;list-style:none;padding:10px 14px;color:var(--mut);
    font-size:13px;border-bottom:1px solid var(--line);display:flex;gap:6px;align-items:center}
  details>summary::-webkit-details-marker{display:none}
  details>summary::before{content:"▸";color:var(--acc)}
  details[open]>summary::before{content:"▾"}
  /* 列表 */
  table.lst{width:100%;border-collapse:collapse;font-size:12px}
  table.lst td,table.lst th{padding:6px 10px;text-align:left;border-bottom:1px solid #1c2742;vertical-align:top}
  table.lst th{color:var(--mut);font-weight:500}
  .pass{color:var(--ok)} .fail{color:var(--bad)}
  /* 反馈 */
  .fb{padding:10px 12px;border-bottom:1px solid #1c2742;font-size:12px}
  .fb .meta{color:var(--mut);font-size:11px;display:flex;justify-content:space-between;gap:6px}
  .fb .txt{margin-top:4px;line-height:1.6}
  .fb.pending{border-left:3px solid var(--pend);background:#1a153066}
  .fb.seen{border-left:3px solid var(--warn);background:#2a231066}
  .fb.fixed{border-left:3px solid var(--acc2);background:#0d2c3a44}
  .fb.resolved{border-left:3px solid var(--ok);opacity:.6}
  form.fbform{padding:12px 14px;display:flex;flex-direction:column;gap:8px}
  form.fbform select,form.fbform textarea{background:#0e1526;
    border:1px solid var(--line);color:var(--txt);border-radius:9px;padding:8px 10px;font-size:13px}
  form.fbform textarea{resize:vertical;min-height:60px;font-family:inherit}
  .hint{font-size:11px;color:var(--mut);line-height:1.7;padding:9px 14px;border-top:1px dashed var(--line)}
  .hint code{font-family:var(--mono);font-size:10.5px;background:#0a0f1e;color:#9fd0ff;
    padding:2px 6px;border-radius:5px;display:block;margin:4px 0;word-break:break-all}
  .toast{position:fixed;bottom:20px;left:50%;transform:translateX(-50%);
    background:#123a2b;color:var(--ok);padding:9px 18px;border-radius:10px;
    border:1px solid #1f5c40;opacity:0;pointer-events:none;transition:opacity .25s;z-index:99}
  .toast.show{opacity:1}
  .finalwrap{display:flex;justify-content:center;align-items:center;
    background:radial-gradient(circle at 50% 38%,#10182e,#05070f);padding:22px;border-radius:14px;
    position:relative;box-shadow:inset 0 0 0 1px var(--line)}
  .finalwrap::before{content:"";position:absolute;top:0;left:0;right:0;height:4px;
    background:linear-gradient(90deg,#3566e0,#06b6d4,#ec4899);opacity:.85;border-radius:14px 14px 0 0}
  .finalwrap video{max-height:70vh;max-width:100%;border-radius:10px;
    box-shadow:0 24px 64px rgba(0,0,0,.55);border:1px solid #243049;background:#000}
  /* 验证记录卡片：限高滚动，不再无限撑高 */
  #verify{max-height:300px;overflow:auto;border-radius:0 0 12px 12px}
  #verify table.lst th{position:sticky;top:0;background:var(--panel2);z-index:1}
  /* 分镜预览：多阶段媒体切换 tab */
  .mtabs{display:flex;gap:4px;padding:6px 8px 0;background:var(--panel2);flex-wrap:wrap}
  .mtab{cursor:pointer;border:1px solid var(--line);background:#16203a;color:var(--mut);
    border-radius:7px;padding:3px 9px;font-size:11px;transition:all .15s}
  .mtab.on{background:linear-gradient(135deg,#3566e0,#2b5bd7);color:#fff;border-color:#3a6fe8}
  .mlayer{position:absolute;inset:0;display:none}
  .mlayer.on{display:block}
  .lfrow{display:flex;align-items:center;gap:8px;margin-top:6px}
  .lfrow img{height:56px;border-radius:8px;border:1px solid var(--line);cursor:zoom-in}
  .mut{color:var(--mut)} .center{text-align:center;padding:30px;color:var(--mut)}
  .dot{width:8px;height:8px;border-radius:50%;background:var(--ok);display:inline-block;
    margin-right:5px;animation:pulse 2s infinite}
  @keyframes pulse{0%,100%{opacity:1}50%{opacity:.35}}
  /* 弹层：Lightbox / 阅读器 */
  .overlay{position:fixed;inset:0;background:rgba(3,6,12,.9);backdrop-filter:blur(6px);
    z-index:50;display:none;align-items:center;justify-content:center;flex-direction:column;padding:24px}
  .overlay.show{display:flex}
  .overlay .x{position:absolute;top:16px;right:20px;cursor:pointer;border:1px solid var(--line);
    background:#1b2438;color:var(--txt);border-radius:10px;padding:6px 14px;font-size:13px}
  .overlay .ttl{color:var(--mut);font-size:13px;margin-bottom:12px}
  #lb-media{max-width:min(1200px,94vw);max-height:82vh;display:flex;align-items:center;justify-content:center}
  #lb-media img{max-width:100%;max-height:82vh;border-radius:10px}
  #lb-media video{max-width:100%;max-height:82vh;border-radius:10px}
  #lb-media iframe{aspect-ratio:var(--shot-aspect,9/16);height:80vh;max-width:94vw;width:auto;border:0;border-radius:12px;background:#fff}
  #reader{background:rgba(3,6,12,.94)}
  #reader .sheet{width:min(860px,94vw);max-height:88vh;overflow:auto;background:var(--panel);
    border:1px solid var(--line);border-radius:16px;padding:26px 34px;box-shadow:var(--shadow)}
  #reader .sheet .md{font-size:14px}
</style>
</head>
<body>
<header>
  <h1><span class="dot" id="live"></span>🎬 lite-video 预览看板 <span class="mut" id="proj-title"></span></h1>
  <div class="badges" id="badges"></div>
</header>
<div class="wrap">
  <div class="banner" id="fbbanner" style="display:none">
    <span>⏳ <b id="fbbanner-n"></b> 条待处理反馈，等待 agent 读取处理</span>
    <span class="cmd" id="fbbanner-cmd"></span>
    <button class="btn" onclick="copyAgentCmd()">复制命令</button>
  </div>
  <div class="card"><h2>流水线进度 <span class="mut" id="auto"></span></h2>
    <div class="bd"><div class="pipe" id="pipe"></div></div></div>
  <div class="card" id="finalcard" style="display:none">
    <h2>🎬 成片预览（compose 阶段交付）<span class="mut" id="finalinfo"></span></h2>
    <div class="bd finalwrap"><video id="finalvideo" controls preload="metadata"></video></div>
  </div>
  <div class="grid">
    <!-- 左：剧本文档 -->
    <div class="col" id="leftcol"></div>
    <!-- 中：分镜 -->
    <div class="col">
      <div class="card"><h2>分镜产出预览 <span class="mut" id="shotcount"></span></h2>
        <div class="bd"><div class="shots" id="shots"></div></div></div>
    </div>
    <!-- 右：验证/成本/反馈 -->
    <div class="col">
      <div class="card"><h2>提交反馈</h2>
        <form class="fbform" id="fbform">
          <select id="fb-stage"><option value="">（全局/剧本阶段）</option></select>
          <select id="fb-shot"><option value="">（不分镜）</option></select>
          <textarea id="fb-content" placeholder="写下你的修改意见或建议…"></textarea>
          <button class="btn pri" type="submit">提交反馈</button>
        </form>
        <div class="hint">📌 提交后写入生产库，agent 在下一轮执行前必须读取并处理：
          <code>python3 scripts/pv_db.py feedback-list --dir &lt;项目目录&gt; --pending</code>
          处理完成后标记：<code>python3 scripts/pv_db.py feedback-resolve --dir &lt;项目目录&gt; --id &lt;N&gt;</code>
        </div>
      </div>
      <div class="card"><h2>反馈列表 <span class="mut" id="fbcount"></span></h2><div id="fblist"></div></div>
      <div class="card"><h2>验证记录</h2><div class="bd" id="verify" style="padding:0"></div></div>
      <div class="card"><h2>成本 <span class="mut" id="costsum"></span></h2><div class="bd" id="costlist"></div></div>
    </div>
  </div>
</div>
<!-- Lightbox：分镜视觉放大 -->
<div class="overlay" id="lightbox" onclick="if(event.target===this)closeLb()">
  <button class="x" onclick="closeLb()">✕ 关闭 (Esc)</button>
  <div class="ttl" id="lb-ttl"></div>
  <div id="lb-media"></div>
</div>
<!-- 阅读器：文档全屏 -->
<div class="overlay" id="reader" onclick="if(event.target===this)closeReader()">
  <button class="x" onclick="closeReader()">✕ 关闭 (Esc)</button>
  <div class="sheet" id="reader-sheet"></div>
</div>
<div class="toast" id="toast"></div>
<script>
const BASE=__BASE__;
let STATUS=null;
const SHOT_FP={}, DOC_OPEN={}, SHOT_MEDIA={};
function $(s){return document.querySelector(s)}
function esc(s){return String(s==null?"":s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]))}
function toast(m){const t=$("#toast");t.textContent=m;t.classList.add("show");
  setTimeout(()=>t.classList.remove("show"),2200)}
function rel(p){ if(!p)return ""; const root=STATUS.project_dir;
  return p.startsWith(root)?p.slice(root.length).replace(/^\//,""):p }
function fmtDur(s){ s=Math.round(s); return Math.floor(s/60)+":"+String(s%60).padStart(2,"0") }
/* 用户交互保护：反馈输入框聚焦 或 弹层打开 时不整页重建 */
function userBusy(){ return document.activeElement===$("#fb-content") }

/* ---------- Markdown 渲染（纯前端，无依赖）---------- */
function mdInline(s){
  return s.replace(/\*\*([^*]+)\*\*/g,"<strong>$1</strong>")
    .replace(/(^|[^*])\*([^*\n]+)\*(?!\*)/g,"$1<em>$2</em>")
    .replace(/`([^`]+)`/g,"<code>$1</code>")
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g,'<a href="$2" target="_blank" rel="noopener">$1</a>');
}
function md2html(src){
  const lines=String(src).split(/\r?\n/); let out=[],i=0,inCode=false,buf=[],list=null;
  const flushList=()=>{if(list){out.push("</"+list+">");list=null}};
  while(i<lines.length){
    const ln=lines[i];
    if(/^```/.test(ln)){ if(inCode){out.push("<pre><code>"+esc(buf.join("\n"))+"</code></pre>");buf=[];inCode=false}
      else{flushList();inCode=true} i++;continue }
    if(inCode){buf.push(ln);i++;continue}
    if(/^\s*$/.test(ln)){flushList();i++;continue}
    let m;
    if(m=ln.match(/^(#{1,6})\s+(.*)/)){flushList();const h=m[1].length;
      out.push("<h"+h+">"+mdInline(esc(m[2]))+"</h"+h+">");i++;continue}
    if(/^(-{3,}|\*{3,})\s*$/.test(ln)){flushList();out.push("<hr>");i++;continue}
    if(m=ln.match(/^>\s?(.*)/)){flushList();out.push("<blockquote>"+mdInline(esc(m[1]))+"</blockquote>");i++;continue}
    /* 表格：当前行含 | 且下一行是分隔行 */
    if(ln.includes("|") && i+1<lines.length && /^\s*\|?[\s:|-]+\|?\s*$/.test(lines[i+1]) && lines[i+1].includes("-")){
      flushList();
      const cells=r=>r.replace(/^\||\|\s*$/g,"").split("|").map(c=>mdInline(esc(c.trim())));
      let t="<table><tr>"+cells(ln).map(c=>"<th>"+c+"</th>").join("")+"</tr>";
      i+=2;
      while(i<lines.length && lines[i].includes("|")){t+="<tr>"+cells(lines[i]).map(c=>"<td>"+c+"</td>").join("")+"</tr>";i++}
      out.push(t+"</table>");continue}
    if(m=ln.match(/^\s*[-*+]\s+(.*)/)){ if(list!=="ul"){flushList();out.push("<ul>");list="ul"}
      out.push("<li>"+mdInline(esc(m[1]))+"</li>");i++;continue}
    if(m=ln.match(/^\s*\d+[.)]\s+(.*)/)){ if(list!=="ol"){flushList();out.push("<ol>");list="ol"}
      out.push("<li>"+mdInline(esc(m[1]))+"</li>");i++;continue}
    flushList();out.push("<p>"+mdInline(esc(ln))+"</p>");i++;
  }
  if(inCode)out.push("<pre><code>"+esc(buf.join("\n"))+"</code></pre>");
  flushList();return out.join("\n");
}

/* ---------- 渲染 ---------- */
function renderHead(){
  const p=STATUS.project;
  document.documentElement.style.setProperty("--shot-aspect",(p.width||1080)+"/"+(p.height||1920));
  $("#proj-title").textContent="· "+(p.title||p.topic||"");
  const mode={imageflow:"图文模式",fullvideo:"全视频模式",webanim:"Web动画模式"}[p.mode]||p.mode;
  let b=`<span class="chip acc">${mode}</span>`;
  b+=`<span class="chip">${p.width}×${p.height}</span>`;
  if(p.total_duration)b+=`<span class="chip">总时长 <b>${fmtDur(p.total_duration)}</b></span>`;
  if(STATUS.total_cost.amount>0)b+=`<span class="chip">成本 <b>${STATUS.total_cost.amount.toFixed(3)} ${STATUS.total_cost.currency}</b></span>`;
  if(STATUS.pending_feedback>0)b+=`<span class="chip pend" onclick="document.getElementById('fb-content').focus()">⏳ ${STATUS.pending_feedback} 条待处理反馈</span>`;
  b+=`<span class="chip">阶段 <b>${STATUS.stages.filter(s=>s.status==="completed").length}/${STATUS.stages.length}</b></span>`;
  $("#badges").innerHTML=b;
  /* 反馈横幅：提醒 agent 读取（闭环）*/
  const banner=$("#fbbanner");
  if(STATUS.pending_feedback>0){
    banner.style.display="";
    $("#fbbanner-n").textContent=STATUS.pending_feedback;
    $("#fbbanner-cmd").textContent="python3 scripts/pv_db.py feedback-list --dir "+STATUS.project_dir+" --pending";
  }else banner.style.display="none";
}
function renderFinal(){
  const p=STATUS.project;
  const card=$("#finalcard");
  if(p.final_video_path){
    card.style.display="";
    $("#finalinfo").textContent=(p.total_duration?fmtDur(p.total_duration)+" · ":"")+rel(p.final_video_path);
    const v=$("#finalvideo"), src=BASE+"files/"+rel(p.final_video_path);
    if(v.getAttribute("src")!==src) v.src=src;
  }else{
    card.style.display="none";
  }
}
function renderPipe(){
  const mark={pending:"○",in_progress:"◐",awaiting_human:"⏸",completed:"✓"};
  $("#pipe").innerHTML=STATUS.stages.map(s=>`
    <div class="stage ${s.status==="completed"?"done":""}">
      ${s.gated?'<span class="gate">🔒门控</span>':''}
      <div class="nm">${mark[s.status]||""} 第 ${s.seq+1} 阶段</div>
      <div class="lb">${s.name}</div>
      <span class="st ${s.status}">${({pending:"待开始",in_progress:"进行中",awaiting_human:"待审批",completed:"已完成"})[s.status]||s.status}</span>
    </div>`).join("");
}
/* 分镜卡片指纹：数据未变则保留 DOM（保住展开/播放状态）*/
function shotFp(s){return JSON.stringify([s.narration,s.duration,s.audio_path,s.video_segment_path,
  s.web_page_path,s.image_path,s.first_frame_path,s.last_frame_path,s.tts_text,s.animation_brief])}
function buildShot(s){
  const M=[];
  if(s.web_page_path) M.push(["page","动画",`<iframe src="${BASE}page/${s.id}" loading="lazy" title="动画回放"></iframe>`]);
  if(s.video_segment_path) M.push(["video","片段",`<video src="${BASE}files/${rel(s.video_segment_path)}" controls preload="none" muted></video>`]);
  if(s.image_path) M.push(["image","配图",`<img src="${BASE}files/${rel(s.image_path)}" loading="lazy">`]);
  if(s.first_frame_path) M.push(["first","首帧",`<img src="${BASE}files/${rel(s.first_frame_path)}" loading="lazy">`]);
  if(s.last_frame_path) M.push(["last","尾帧",`<img src="${BASE}files/${rel(s.last_frame_path)}" loading="lazy">`]);
  // 默认显示当前阶段最新产出(最高优先)；用户手动切换后记住选择
  let act=SHOT_MEDIA[s.id];
  if(act && !M.some(m=>m[0]===act)) act=null;
  if(!act && M.length) act=M[0][0];
  const tabs=M.length>1?`<div class="mtabs">${M.map(m=>`<button class="mtab ${m[0]===act?'on':''}" data-mtype="${m[0]}" onclick="setShotMedia(${s.id},'${m[0]}')">${m[1]}</button>`).join("")}</div>`:"";
  const layers=M.length?M.map(m=>`<div class="mlayer ${m[0]===act?'on':''}" data-media="${m[0]}">${m[2]}</div>`).join(""):`<div class="empty">该镜暂无视觉产出</div>`;
  const zoomable=M.length>0;
  const dur=s.duration?fmtDur(s.duration):"—";
  const hasBrief=s.animation_brief||s.tts_text;
  const el=document.createElement("div");
  el.className="shot"; el.dataset.id=s.id;
  el.innerHTML=`
    ${tabs}
    <div class="ph">${layers}
      ${zoomable?`<button class="zoom" title="放大查看当前媒体" onclick="openLb(${s.id})">🔍</button>`:""}
    </div>
    <div class="bt">
      <div class="tt"><span>#${String(s.id).padStart(2,"0")}</span><span class="id">${dur}</span></div>
      <div class="nr">${esc(s.narration||"")}</div>
      ${hasBrief?`<div class="brief">${s.tts_text?`<div class="mut">朗读: ${esc(s.tts_text)}</div>`:""}${s.animation_brief?`<div>动画: ${esc(s.animation_brief)}</div>`:""}</div>`:""}
      <div class="tools">
        ${hasBrief?`<button class="btn" onclick="this.closest('.shot').classList.toggle('open')">详情</button>`:""}
        <button class="btn" onclick="this.closest('.shot').classList.toggle('full')">展开全文</button>
        <button class="btn" onclick="quickFb(${s.id})">反馈</button>
      </div>
      ${s.audio_path?`<audio src="${BASE}files/${rel(s.audio_path)}" controls preload="none"></audio>`:""}
    </div>`;
  return el;
}
function setShotMedia(id,type){
  SHOT_MEDIA[id]=type;
  const card=document.querySelector(`.shot[data-id="${id}"]`); if(!card)return;
  card.querySelectorAll(".mtab").forEach(b=>b.classList.toggle("on", b.dataset.mtype===type));
  card.querySelectorAll(".mlayer").forEach(l=>l.classList.toggle("on", l.dataset.media===type));
}
function renderShots(){
  const sh=STATUS.shots||[];
  $("#shotcount").textContent=sh.length+" 镜 · "+sh.filter(s=>s.video_segment_path).length+" 已出片段";
  const box=$("#shots");
  if(!sh.length){box.innerHTML='<div class="center">尚无分镜</div>';return}
  if(box.querySelector(".center"))box.innerHTML="";
  const exist={}; box.querySelectorAll(".shot").forEach(n=>exist[n.dataset.id]=n);
  sh.forEach((s,i)=>{
    const fp=shotFp(s), key=String(s.id);
    let node=exist[key];
    if(node && SHOT_FP[key]===fp){ delete exist[key]; }       /* 未变化：原样保留 */
    else{ const nn=buildShot(s); if(node) box.replaceChild(nn,node); else box.appendChild(nn);
      SHOT_FP[key]=fp; delete exist[key]; node=nn; }
    /* 保证顺序 */
    if(box.children[i]!==node) box.insertBefore(node, box.children[i]||null);
  });
  Object.values(exist).forEach(n=>n.remove());
}
function docCard(key,title,body,opened){
  return `<div class="card"><details ${opened?"open":""} data-doc="${key}">
    <summary>${title} <span class="mut" style="margin-left:auto;font-size:11px">
      <button class="btn" style="padding:1px 8px" onclick="event.preventDefault();openReader('${key}')">⛶ 全屏阅读</button></span></summary>
    <div class="doc-scroll md">${md2html(body)}</div></details></div>`;
}
let DOC_FP=null;
function renderDocs(){
  const ex=STATUS.extra||{}; const L=$("#leftcol");
  const fp=JSON.stringify([ex.script_md||"",ex.plan_md||"",(STATUS.decision_log||[]).length]);
  if(fp===DOC_FP && L.querySelector(".card")) return;   /* 内容未变：不重建，保住滚动位置 */
  DOC_FP=fp;
  let h="";
  if(ex.script_md!==undefined) DOC_OPEN.script=DOC_OPEN.script===undefined?true:DOC_OPEN.script;
  if(ex.script_md!==undefined) h+=docCard("script","📖 剧本 script.md",ex.script_md,DOC_OPEN.script);
  if(ex.plan_md!==undefined) h+=docCard("plan","🗂 计划 plan.md",ex.plan_md,!!DOC_OPEN.plan);
  const dl=STATUS.decision_log||[];
  if(dl.length) h+=docCard("log","🧭 决策日志 ("+dl.length+")",dl.map(d=>`**[${d.stage||"-"}]** ${d.content}`).join("\n\n"),!!DOC_OPEN.log);
  if(!h) h='<div class="card"><div class="center">剧本/计划文档将在阶段 1-2 产出后出现</div></div>';
  L.innerHTML=h;
  L.querySelectorAll("details[data-doc]").forEach(d=>{
    const k=d.dataset.doc;
    d.addEventListener("toggle",()=>{DOC_OPEN[k]=d.open});
  });
}
function openReader(key){
  const ex=STATUS.extra||{};
  const src={script:ex.script_md,plan:ex.plan_md,log:(STATUS.decision_log||[]).map(d=>`**[${d.stage||"-"}]** ${d.content}`).join("\n\n")}[key]||"";
  const title={script:"剧本 script.md",plan:"计划 plan.md",log:"决策日志"}[key]||"";
  $("#reader-sheet").innerHTML=`<div class="md"><h1>${title}</h1>${md2html(src)}</div>`;
  $("#reader").classList.add("show");
}
function closeReader(){$("#reader").classList.remove("show")}
function renderVerify(){
  const v=(STATUS.verifications||[]).slice(0,60);
  $("#verify").innerHTML=v.length?`<table class="lst"><tr><th>阶段</th><th>检查</th><th>结果</th></tr>${
    v.map(r=>`<tr><td>${r.stage}</td><td class="mut">${esc(r.check_name)}</td>
      <td class="${r.passed?'pass':'fail'}">${r.passed?'✓':'✗'} <span class="mut">${esc((r.evidence||"").slice(0,34))}</span></td></tr>`).join("")
  }</table>`:'<div class="center">暂无验证记录</div>';
}
function renderCost(){
  const c=STATUS.costs||[];
  $("#costsum").textContent=STATUS.total_cost.amount>0?STATUS.total_cost.amount.toFixed(3)+" "+STATUS.total_cost.currency:"";
  $("#costlist").innerHTML=c.length?`<table class="lst">${c.map(r=>`<tr><td>${r.stage||"-"}</td><td>${esc(r.item)}</td><td>${r.cost} ${r.currency}</td></tr>`).join("")}</table>`
    :'<div class="center mut">暂无成本记录</div>';
}
function renderFb(){
  const f=STATUS.feedback||[];
  $("#fbcount").textContent=f.length+" 条 · "+STATUS.pending_feedback+" 待处理";
  $("#fblist").innerHTML=f.length?f.map(x=>`
    <div class="fb ${x.status}">
      <div class="meta"><span>[${x.stage||"全局"}]${x.shot_id?"/shot_"+String(x.shot_id).padStart(2,"0"):""}</span>
        <span>${x.created_at||""}</span></div>
      <div class="txt">${esc(x.content)}</div>
      ${x.fix_reason?`<div class="mut" style="font-size:11px;margin-top:3px">已修复：${esc(x.fix_reason)}</div>`:""}
      <div class="tools" style="margin-top:6px">
        <span class="tag ${x.status==='pending'?'p':x.status==='seen'?'pend':x.status==='fixed'?'':'p'}"
          style="${(x.status==='resolved')?'opacity:.6':''}">${{pending:'新',seen:'已读·待修复',fixed:'已修复待确认',resolved:'已解决'}[x.status]||x.status}</span>
        ${x.status==="fixed"?`<button class="btn" onclick="resolveFb(${x.id})">确认已解决</button>`:""}
      </div>
    </div>`).join(""):'<div class="center mut">暂无反馈</div>';
}
function fillSelects(){
  if(userBusy())return;   /* 正在输入反馈时不重绘表单 */
  const st=$("#fb-stage"), sh=$("#fb-shot");
  const curStage=st.value, curShot=sh.value;
  st.innerHTML='<option value="">（全局/剧本阶段）</option>'+STATUS.stages.map(s=>`<option value="${s.name}">${s.seq+1}. ${s.name}</option>`).join("");
  sh.innerHTML='<option value="">（不分镜）</option>'+(STATUS.shots||[]).map(s=>`<option value="${s.id}">shot_${String(s.id).padStart(2,"0")}</option>`).join("");
  st.value=curStage; sh.value=curShot;
}
function quickFb(id){ $("#fb-shot").value=id; $("#fb-content").focus(); window.scrollTo({top:0,behavior:"smooth"}); toast("已选中 shot_"+String(id).padStart(2,"0")+",请填写反馈")}
async function resolveFb(id){ await fetch(BASE+"api/feedback/resolve",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({id})}); toast("已标记处理"); refresh(); }
function copyAgentCmd(){
  const t=$("#fbbanner-cmd").textContent;
  (navigator.clipboard?navigator.clipboard.writeText(t):Promise.reject()).then(()=>toast("已复制 agent 读取命令"))
    .catch(()=>{const ta=document.createElement("textarea");ta.value=t;document.body.appendChild(ta);ta.select();document.execCommand("copy");ta.remove();toast("已复制")});
}

/* ---------- Lightbox：分镜视觉放大 ---------- */
function openLb(shotId){
  const s=(STATUS.shots||[]).find(x=>x.id===shotId); if(!s)return;
  const t=SHOT_MEDIA[shotId];
  let html="",ttl="shot_"+String(shotId).padStart(2,"0");
  if(t==="page"||(!t&&s.web_page_path)){html=`<iframe src="${BASE}page/${s.id}"></iframe>`;ttl+=" · 动画回放"}
  else if(t==="video"||(!t&&s.video_segment_path)){html=`<video src="${BASE}files/${rel(s.video_segment_path)}" controls autoplay muted loop></video>`;ttl+=" · 视频片段"}
  else if(t==="image"||(!t&&s.image_path)){html=`<img src="${BASE}files/${rel(s.image_path)}">`;ttl+=" · 配图"}
  else if(t==="first"||(!t&&s.first_frame_path)){html=`<img src="${BASE}files/${rel(s.first_frame_path)}">`;ttl+=" · 首帧"}
  else if(t==="last"||s.last_frame_path){html=`<img src="${BASE}files/${rel(s.last_frame_path)}">`;ttl+=" · 尾帧"}
  $("#lb-ttl").textContent=ttl;
  $("#lb-media").innerHTML=html;
  $("#lightbox").classList.add("show");
}
function openLbImg(src,ttl){$("#lb-ttl").textContent=ttl;$("#lb-media").innerHTML=`<img src="${src}">`;$("#lightbox").classList.add("show")}
function closeLb(){$("#lightbox").classList.remove("show");$("#lb-media").innerHTML=""}
document.addEventListener("keydown",e=>{if(e.key==="Escape"){closeLb();closeReader()}});

$("#fbform").addEventListener("submit",async e=>{
  e.preventDefault();
  const content=$("#fb-content").value.trim();
  if(!content){toast("请填写反馈内容");return}
  const body={stage:$("#fb-stage").value,shot:parseInt($("#fb-shot").value)||0,content};
  const r=await fetch(BASE+"api/feedback",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
  const d=await r.json();
  if(d.ok){$("#fb-content").value="";toast("反馈已提交 #"+d.id+"，agent 会在下一轮读取处理");refresh()}else{toast(d.error||"提交失败")}
});

/* ---------- 轮询：拉全量 JSON，分块增量更新 ---------- */
async function refresh(){
  try{
    const r=await fetch(BASE+"api/status"); const data=await r.json();
    if(data.error)throw new Error(data.error);
    STATUS=data;
    renderHead();renderPipe();renderFinal();
    renderShots();          /* 内部按指纹 diff，未变化的卡片不重建 */
    renderDocs();renderVerify();renderCost();renderFb();fillSelects();
    $("#auto").textContent="增量同步 · "+new Date().toLocaleTimeString();
  }catch(e){ $("#auto").textContent="刷新失败: "+e.message }
}
refresh(); setInterval(refresh,2000);
</script>
</body>
</html>"""

LIST_HTML = r"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>lite-video 项目列表</title>
<style>
  :root{--bg:#0b0f1a;--panel:#131a2b;--panel2:#0f1524;--line:#223052;
    --txt:#e7eefc;--mut:#8fa2c4;--acc:#4f8cff;--ok:#2fd08a;--pend:#c084fc}
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--txt);
    font:14px/1.55 -apple-system,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif}
  header{display:flex;flex-wrap:wrap;gap:10px;align-items:center;justify-content:space-between;
    padding:14px 18px;background:linear-gradient(90deg,#101a33,#0d1424);border-bottom:1px solid var(--line)}
  header h1{font-size:17px;margin:0}
  .wrap{max-width:1100px;margin:0 auto;padding:20px 18px}
  .mut{color:var(--mut)}
  .proj{display:flex;align-items:center;gap:14px;background:var(--panel);
    border:1px solid var(--line);border-radius:12px;padding:14px 16px;margin-bottom:12px;
    text-decoration:none;color:var(--txt);transition:border-color .15s,transform .15s}
  .proj:hover{border-color:var(--acc);transform:translateY(-1px)}
  .proj .ic{font-size:26px;width:44px;height:44px;border-radius:10px;background:var(--panel2);
    display:flex;align-items:center;justify-content:center;flex:none}
  .proj .nm{font-size:15px;font-weight:600}
  .proj .meta{font-size:12px;color:var(--mut);margin-top:3px;display:flex;gap:10px;flex-wrap:wrap}
  .proj .right{margin-left:auto;text-align:right;flex:none}
  .bar{width:140px;height:6px;border-radius:3px;background:#1c2742;overflow:hidden;margin:4px 0 0 auto}
  .bar i{display:block;height:100%;background:var(--ok)}
  .tag{display:inline-block;padding:1px 8px;border-radius:10px;font-size:11px;background:#1c2742;border:1px solid var(--line)}
  .tag.final{background:#123a2b;color:var(--ok)}
  .tag.pend{background:#3a2350;color:#e9d5ff;border-color:#6b3fa0}
  .empty{text-align:center;color:var(--mut);padding:60px 20px}
  .empty code{background:var(--panel2);padding:2px 8px;border-radius:6px}
</style>
</head>
<body>
<header><h1>🎬 lite-video 预览看板</h1><span class="mut" id="cnt"></span></header>
<div class="wrap" id="list"><div class="empty">加载中…</div></div>
<script>
function esc(s){return String(s==null?"":s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]))}
async function refresh(){
  try{
    const r=await fetch("/api/projects"); const ps=await r.json();
    document.getElementById("cnt").textContent=ps.length+" 个项目 · 每 3s 自动刷新";
    const el=document.getElementById("list");
    if(!ps.length){el.innerHTML='<div class="empty">扫描根下暂无项目（含 production.db 的目录会被识别）</div>';return}
    el.innerHTML=ps.map(p=>{
      const pct=p.total?Math.round(p.done/p.total*100):0;
      const icon=p.final?"🎬":(p.done?"📦":"🎞");
      return `<a class="proj" href="/p/${encodeURIComponent(p.slug)}/">
        <div class="ic">${icon}</div>
        <div style="min-width:0">
          <div class="nm">${esc(p.title)}</div>
          <div class="meta"><span>${p.mode}</span><span>${p.shots} 镜</span>
            <span class="mut">${esc(p.path)}</span><span class="mut">${p.updated}</span></div>
        </div>
        <div class="right">
          ${p.final?'<span class="tag final">已出成片</span>':""}
          ${p.pending_feedback?`<span class="tag pend">⏳ ${p.pending_feedback} 待反馈</span>`:""}
          <span class="tag">${p.done}/${p.total} 阶段</span>
          <div class="bar"><i style="width:${pct}%"></i></div>
        </div>
      </a>`;
    }).join("");
  }catch(e){document.getElementById("list").innerHTML='<div class="empty">加载失败: '+esc(e.message)+'</div>'}
}
refresh(); setInterval(refresh,3000);
</script>
</body>
</html>"""

MIME = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".gif": "image/gif", ".svg": "image/svg+xml",
    ".mp3": "audio/mpeg", ".wav": "audio/wav", ".m4a": "audio/mp4",
    ".mp4": "video/mp4", ".webm": "video/webm",
    ".txt": "text/plain; charset=utf-8", ".md": "text/plain; charset=utf-8",
    ".srt": "text/plain; charset=utf-8", ".ass": "text/plain; charset=utf-8",
}


def scan_projects(root, depth=3):
    """递归扫描 root 下含 production.db 的目录，返回 {slug: realpath}。
    命中后不再下钻（项目目录内部不视为独立项目）。"""
    found = {}
    root = os.path.abspath(root)
    db_name = pv_db.DB_NAME

    def walk(d, level):
        if level > depth:
            return
        try:
            entries = sorted(os.listdir(d))
        except OSError:
            return
        if db_name in entries and os.path.isfile(os.path.join(d, db_name)):
            rp = os.path.realpath(d)
            rel = os.path.relpath(rp, os.path.realpath(root))
            slug = rel.replace(os.sep, "_") if rel != "." else os.path.basename(rp)
            found[slug] = rp
            return
        for name in entries:
            if name.startswith("."):
                continue
            sub = os.path.join(d, name)
            if os.path.isdir(sub) and not os.path.islink(sub):
                walk(sub, level + 1)

    walk(root, 0)
    return found


def list_projects(projects):
    """为列表页汇总每个项目的概要信息。"""
    mode_zh = {"imageflow": "图文", "fullvideo": "全视频", "webanim": "Web动画"}
    out = []
    for slug, real in sorted(projects.items()):
        info = {"slug": slug, "path": real, "title": os.path.basename(real),
                "mode": "-", "done": 0, "total": 0, "shots": 0,
                "pending_feedback": 0, "final": False, "updated": ""}
        try:
            conn = pv_db.connect(real)
            try:
                row = conn.execute(
                    "SELECT title, topic, mode FROM projects ORDER BY id LIMIT 1").fetchone()
                if row:
                    info["title"] = row["title"] or row["topic"] or info["title"]
                    info["mode"] = mode_zh.get(row["mode"], row["mode"] or "-")
                st = conn.execute("SELECT status FROM stages ORDER BY seq").fetchall()
                info["total"] = len(st)
                info["done"] = sum(1 for r in st if r["status"] == "completed")
                info["shots"] = conn.execute("SELECT COUNT(*) c FROM shots").fetchone()["c"]
                try:
                    info["pending_feedback"] = conn.execute(
                        "SELECT COUNT(*) c FROM feedback WHERE status='pending'"
                    ).fetchone()["c"]
                except Exception:
                    pass
                fv = conn.execute(
                    "SELECT final_video_path FROM projects ORDER BY id LIMIT 1").fetchone()
                info["final"] = bool(fv and fv["final_video_path"])
            finally:
                conn.close()
        except Exception:  # noqa: BLE001
            pass
        try:
            info["updated"] = time.strftime(
                "%Y-%m-%d %H:%M",
                time.localtime(os.path.getmtime(os.path.join(real, pv_db.DB_NAME))))
        except OSError:
            pass
        out.append(info)
    return out


def build_status(project_dir, project_real=None):
    """汇总状态库全量数据为可 JSON 序列化结构。"""
    conn = pv_db.connect(project_dir)
    try:
        pr = dict(conn.execute("SELECT * FROM projects ORDER BY id LIMIT 1").fetchone())
        pr.setdefault("mode", "imageflow")
        stages = [dict(r) for r in conn.execute("SELECT * FROM stages ORDER BY seq")]
        shots = []
        for r in conn.execute("SELECT * FROM shots ORDER BY id"):
            d = dict(r)
            for k in ("first_frame_path", "last_frame_path", "web_page_path",
                      "tts_text", "animation_brief"):
                d.setdefault(k, None)
            shots.append(d)
        vers = [dict(r) for r in conn.execute(
            "SELECT * FROM verifications ORDER BY id DESC LIMIT 200")]
        costs = [dict(r) for r in conn.execute("SELECT * FROM costs ORDER BY id")]
        try:
            fbs = [dict(r) for r in conn.execute("SELECT * FROM feedback ORDER BY id DESC")]
        except Exception:
            fbs = []
        arts = [dict(r) for r in conn.execute("SELECT * FROM artifacts ORDER BY id")]
        logs = [dict(r) for r in conn.execute(
            "SELECT * FROM decision_log ORDER BY id DESC LIMIT 50")]
        # 剧本文档（若存在）
        extra = {}
        for name in ("script.md", "plan.md"):
            p = os.path.join(project_dir, name)
            if os.path.exists(p):
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        extra[name.replace(".", "_")] = f.read()
                except Exception:
                    pass
        total_cost = conn.execute(
            "SELECT COALESCE(SUM(cost),0) c, COALESCE(MIN(currency),'CNY') cur FROM costs"
        ).fetchone()
        return {
            "project": pr, "stages": stages, "shots": shots,
            "verifications": vers, "costs": costs, "feedback": fbs,
            "artifacts": arts, "decision_log": logs, "extra": extra,
            "total_cost": {"amount": total_cost["c"], "currency": total_cost["cur"]},
            "pending_feedback": sum(1 for f in fbs if f.get("status") != "resolved"),
            "project_dir": os.path.abspath(project_dir),
        }
    finally:
        conn.close()


# ---------- 后台启动支持 ----------
STATE_FILENAME = ".dashboard.json"
LOG_FILENAME = ".dashboard.log"
DEFAULT_PORT = 8620
PORT_BAND = (8620, 8639)
DASHBOARD_URL_PREFIX = "DASHBOARD_URL="


def _state_path(project_dir):
    return os.path.join(project_dir, STATE_FILENAME)


def read_state(project_dir):
    try:
        with open(_state_path(project_dir), "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def write_state(project_dir, state):
    with open(_state_path(project_dir), "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)


def clear_state(project_dir):
    try:
        os.remove(_state_path(project_dir))
    except OSError:
        pass


def _socket_free(bind, port):
    import socket as _socket
    s = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
    s.setsockopt(_socket.SOL_SOCKET, _socket.SO_REUSEADDR, 1)
    try:
        s.bind((bind, port))
    except OSError:
        return False
    finally:
        s.close()
    return True


def pick_port(bind, preferred, lo=PORT_BAND[0], hi=PORT_BAND[1]):
    for port in range(max(int(preferred), lo), hi + 1):
        if _socket_free(bind, port):
            return port
    return None


def probe_alive(host, port, timeout=2.0):
    import urllib.request
    url = "http://%s:%d/api/status" % (host, port)
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def health_check(host, port, attempts=25, interval=0.2):
    for _ in range(attempts):
        if probe_alive(host, port, timeout=1.0):
            return True
        time.sleep(interval)
    return False


def extract_url(stdout_text):
    for line in (stdout_text or "").splitlines():
        line = line.strip()
        if line.startswith(DASHBOARD_URL_PREFIX):
            return line[len(DASHBOARD_URL_PREFIX):].strip()
    return None


def _bind_host(args_bind):
    return "127.0.0.1" if args_bind in ("0.0.0.0", "", None) else args_bind


def _can_fork():
    return hasattr(os, "fork")


def _serve_foreground(project_dir, bind, port):
    server = ThreadingHTTPServer((bind, port), make_handler(project_dir))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()


def _redirect_stdio(log_path):
    devnull = os.open(os.devnull, os.O_RDWR)
    os.dup2(devnull, 0)
    lf = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    os.dup2(lf, 1)
    os.dup2(lf, 2)


def _fork_and_serve(project_dir, bind, port, log_path):
    """fork 出后台子进程 serve；父进程返回子进程 pid。

    复用 / 前台回退由调用方（cmd_start）决策；此函数假定已在 POSIX 且端口已选好。
    """
    pid = os.fork()
    if pid == 0:  # child
        try:
            os.setsid()
            _redirect_stdio(log_path)
            _serve_foreground(project_dir, bind, port)
        except Exception as e:  # noqa: BLE001
            try:
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write("dashboard child crashed: %s\n" % e)
            finally:
                os._exit(1)
        os._exit(0)
    return pid


def cmd_start(args):
    project_dir = os.path.abspath(args.dir)
    host = _bind_host(args.bind)

    # 1) 复用探活
    st = read_state(project_dir)
    if st and st.get("port") and probe_alive(host, int(st["port"])):
        url = "http://%s:%d/" % (host, int(st["port"]))
        print(DASHBOARD_URL_PREFIX + url)
        print("lite-video 预览看板已在运行（复用）: %s" % url)
        return 0

    # 2) 端口选择
    port = pick_port(host, args.port or DEFAULT_PORT)
    if port is None:
        print("ERROR: 无可用端口（%d-%d 均被占用）" % PORT_BAND, file=sys.stderr)
        return 2

    # 3) 库检查（后台 serve 需要生产库）
    if not os.path.exists(os.path.join(project_dir, pv_db.DB_NAME)):
        print("ERROR: 未找到生产库 %s/%s（先用 pv_db.py init 初始化）"
              % (project_dir, pv_db.DB_NAME), file=sys.stderr)
        return 1

    # 4) 后台化
    log_path = os.path.join(project_dir, LOG_FILENAME)
    if not _can_fork():
        print("WARNING: 当前平台不支持 fork 后台化，已前台运行"
              "（请改用 nohup/独立终端）", file=sys.stderr)
        _serve_foreground(project_dir, args.bind, port)  # 前台阻塞，不返回
        return 0

    pid = _fork_and_serve(project_dir, args.bind, port, log_path)
    if not health_check(host, port):
        print("ERROR: 看板健康检查超时，详见 %s" % log_path, file=sys.stderr)
        return 3

    write_state(project_dir, {"pid": pid, "port": port, "bind": args.bind})
    url = "http://%s:%d/" % (host, port)
    print(DASHBOARD_URL_PREFIX + url)
    print("============================================")
    print("lite-video 预览看板已后台启动 (pid %d)" % pid)
    print("  地址: %s" % url)
    print("  项目: %s" % project_dir)
    print("  日志: %s" % log_path)
    print("  停止: python3 scripts/pv_dashboard.py --dir <目录> --stop")
    print("============================================")
    return 0


def cmd_stop(args):
    project_dir = os.path.abspath(args.dir)
    st = read_state(project_dir)
    if not st or not st.get("pid"):
        clear_state(project_dir)
        print("看板未在运行（无状态记录）")
        return 0
    pid = int(st["pid"])
    try:
        os.kill(pid, 15)  # SIGTERM
        print("已停止看板 (pid %d)" % pid)
    except ProcessLookupError:
        print("看板进程已不存在 (pid %d)，清理状态" % pid)
    except OSError as e:
        print("停止失败: %s（可手动 kill %d）" % (e, pid), file=sys.stderr)
        return 4
    clear_state(project_dir)
    return 0


def cmd_status(args):
    project_dir = os.path.abspath(args.dir)
    host = _bind_host(args.bind)
    st = read_state(project_dir)
    if st and st.get("port") and probe_alive(host, int(st["port"])):
        url = "http://%s:%d/" % (host, int(st["port"]))
        print("运行中: %s (pid %s)" % (url, st.get("pid")))
        return 0
    clear_state(project_dir)
    print("未运行")
    return 1


def make_handler(project_dir=None, projects=None):
    """project_dir: 单项目模式；projects: 多项目模式 {slug: realpath}。"""
    projects = projects or {}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # 静默访问日志
            pass

        # ---------- 响应辅助 ----------
        def _send(self, code, body, ctype="application/json; charset=utf-8"):
            data = body.encode("utf-8") if isinstance(body, str) else body
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def _json(self, obj, code=200):
            self._send(code, json.dumps(obj, ensure_ascii=False, default=str))

        def _resolve(self, path):
            """返回 (project_real, project_dir, rest, base)；未命中返回 (None,...)。"""
            if project_dir:
                return os.path.realpath(project_dir), project_dir, path, ""
            m = re.match(r"^/p/([^/]+)(/.*)?$", path)
            if not m:
                return None, None, None, None
            slug, rest = m.group(1), m.group(2) or "/"
            real = projects.get(slug)
            if not real:
                return None, None, None, None
            return real, real, rest, "/p/%s/" % slug

        # ---------- GET ----------
        def do_GET(self):
            path = self.path.split("?")[0]
            # 多项目列表页与项目 API
            if not project_dir and path in ("/", "/index.html"):
                return self._send(200, LIST_HTML, "text/html; charset=utf-8")
            if not project_dir and path == "/api/projects":
                try:
                    return self._json(list_projects(projects))
                except Exception as e:  # noqa: BLE001
                    return self._json({"error": str(e)}, 500)
            # 内置动画库（全局路由，供回放页 <script src=/libs/...> 使用）
            if path.startswith("/libs/"):
                return self._serve_lib(path[len("/libs/"):])
            proj_real, proj_dir, rest, base = self._resolve(path)
            if proj_real is None:
                return self._send(404, "not found", "text/plain; charset=utf-8")
            if rest in ("/", "/index.html"):
                page = INDEX_HTML.replace("__BASE__", json.dumps(base))
                return self._send(200, page, "text/html; charset=utf-8")
            if rest == "/api/status":
                try:
                    return self._json(build_status(proj_dir, proj_real))
                except Exception as e:  # noqa: BLE001
                    return self._json({"error": str(e)}, 500)
            if rest.startswith("/libs/"):
                return self._serve_lib(rest[len("/libs/"):])
            if rest.startswith("/page/"):
                return self._serve_replay_page(rest, proj_real, base)
            if rest.startswith("/files/"):
                return self._serve_file(rest[len("/files/"):], proj_real)
            return self._send(404, "not found", "text/plain; charset=utf-8")

        # ---------- POST ----------
        def do_POST(self):
            path = self.path.split("?")[0]
            proj_real, proj_dir, rest, base = self._resolve(path)
            if proj_real is None:
                return self._send(404, "not found", "text/plain; charset=utf-8")
            try:
                n = int(self.headers.get("Content-Length", 0))
                raw = self.rfile.read(n).decode("utf-8") if n else "{}"
                doc = json.loads(raw or "{}")
            except Exception:
                return self._json({"error": "invalid json"}, 400)
            if rest == "/api/feedback":
                content = (doc.get("content") or "").strip()
                if not content:
                    return self._json({"error": "反馈内容不能为空"}, 400)
                conn = pv_db.connect(proj_dir)
                try:
                    fid = pv_db.add_feedback(conn, doc.get("stage") or "",
                                             doc.get("shot") or None, content)
                finally:
                    conn.close()
                return self._json({"ok": True, "id": fid})
            if rest == "/api/feedback/resolve":
                conn = pv_db.connect(proj_dir)
                try:
                    pv_db.resolve_feedback(conn, int(doc.get("id", 0)))
                finally:
                    conn.close()
                return self._json({"ok": True})
            return self._send(404, "not found", "text/plain; charset=utf-8")

        # ---------- 内置动画库（白名单，防穿越）----------
        def _serve_lib(self, name):
            if not re.fullmatch(r"[a-zA-Z0-9_\-]+\.min\.js", name):
                return self._send(403, "forbidden", "text/plain")
            full = os.path.realpath(os.path.join(pv_common.libs_dir(), name))
            if not full.startswith(os.path.realpath(pv_common.libs_dir()) + os.sep):
                return self._send(403, "forbidden", "text/plain")
            if not os.path.isfile(full):
                return self._send(404, "lib not found", "text/plain")
            try:
                with open(full, "rb") as f:
                    return self._send(200, f.read(), "application/javascript; charset=utf-8")
            except Exception as e:  # noqa: BLE001
                return self._send(500, str(e), "text/plain")

        # ---------- 文件服务（防穿越）----------
        def _serve_file(self, rel, project_real):
            full = os.path.realpath(os.path.join(project_real, rel))
            if not full.startswith(project_real + os.sep) and full != project_real:
                return self._send(403, "forbidden", "text/plain")
            if not os.path.isfile(full):
                return self._send(404, "not found", "text/plain")
            ext = os.path.splitext(full)[1].lower()
            ctype = MIME.get(ext, "application/octet-stream")
            try:
                with open(full, "rb") as f:
                    return self._send(200, f.read(), ctype)
            except Exception as e:  # noqa: BLE001
                return self._send(500, str(e), "text/plain")

        # ---------- 动画回放页（注入驱动）----------
        def _serve_replay_page(self, path, project_real, base):
            try:
                shot_id = int(path.rsplit("/", 1)[1])
            except ValueError:
                return self._send(400, "bad shot id", "text/plain")
            conn = pv_db.connect(project_real)
            try:
                row = conn.execute(
                    "SELECT web_page_path FROM shots WHERE id=?", (shot_id,)).fetchone()
            finally:
                conn.close()
            if not row or not row["web_page_path"] \
                    or not os.path.exists(row["web_page_path"]):
                return self._send(404, "该镜尚无动画页面", "text/plain; charset=utf-8")
            page_path = os.path.realpath(row["web_page_path"])
            if not page_path.startswith(project_real + os.sep):
                return self._send(403, "forbidden", "text/plain")
            with open(page_path, "r", encoding="utf-8") as f:
                body = f.read()
            # 库注入：解析 pv-libs 声明，以 <script src> 形式插在 <head> 之后
            # （先于页面脚本执行；渲染器侧同逻辑但用内联注入，看板侧走 /libs/ 路由）
            m = re.search(r'<meta\s+name="pv-libs"\s+content="([^"]*)"', body[:20000])
            lib_tags = ""
            if m:
                names = [s.strip() for s in m.group(1).split(",") if s.strip()]
                lib_tags = "".join(
                    '<script src="/libs/%s.min.js"></script>' % n
                    for n in names if re.fullmatch(r"[a-zA-Z0-9_\-]+", n))
            if "</head>" in body:
                body = body.replace("</head>", lib_tags + "</head>", 1)
            else:
                body = lib_tags + body
            if "</body>" in body:
                body = body.replace("</body>", INJECT_REPLAY + "</body>", 1)
            else:
                body += INJECT_REPLAY
            return self._send(200, body, "text/html; charset=utf-8")

    return Handler


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", help="单项目模式：项目目录（含 production.db）")
    ap.add_argument("--root", default=".",
                    help="多项目模式：扫描根目录（默认当前目录）")
    ap.add_argument("--depth", type=int, default=3,
                    help="多项目模式：扫描深度（默认 3 层）")
    ap.add_argument("--port", type=int, default=8620)
    ap.add_argument("--bind", default="127.0.0.1",
                    help="监听地址（默认仅本机；容器/远程环境可用 0.0.0.0）")
    ap.add_argument("--once", action="store_true",
                    help="打印一次状态/列表 JSON 后退出（调试用）")
    ap.add_argument("--start", action="store_true",
                    help="后台启动看板，stdout 打印 DASHBOARD_URL= 地址行（需 --dir）")
    ap.add_argument("--stop", action="store_true",
                    help="停止 --dir 项目的后台看板")
    ap.add_argument("--status", action="store_true",
                    help="查询 --dir 项目的看板是否在运行")
    args = ap.parse_args()

    if args.stop:
        if not args.dir:
            raise SystemExit("--stop 需要 --dir <项目目录>")
        raise SystemExit(cmd_stop(args))
    if args.status:
        if not args.dir:
            raise SystemExit("--status 需要 --dir <项目目录>")
        raise SystemExit(cmd_status(args))
    if args.start:
        if not args.dir:
            raise SystemExit("--start 需要 --dir <项目目录>")
        raise SystemExit(cmd_start(args))

    if args.dir:
        # 单项目模式（兼容旧用法）
        if not os.path.exists(os.path.join(args.dir, pv_db.DB_NAME)):
            raise SystemExit("未找到生产库: %s/%s（先用 pv_db.py init 初始化）"
                             % (args.dir, pv_db.DB_NAME))
        if args.once:
            print(json.dumps(build_status(args.dir), ensure_ascii=False, indent=2))
            return
        server = ThreadingHTTPServer((args.bind, args.port), make_handler(args.dir))
        print("============================================")
        print("lite-video 预览看板已启动（单项目模式）")
        print("  地址: http://%s:%d/" % (args.bind, args.port))
        print("  项目: %s" % os.path.abspath(args.dir))
        print("  停止: Ctrl+C")
        print("============================================")
    else:
        # 多项目模式：自动扫描
        projects = scan_projects(args.root, args.depth)
        if args.once:
            print(json.dumps(list_projects(projects), ensure_ascii=False, indent=2))
            return
        server = ThreadingHTTPServer(
            (args.bind, args.port), make_handler(projects=projects))
        print("============================================")
        print("lite-video 预览看板已启动（多项目模式）")
        print("  地址: http://%s:%d/   ← 项目列表，点击进入")
        print("  扫描: %s（深度 %d）→ %d 个项目"
              % (os.path.abspath(args.root), args.depth, len(projects)))
        for slug, real in sorted(projects.items()):
            print("    - [%s] %s" % (slug, real))
        if not projects:
            print("  （未找到项目：含 %s 的目录会被识别；可加大 --depth 或换 --root）"
                  % pv_db.DB_NAME)
        print("  停止: Ctrl+C")
        print("============================================")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n看板已停止")
        server.server_close()


if __name__ == "__main__":
    main()
