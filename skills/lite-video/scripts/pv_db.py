#!/usr/bin/env python3
"""lite-video 状态层：SQLite 全流程状态引擎。

借鉴 OpenMontage 的 checkpoint 协议 + superpowers 的门控/验证纪律，
用单库事务替代 storyboard.json，保证状态原子性、可查询、全程留痕。

数据模型：
  projects      项目元信息（主题/标题/分辨率/音色/成片路径）
  stages        六阶段状态机：script→plan→tts→visuals→segments→compose
                状态：pending/in_progress/awaiting_human/completed
                script 与 plan 为门控阶段（gated=1），未获批准不能完成
  shots         分镜级产物（旁白/画面描述/图片/音频/时长/片段/运镜）
  approvals     门控审批记录（approved/revision/aborted）
  verifications 验证证据（evidence before claims：宣称完成必须有验证记录）
  artifacts     各阶段产物登记（剧本/计划书/字幕/成片等）
  decision_log  决策日志

常用 CLI：
  init / status / start-stage / gate / approve / complete-stage /
  set-shots / get-shots / set-shot / update-project /
  add-artifact / log / verify / next-stage
"""
import argparse
import json
import os
import sqlite3
import sys

DB_NAME = "production.db"
MODES = ("imageflow", "fullvideo", "webanim")
# imageflow 图文模式：图片 + Ken Burns 运镜（无需视频生成能力，兜底方案）
# fullvideo 全视频模式：首/尾帧图 → 图生视频 → 剪辑（需要图生视频能力）
# webanim   Web动画模式：HTML/CSS 动画页 → 无头浏览器确定性逐帧渲染 → 剪辑
STAGES_BY_MODE = {
    "imageflow": ["script", "plan", "tts", "visuals", "segments", "compose"],
    "fullvideo": ["script", "plan", "tts", "keyframes", "videogen", "compose"],
    "webanim": ["script", "plan", "tts", "webpages", "weblint", "webrender", "compose"],
}
GATED = {"script", "plan"}
STAGE_LABEL = {
    "script": "剧本讨论",
    "plan": "制作计划",
    "tts": "旁白合成",
    "visuals": "配图准备",
    "segments": "分镜片段",
    "keyframes": "首尾帧生成",
    "videogen": "图生视频",
    "webpages": "动画页面",
    "weblint": "动画预检",
    "webrender": "逐帧渲染",
    "compose": "视频合成",
}


# ---------- 基础 ----------

def db_path(project_dir):
    return os.path.join(project_dir, DB_NAME)


def connect(project_dir):
    p = db_path(project_dir)
    if not os.path.exists(p):
        raise SystemExit("未找到生产库: %s（先运行 pv_db.py init）" % p)
    conn = sqlite3.connect(p)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # 向后兼容迁移：旧版本建的库缺少新增表时自动补齐
    conn.execute(
        """CREATE TABLE IF NOT EXISTS feedback(
             id INTEGER PRIMARY KEY AUTOINCREMENT, stage TEXT, shot_id INTEGER,
             content TEXT NOT NULL, status TEXT DEFAULT 'pending',
             created_at TEXT, resolved_at TEXT, seen_at TEXT, fix_reason TEXT, fixed_at TEXT
           )"""
    )
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(shots)")]
        for col in ("tts_text", "animation_brief"):
            if col not in cols:
                conn.execute("ALTER TABLE shots ADD COLUMN %s TEXT" % col)
        fb_cols = [r[1] for r in conn.execute("PRAGMA table_info(feedback)")]
        for col in ("seen_at", "fix_reason", "fixed_at"):
            if col not in fb_cols:
                conn.execute("ALTER TABLE feedback ADD COLUMN %s TEXT" % col)
        conn.commit()
    except sqlite3.Error:
        pass
    return conn


def now():
    import datetime

    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ---------- 初始化 ----------

def init_project(project_dir, topic, title, width, height, voice, fps, mode, force=False):
    if mode not in MODES:
        raise SystemExit("mode 必须是 %s 之一" % "/".join(MODES))
    p = db_path(project_dir)
    if os.path.exists(p):
        if not force:
            raise SystemExit("生产库已存在: %s（如需重建请加 --force）" % p)
        os.remove(p)
    os.makedirs(project_dir, exist_ok=True)
    conn = sqlite3.connect(p)
    conn.executescript(
        """
        CREATE TABLE projects(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          topic TEXT NOT NULL, title TEXT,
          width INTEGER DEFAULT 1080, height INTEGER DEFAULT 1920,
          voice TEXT DEFAULT 'zh-CN-YunxiNeural', fps INTEGER DEFAULT 30,
          mode TEXT NOT NULL DEFAULT 'imageflow',
          status TEXT DEFAULT 'active',
          final_video_path TEXT, total_duration REAL,
          created_at TEXT, updated_at TEXT
        );
        CREATE TABLE stages(
          name TEXT PRIMARY KEY, seq INTEGER NOT NULL, gated INTEGER DEFAULT 0,
          status TEXT NOT NULL DEFAULT 'pending',
          summary TEXT, started_at TEXT, completed_at TEXT
        );
        CREATE TABLE shots(
          id INTEGER PRIMARY KEY, narration TEXT NOT NULL, image_prompt TEXT,
          image_path TEXT, audio_path TEXT, duration REAL,
          video_segment_path TEXT, motion TEXT, status TEXT DEFAULT 'pending',
          first_frame_path TEXT, last_frame_path TEXT,
          web_page_path TEXT, tts_text TEXT, animation_brief TEXT
        );
        CREATE TABLE approvals(
          id INTEGER PRIMARY KEY AUTOINCREMENT, stage TEXT NOT NULL,
          decision TEXT NOT NULL, notes TEXT, created_at TEXT
        );
        CREATE TABLE costs(
          id INTEGER PRIMARY KEY AUTOINCREMENT, stage TEXT, item TEXT NOT NULL,
          cost REAL NOT NULL DEFAULT 0, currency TEXT DEFAULT 'CNY',
          notes TEXT, created_at TEXT
        );
        CREATE TABLE verifications(
          id INTEGER PRIMARY KEY AUTOINCREMENT, stage TEXT NOT NULL,
          check_name TEXT NOT NULL, passed INTEGER NOT NULL,
          evidence TEXT, created_at TEXT
        );
        CREATE TABLE artifacts(
          id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL,
          path TEXT NOT NULL, meta TEXT, created_at TEXT
        );
        CREATE TABLE decision_log(
          id INTEGER PRIMARY KEY AUTOINCREMENT, stage TEXT,
          content TEXT NOT NULL, created_at TEXT
        );
        CREATE TABLE feedback(
          id INTEGER PRIMARY KEY AUTOINCREMENT, stage TEXT, shot_id INTEGER,
          content TEXT NOT NULL, status TEXT DEFAULT 'pending',
          created_at TEXT, resolved_at TEXT, seen_at TEXT, fix_reason TEXT, fixed_at TEXT
        );
        """
    )
    t = now()
    conn.execute(
        "INSERT INTO projects(topic,title,width,height,voice,fps,mode,created_at,updated_at)"
        " VALUES(?,?,?,?,?,?,?,?,?)",
        (topic, title, width, height, voice, fps, mode, t, t),
    )
    for i, name in enumerate(STAGES_BY_MODE[mode]):
        conn.execute(
            "INSERT INTO stages(name,seq,gated) VALUES(?,?,?)",
            (name, i, 1 if name in GATED else 0),
        )
    conn.commit()
    conn.close()
    print("生产库已初始化: %s（模式: %s）" % (p, mode))


# ---------- 项目/阶段 ----------

def get_project(conn):
    row = conn.execute("SELECT * FROM projects ORDER BY id LIMIT 1").fetchone()
    if not row:
        raise SystemExit("projects 表为空")
    return row


def stage_row(conn, name):
    row = conn.execute("SELECT * FROM stages WHERE name=?", (name,)).fetchone()
    if not row:
        raise SystemExit("未知阶段: %s（合法：%s）" % (name, ",".join(STAGES)))
    return row


def start_stage(conn, name):
    check_and_mark_pending(conn)   # 强制前置:进阶段即读即标记新反馈(非阻塞)
    row = stage_row(conn, name)
    if row["status"] == "completed":
        print("阶段 %s 已完成，无需重启" % name)
        return
    prev = conn.execute(
        "SELECT name,status FROM stages WHERE seq<? ORDER BY seq DESC LIMIT 1",
        (row["seq"],),
    ).fetchone()
    if prev and prev["status"] != "completed":
        raise SystemExit(
            "顺序违规：阶段 %s 的前置阶段 %s 尚未完成（当前 %s）。"
            "流水线必须按序推进。" % (name, prev["name"], prev["status"])
        )
    conn.execute(
        "UPDATE stages SET status='in_progress', started_at=? WHERE name=?",
        (now(), name),
    )
    conn.commit()
    print("阶段进入 in_progress: %s" % name)


def gate_stage(conn, name, summary):
    check_and_mark_pending(conn)   # 强制前置:提交门控前读即标记(非阻塞)
    row = stage_row(conn, name)
    if not row["gated"]:
        raise SystemExit("阶段 %s 不是门控阶段，无需人工审批" % name)
    conn.execute(
        "UPDATE stages SET status='awaiting_human', summary=? WHERE name=?",
        (summary, name),
    )
    conn.commit()
    print("阶段 %s 已挂起等待人工审批（awaiting_human）。请向用户展示内容并结束回合。" % name)


def approve_stage(conn, name, decision, notes):
    row = stage_row(conn, name)
    if not row["gated"]:
        raise SystemExit("阶段 %s 不是门控阶段" % name)
    if decision not in ("approved", "revision", "aborted"):
        raise SystemExit("decision 必须是 approved/revision/aborted")
    conn.execute(
        "INSERT INTO approvals(stage,decision,notes,created_at) VALUES(?,?,?,?)",
        (name, decision, notes, now()),
    )
    if decision == "approved":
        print("阶段 %s 已获批准" % name)
    else:
        conn.execute(
            "UPDATE stages SET status='in_progress', summary=NULL WHERE name=?", (name,)
        )
        print("阶段 %s 审批结论=%s，已退回 in_progress 等待修订" % (name, decision))
    conn.commit()


def complete_stage(conn, name):
    row = stage_row(conn, name)
    if row["status"] == "completed":
        print("阶段 %s 已完成" % name)
        return
    if row["gated"]:
        ap = conn.execute(
            "SELECT decision FROM approvals WHERE stage=? ORDER BY id DESC LIMIT 1",
            (name,),
        ).fetchone()
        if not ap or ap["decision"] != "approved":
            raise SystemExit(
                "GATE VIOLATION：门控阶段 %s 未获用户批准，禁止标记完成。"
                "请先 gate → 展示 → 用户批准 → approve。" % name
            )
    else:
        ok = conn.execute(
            "SELECT COUNT(*) c FROM verifications WHERE stage=? AND passed=1", (name,)
        ).fetchone()["c"]
        if ok == 0:
            raise SystemExit(
                "EVIDENCE REQUIRED：阶段 %s 没有任何通过的验证记录。"
                "Evidence before claims——先运行 pv_verify.py 拿到证据再完成阶段。" % name
            )
    # 所有阶段（含门控）：存在失败验证记录一律禁止完成
    bad = conn.execute(
        "SELECT COUNT(*) c FROM verifications WHERE stage=? AND passed=0", (name,)
    ).fetchone()["c"]
    if bad > 0:
        rows = conn.execute(
            "SELECT check_name, evidence FROM verifications"
            " WHERE stage=? AND passed=0 ORDER BY id DESC LIMIT 3", (name,)
        ).fetchall()
        detail = "; ".join("%s(%s)" % (r["check_name"], (r["evidence"] or "")[:60])
                           for r in rows)
        raise SystemExit(
            "VERIFICATION FAILED：阶段 %s 存在 %d 条失败验证记录，禁止完成。"
            "修复后重跑验证再试。最近失败: %s" % (name, bad, detail)
        )
    conn.execute(
        "UPDATE stages SET status='completed', completed_at=? WHERE name=?",
        (now(), name),
    )
    conn.commit()
    print("阶段完成: %s" % name)


def next_stage(conn):
    row = conn.execute(
        "SELECT name,status FROM stages WHERE status!='completed' ORDER BY seq LIMIT 1"
    ).fetchone()
    # 未修复反馈(pending+seen)提醒 agent;fixed 待用户确认另列(非阻塞)
    try:
        n_unfixed = conn.execute(
            "SELECT COUNT(*) c FROM feedback WHERE status IN ('pending','seen')"
        ).fetchone()["c"]
        n_fixed = conn.execute(
            "SELECT COUNT(*) c FROM feedback WHERE status='fixed'").fetchone()["c"]
    except Exception:
        n_unfixed = n_fixed = 0
    if n_unfixed:
        print("⚠ 未修复反馈 %d 条 → pv_db.py feedback-fix --dir <目录> --id <N> --reason \"原因\""
              % n_unfixed)
    if n_fixed:
        print("ℹ 另有 %d 条已修复待用户确认（不阻塞）" % n_fixed)
    if not row:
        print("ALL_DONE")
        return
    print("%s\t%s" % (row["name"], row["status"]))


# ---------- 分镜 ----------

def set_shots(conn, shots_file):
    with open(shots_file, "r", encoding="utf-8") as f:
        shots = json.load(f)
    conn.execute("DELETE FROM shots")
    for s in shots:
        conn.execute(
            "INSERT INTO shots(id,narration,image_prompt,motion,tts_text,animation_brief)"
            " VALUES(?,?,?,?,?,?)",
            (s["id"], s["narration"], s.get("image_prompt", ""),
             s.get("motion", "in" if s["id"] % 2 == 1 else "out"),
             s.get("tts_text", ""), s.get("animation_brief", "")),
        )
    conn.commit()
    print("分镜已写入: %d 条" % len(shots))


def update_shot(conn, shot_id, image_path=None, audio_path=None,
                duration=None, segment_path=None, image_prompt=None, status=None,
                first_frame_path=None, last_frame_path=None, web_page_path=None,
                tts_text=None):
    sets, args = [], []
    if image_path is not None:
        sets.append("image_path=?"); args.append(image_path)
    if audio_path is not None:
        sets.append("audio_path=?"); args.append(audio_path)
    if duration is not None:
        sets.append("duration=?"); args.append(duration)
    if segment_path is not None:
        sets.append("video_segment_path=?"); args.append(segment_path)
    if image_prompt is not None:
        sets.append("image_prompt=?"); args.append(image_prompt)
    if status is not None:
        sets.append("status=?"); args.append(status)
    if first_frame_path is not None:
        sets.append("first_frame_path=?"); args.append(first_frame_path)
    if last_frame_path is not None:
        sets.append("last_frame_path=?"); args.append(last_frame_path)
    if web_page_path is not None:
        sets.append("web_page_path=?"); args.append(web_page_path)
    if tts_text is not None:
        sets.append("tts_text=?"); args.append(tts_text)
    if animation_brief is not None:
        sets.append("animation_brief=?"); args.append(animation_brief)
    if not sets:
        raise SystemExit("没有要更新的字段")
    args.append(shot_id)
    cur = conn.execute("UPDATE shots SET %s WHERE id=?" % ",".join(sets), args)
    conn.commit()
    if cur.rowcount == 0:
        raise SystemExit("shot %s 不存在" % shot_id)
    print("shot %s 已更新" % shot_id)


def get_shots(conn):
    rows = conn.execute("SELECT * FROM shots ORDER BY id").fetchall()
    print(json.dumps([dict(r) for r in rows], ensure_ascii=False, indent=2))


# ---------- 产物/日志/验证 ----------

def add_artifact(conn, kind, path, meta):
    conn.execute(
        "INSERT INTO artifacts(kind,path,meta,created_at) VALUES(?,?,?,?)",
        (kind, path, meta, now()),
    )
    conn.commit()
    print("产物已登记: %s -> %s" % (kind, path))


def add_log(conn, stage, content):
    conn.execute(
        "INSERT INTO decision_log(stage,content,created_at) VALUES(?,?,?)",
        (stage, content, now()),
    )
    conn.commit()
    print("已记录决策日志 [%s]" % (stage or "-"))


def add_feedback(conn, stage, shot_id, content):
    """登记一条用户反馈（来自 dashboard 或人工），状态 pending 待 agent 处理。"""
    conn.execute(
        "INSERT INTO feedback(stage,shot_id,content,status,created_at)"
        " VALUES(?,?,?, 'pending', ?)",
        (stage or "", shot_id, content, now()),
    )
    conn.commit()
    fid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    print("反馈已登记 #%d [%s%s]: %s"
          % (fid, stage or "-", ("/shot_%02d" % shot_id) if shot_id else "", content))
    return fid


def check_and_mark_pending(conn):
    """原子列出 pending 反馈并置 seen(读即标记)。返回被标记行。"""
    rows = conn.execute(
        "SELECT * FROM feedback WHERE status='pending' ORDER BY id"
    ).fetchall()
    if rows:
        conn.execute(
            "UPDATE feedback SET status='seen', seen_at=? WHERE status='pending'",
            (now(),),
        )
        conn.commit()
        for r in rows:
            print("#%d [%s] [%s%s] %s — %s"
                  % (r["id"], "seen", r["stage"] or "-",
                     ("/shot_%02d" % r["shot_id"]) if r["shot_id"] else "",
                     r["created_at"] or "", r["content"]))
        print("⚠ %d 条新反馈已标记已读；修复后用: "
              "pv_db.py feedback-fix --dir <目录> --id <N> --reason \"原因\"" % len(rows))
    return rows


def fix_feedback(conn, fid, reason):
    """agent 修复反馈:pending/seen → fixed,记录 fix_reason。"""
    cur = conn.execute(
        "UPDATE feedback SET status='fixed', fix_reason=?, fixed_at=? "
        "WHERE id=? AND status IN ('pending','seen')",
        (reason, now(), fid),
    )
    conn.commit()
    if cur.rowcount:
        print("反馈 #%d 已标记已修复：%s" % (fid, reason))
    else:
        print("反馈 #%d 不存在或已修复/已解决" % fid)


def resolve_feedback(conn, fid):
    """用户确认已解决:任意非 resolved → resolved(保底允许 fixed/pending/seen 直跳)。"""
    cur = conn.execute(
        "UPDATE feedback SET status='resolved', resolved_at=? WHERE id=? AND status!='resolved'",
        (now(), fid),
    )
    conn.commit()
    if cur.rowcount:
        print("反馈 #%d 已确认解决" % fid)
    else:
        print("反馈 #%d 不存在或已解决" % fid)


def list_feedback(conn, which="all"):
    """which: all | pending(读即标记 seen) | seen | fixed | unresolved。pending 外只读。"""
    if which == "pending":
        rows = check_and_mark_pending(conn)
        if not rows:
            print("（无新反馈）")
        return
    where = {"seen": " WHERE status='seen'",
             "fixed": " WHERE status='fixed'",
             "unresolved": " WHERE status!='resolved'"}
    q = "SELECT * FROM feedback" + where.get(which, "") + " ORDER BY id"
    rows = conn.execute(q).fetchall()
    for r in rows:
        extra = (" | 修复:%s" % r["fix_reason"]) if r["fix_reason"] else ""
        print("#%d [%s] [%s%s] %s — %s%s"
              % (r["id"], r["status"], r["stage"] or "-",
                 ("/shot_%02d" % r["shot_id"]) if r["shot_id"] else "",
                 r["created_at"] or "", r["content"], extra))
    if not rows:
        print("（无反馈记录）")


def add_cost(conn, stage, item, cost, currency, notes):
    conn.execute(
        "INSERT INTO costs(stage,item,cost,currency,notes,created_at)"
        " VALUES(?,?,?,?,?,?)",
        (stage, item, cost, currency, notes, now()),
    )
    conn.commit()
    total = conn.execute("SELECT COALESCE(SUM(cost),0) FROM costs").fetchone()[0]
    print("成本已记录: [%s] %s %.4f %s（累计 %.4f %s）"
          % (stage or "-", item, cost, currency, total, currency))


def record_verify(conn, stage, check, passed, evidence):
    conn.execute(
        "INSERT INTO verifications(stage,check_name,passed,evidence,created_at)"
        " VALUES(?,?,?,?,?)",
        (stage, check, 1 if passed else 0, evidence, now()),
    )
    conn.commit()
    print("验证已记录: [%s] %s %s" % (stage, check, "PASS" if passed else "FAIL"))


def update_project(conn, final=None, total_duration=None, title=None):
    sets, args = ["updated_at=?"], [now()]
    if final is not None:
        sets.append("final_video_path=?"); args.append(final)
    if total_duration is not None:
        sets.append("total_duration=?"); args.append(total_duration)
    if title is not None:
        sets.append("title=?"); args.append(title)
    conn.execute("UPDATE projects SET %s WHERE id=1" % ",".join(sets), args)
    conn.commit()
    print("项目信息已更新")


# ---------- 状态报告 ----------

def status_report(conn):
    pr = get_project(conn)
    lines = []
    lines.append("项目: %s（%s）" % (pr["title"] or pr["topic"], pr["topic"]))
    mode_label = {"imageflow": "图文模式", "fullvideo": "全视频模式",
                  "webanim": "Web动画模式"}.get(pr["mode"], pr["mode"])
    lines.append("规格: %dx%d | 音色: %s | fps: %d | 模式: %s | 状态: %s"
                 % (pr["width"], pr["height"], pr["voice"], pr["fps"],
                    mode_label, pr["status"]))
    try:
        n_unfixed = conn.execute(
            "SELECT COUNT(*) c FROM feedback WHERE status IN ('pending','seen')"
        ).fetchone()["c"]
        n_fixed = conn.execute(
            "SELECT COUNT(*) c FROM feedback WHERE status='fixed'").fetchone()["c"]
        if n_unfixed:
            lines.append("⚠ 未修复反馈 %d 条 → pv_db.py feedback-fix --dir <目录> --id <N> --reason \"原因\""
                         % n_unfixed)
        if n_fixed:
            lines.append("ℹ 已修复待用户确认 %d 条（不阻塞）" % n_fixed)
    except Exception:
        pass
    if pr["final_video_path"]:
        lines.append("成片: %s（%.1fs）" % (pr["final_video_path"], pr["total_duration"] or 0))
    lines.append("")
    lines.append("阶段进度:")
    for r in conn.execute("SELECT * FROM stages ORDER BY seq"):
        mark = {"pending": "○", "in_progress": "◐",
                "awaiting_human": "⏸待审批", "completed": "✓"}[r["status"]]
        gated = " [门控]" if r["gated"] else ""
        lines.append("  %s %d.%s(%s)%s  %s"
                     % (mark, r["seq"] + 1, r["name"], STAGE_LABEL[r["name"]],
                        gated, r["started_at"] or ""))
    n = conn.execute("SELECT COUNT(*) c FROM shots").fetchone()["c"]
    done_audio = conn.execute(
        "SELECT COUNT(*) c FROM shots WHERE audio_path IS NOT NULL").fetchone()["c"]
    done_img = conn.execute(
        "SELECT COUNT(*) c FROM shots WHERE image_path IS NOT NULL").fetchone()["c"]
    done_ff = conn.execute(
        "SELECT COUNT(*) c FROM shots WHERE first_frame_path IS NOT NULL").fetchone()["c"]
    done_seg = conn.execute(
        "SELECT COUNT(*) c FROM shots WHERE video_segment_path IS NOT NULL").fetchone()["c"]
    lines.append("")
    if pr["mode"] == "fullvideo":
        lines.append("分镜: %d 条 | 音频 %d | 首帧 %d | 视频片段 %d"
                     % (n, done_audio, done_ff, done_seg))
    elif pr["mode"] == "webanim":
        done_page = conn.execute(
            "SELECT COUNT(*) c FROM shots WHERE web_page_path IS NOT NULL").fetchone()["c"]
        lines.append("分镜: %d 条 | 音频 %d | 动画页面 %d | 视频片段 %d"
                     % (n, done_audio, done_page, done_seg))
    else:
        lines.append("分镜: %d 条 | 音频 %d | 图片 %d | 片段 %d"
                     % (n, done_audio, done_img, done_seg))
    v_fail = conn.execute(
        "SELECT COUNT(*) c FROM verifications WHERE passed=0").fetchone()["c"]
    v_pass = conn.execute(
        "SELECT COUNT(*) c FROM verifications WHERE passed=1").fetchone()["c"]
    lines.append("验证: %d 通过 / %d 失败" % (v_pass, v_fail))
    # costs 表可能不存在于升级前的旧库
    try:
        total_cost = conn.execute(
            "SELECT COALESCE(SUM(cost),0) c, COALESCE(MIN(currency),'CNY') cur FROM costs"
        ).fetchone()
        if total_cost["c"]:
            lines.append("累计成本: %.4f %s" % (total_cost["c"], total_cost["cur"]))
    except Exception:
        pass
    print("\n".join(lines))


# ---------- CLI ----------

def _normalize_argv(argv):
    """兼容 `pv_db.py --dir <目录> <cmd>` 写法（SKILL.md 示例同款顺序）：
    把 --dir 及其值挪到子命令之后。"""
    if len(argv) >= 4 and argv[1] == "--dir":
        return [argv[0], argv[3], argv[1], argv[2]] + argv[4:]
    return argv


def main():
    sys.argv = _normalize_argv(sys.argv)
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add_dir(p):
        p.add_argument("--dir", required=True, help="项目目录（含 production.db）")

    p = sub.add_parser("init"); add_dir(p)
    p.add_argument("--topic", required=True)
    p.add_argument("--title", default="")
    p.add_argument("--width", type=int, default=1080)
    p.add_argument("--height", type=int, default=1920)
    p.add_argument("--voice", default="zh-CN-YunxiNeural")
    p.add_argument("--fps", type=int, default=30)
    p.add_argument("--mode", default="imageflow", choices=MODES,
                   help="imageflow=图文模式(图片+运镜), fullvideo=全视频模式(首尾帧+图生视频)")
    p.add_argument("--force", action="store_true")

    p = sub.add_parser("status"); add_dir(p)
    p = sub.add_parser("next-stage"); add_dir(p)

    p = sub.add_parser("start-stage"); add_dir(p); p.add_argument("--stage", required=True)
    p = sub.add_parser("gate"); add_dir(p)
    p.add_argument("--stage", required=True); p.add_argument("--summary", default="")
    p = sub.add_parser("approve"); add_dir(p)
    p.add_argument("--stage", required=True)
    p.add_argument("--decision", required=True); p.add_argument("--notes", default="")
    p = sub.add_parser("complete-stage"); add_dir(p); p.add_argument("--stage", required=True)

    p = sub.add_parser("set-shots"); add_dir(p); p.add_argument("--file", required=True)
    p = sub.add_parser("get-shots"); add_dir(p)
    p = sub.add_parser("set-shot"); add_dir(p)
    p.add_argument("--id", type=int, required=True)
    p.add_argument("--image-path"); p.add_argument("--audio-path")
    p.add_argument("--duration", type=float)
    p.add_argument("--segment-path"); p.add_argument("--image-prompt")
    p.add_argument("--first-frame-path"); p.add_argument("--last-frame-path")
    p.add_argument("--web-page-path")
    p.add_argument("--tts-text")
    p.add_argument("--animation-brief")
    p.add_argument("--status")

    p = sub.add_parser("update-project"); add_dir(p)
    p.add_argument("--final"); p.add_argument("--total-duration", type=float)
    p.add_argument("--title")

    p = sub.add_parser("add-artifact"); add_dir(p)
    p.add_argument("--kind", required=True); p.add_argument("--path", required=True)
    p.add_argument("--meta", default="")
    p = sub.add_parser("log"); add_dir(p)
    p.add_argument("--stage", default=""); p.add_argument("--content", required=True)
    p = sub.add_parser("cost-log"); add_dir(p)
    p.add_argument("--stage", default=""); p.add_argument("--item", required=True)
    p.add_argument("--cost", type=float, required=True)
    p.add_argument("--currency", default="CNY"); p.add_argument("--notes", default="")
    p = sub.add_parser("verify"); add_dir(p)
    p.add_argument("--stage", required=True); p.add_argument("--check", required=True)
    p.add_argument("--passed", type=int, required=True); p.add_argument("--evidence", default="")
    p = sub.add_parser("feedback-add"); add_dir(p)
    p.add_argument("--stage", default=""); p.add_argument("--shot", type=int, default=0)
    p.add_argument("--content", required=True)
    p = sub.add_parser("feedback-list"); add_dir(p)
    g = p.add_mutually_exclusive_group()
    g.add_argument("--pending", action="store_true", help="列新反馈并读即标记 seen")
    g.add_argument("--seen", action="store_true", help="仅列已读(只读)")
    g.add_argument("--fixed", action="store_true", help="仅列已修复待确认(只读)")
    g.add_argument("--unresolved", action="store_true", help="列全部未解决(含 fixed,只读)")
    p = sub.add_parser("feedback-fix"); add_dir(p)
    p.add_argument("--id", type=int, required=True)
    p.add_argument("--reason", required=True, help="修复原因(必填)")
    p = sub.add_parser("feedback-resolve"); add_dir(p)
    p.add_argument("--id", type=int, required=True)

    args = ap.parse_args()
    if args.cmd == "init":
        init_project(args.dir, args.topic, args.title, args.width, args.height,
                     args.voice, args.fps, args.mode, args.force)
        return
    conn = connect(args.dir)
    try:
        if args.cmd == "status":
            status_report(conn)
        elif args.cmd == "next-stage":
            next_stage(conn)
        elif args.cmd == "start-stage":
            start_stage(conn, args.stage)
        elif args.cmd == "gate":
            gate_stage(conn, args.stage, args.summary)
        elif args.cmd == "approve":
            approve_stage(conn, args.stage, args.decision, args.notes)
        elif args.cmd == "complete-stage":
            complete_stage(conn, args.stage)
        elif args.cmd == "set-shots":
            set_shots(conn, args.file)
        elif args.cmd == "get-shots":
            get_shots(conn)
        elif args.cmd == "set-shot":
            update_shot(conn, args.id, args.image_path, args.audio_path,
                        args.duration, args.segment_path, args.image_prompt,
                        args.status, args.first_frame_path, args.last_frame_path,
                        args.web_page_path, args.tts_text, args.animation_brief)
        elif args.cmd == "update-project":
            update_project(conn, args.final, args.total_duration, args.title)
        elif args.cmd == "add-artifact":
            add_artifact(conn, args.kind, args.path, args.meta)
        elif args.cmd == "log":
            add_log(conn, args.stage, args.content)
        elif args.cmd == "cost-log":
            add_cost(conn, args.stage, args.item, args.cost, args.currency, args.notes)
        elif args.cmd == "verify":
            record_verify(conn, args.stage, args.check, bool(args.passed), args.evidence)
        elif args.cmd == "feedback-add":
            add_feedback(conn, args.stage, args.shot or None, args.content)
        elif args.cmd == "feedback-list":
            which = ("pending" if args.pending else "seen" if args.seen
                     else "fixed" if args.fixed
                     else "unresolved" if args.unresolved else "all")
            list_feedback(conn, which)
        elif args.cmd == "feedback-fix":
            fix_feedback(conn, args.id, args.reason)
        elif args.cmd == "feedback-resolve":
            resolve_feedback(conn, args.id)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
