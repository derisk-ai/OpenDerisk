# -*- coding: utf-8 -*-
"""11 镜的声明式场景 spec（几何单一源，交给 pv_page 构造页）。

每镜内容与已核准剧本一致，只重表达为 nodes(矩形) / edges(node id) / annos /
运动(只动 opacity/transform/glow，不动节点几何与边端点)。运动中需要迁移的元素
（如共享执行世界换底）采用「淡出旧、淡入新」而非拖动带边的节点，避免边端点与
移动节点错位 —— 见 shot_09。
"""

# ---------- Shot 1: 范式立论 ----------
def shot_01_spec(W, H, D):
    px = [128, 576, 1024, 1472]
    plugins = ["模型适配器", "工具注册表", "会话日志", "agent loop"]
    pillX = [255, 810, 1365]
    pillNames = ["去特权化", "可逆即默认", "声明优于编排"]
    pillCols = ["cyan", "purple", "green"]
    nodes = []
    for i in range(4):
        nodes.append({"id": "np%d" % i, "label": plugins[i], "x": px[i], "y": 210,
                      "w": 320, "h": 110, "color": "cyan"})
    for i in range(3):
        nodes.append({"id": "pp%d" % i, "label": pillNames[i], "sub": "支柱 %d" % (i + 1),
                      "x": pillX[i], "y": 660, "w": 300, "h": 220, "color": pillCols[i]})
    edges = [{"id": "en01", "from": "np0", "to": "np1", "color": "cyan"},
             {"id": "en13", "from": "np1", "to": "np3", "color": "cyan"},
             {"id": "en02", "from": "np0", "to": "np2", "color": "cyan"},
             {"id": "en23", "from": "np2", "to": "np3", "color": "cyan"},
             {"id": "en12", "from": "np1", "to": "np2", "color": "cyan"}]
    annos = [
        {"id": "kik", "text": "范式论题 · 一次架构范式变革", "x": 0, "y": 0, "w": W, "align": "center", "size": 30, "color": "magenta", "cls": "kicker"},
        {"id": "tit", "text": [("dsh", None), (" · ", None), ("三根支柱", "magenta"), (" 撑起整座系统", None)], "x": 0, "y": 0, "w": W, "align": "center", "size": 50, "cls": "title"},
        {"id": "big", "text": "万物皆插件", "x": 0, "y": 430, "w": W, "align": "center", "size": 120, "color": "magenta"},
        {"id": "sub", "text": "no privileged core · 连 agent loop 自身都是插件", "x": 0, "y": 580, "w": W, "align": "center", "size": 28, "color": "cyan"},
    ]
    seek_setup = "var big=doc('big'),sub=doc('sub');"
    # 注：__N/__E 已由构造器自动收集；doc 只是 document.getElementById 的别名
    seek_setup = "function doc(i){return document.getElementById(i);} var big=doc('big'),sub=doc('sub');"
    seek = """
      doc('kik').style.opacity=ease(c01(t/0.8));
      doc('tit').style.opacity=ease(c01((t-0.4)/0.8));
      for (var i=0;i<4;i++){var a=ease(c01((t-1.2-i*0.2)/0.7));__N['np'+i].style.opacity=a;__N['np'+i].style.transform='translateY('+((1-a)*30)+'px)';__N['np'+i].style.boxShadow='0 0 '+(14+8*Math.sin(t*2.4+i))+'px #00F0FF';}
      for (var j=0;j<3;j++){var a=ease(c01((t-2.0-j*0.25)/0.8));__N['pp'+j].style.opacity=a;__N['pp'+j].style.transform='translateY('+((1-a)*40)+'px)';__N['pp'+j].style.boxShadow='0 0 '+(16+8*Math.sin(t*2.4+j))+'px '+'#00F0FF,#7C3AED,#00FF9F'.split(',')[j];}
      var eids=['en01','en13','en02','en23','en12'];
      for (var k=0;k<eids.length;k++){var fl=Math.max(0,Math.sin(t*1.6+pseudo(k)*6.28))*ease(c01((t-2.8)/1.0));__E[eids[k]].style.opacity=(fl*0.8).toFixed(3);}
      var bp=c01(t/0.7), jit=(1-bp)*Math.sin(t*90)*10;
      big.style.opacity=ease(c01((t-0.2)/0.5));big.style.transform='translateX('+jit+'px)';
      var p=0.75+0.25*Math.sin(t*2.4);big.style.textShadow='0 0 '+(20*p)+'px #FF2E97,0 0 '+(56*p)+'px #FF2E97';
      sub.style.opacity=ease(c01((t-3.0)/0.9));
"""
    return {"kicker": None, "title": None, "nodes": nodes, "edges": edges, "annos": annos,
            "seek_setup": seek_setup, "seek": seek}


# ---------- Shot 2: 去特权化 ----------
def shot_02_spec(W, H, D):
    nodes = [
        {"id": "consumer", "label": "消费者插件", "x": 80, "y": 470, "w": 300, "h": 140, "color": "magenta"},
        {"id": "c0", "label": "ctx.tools", "x": 820, "y": 360, "w": 300, "h": 80, "color": "purple", "mono": True},
        {"id": "c1", "label": "ctx.llm", "x": 820, "y": 460, "w": 300, "h": 80, "color": "purple", "mono": True},
        {"id": "c2", "label": "ctx.sessions", "x": 820, "y": 560, "w": 300, "h": 80, "color": "purple", "mono": True},
        {"id": "c3", "label": "ctx.fs", "x": 820, "y": 660, "w": 300, "h": 80, "color": "purple", "mono": True},
        {"id": "impl", "label": "fs-local", "x": 1320, "y": 660, "w": 300, "h": 110, "color": "green", "mono": True},
    ]
    edges = [
        {"id": "ln_get", "from": "consumer", "to": "c3", "color": "cyan"},
        {"id": "ln_res", "from": "c3", "to": "impl", "color": "green"},
        {"id": "ln_imp", "from": "consumer", "to": "impl", "color": "magenta", "dashed": True},
    ]
    raw = ('<div id="ctxbox" style="position:absolute;left:780px;top:320px;width:380px;height:460px;'
           'border:2px dashed #00F0FF;border-radius:24px;opacity:0;"></div>'
           '<div id="ctxlabel" style="position:absolute;left:780px;top:288px;width:380px;text-align:center;'
           'font-size:34px;color:#00F0FF;opacity:0;">ctx 仓库</div>'
           '<div id="impx" style="position:absolute;left:560px;top:540px;font-size:60px;color:#FF2E97;'
           'font-weight:bold;opacity:0;text-shadow:0 0 14px #FF2E97;">✕</div>')
    annos = [
        {"id": "kik", "text": "支柱一 · 去特权化", "x": 0, "y": 0, "w": W, "align": "center", "size": 30, "color": "magenta", "cls": "kicker"},
        {"id": "tit", "text": [("按 ", None), ("ctx key", "cyan"), (" 找服务，而非 import", "magenta")], "x": 0, "y": 0, "w": W, "align": "center", "size": 50, "cls": "title"},
        {"id": "flipn", "text": "fs-local → fs-e2b（实现可换，消费者不变）", "x": 1180, "y": 810, "w": 700, "align": "center", "size": 26, "color": "green"},
    ]
    seek = """
      doc('kik').style.opacity=ease(c01(t/0.8));doc('tit').style.opacity=ease(c01((t-0.4)/0.8));
      __N['consumer'].style.opacity=ease(c01((t-1.0)/0.8));__N['consumer'].style.boxShadow='0 0 '+(14+8*Math.sin(t*2.4))+'px #FF2E97';
      doc('ctxbox').style.opacity=ease(c01((t-1.4)/0.7));doc('ctxlabel').style.opacity=ease(c01((t-1.6)/0.7));
      for (var i=0;i<4;i++){__N['c'+i].style.opacity=ease(c01((t-1.8-i*0.22)/0.6));}
      __E['ln_get'].style.opacity=ease(c01((t-2.8)/0.7));
      __E['ln_res'].style.opacity=ease(c01((t-3.2)/0.6));__N['impl'].style.opacity=ease(c01((t-3.4)/0.6));
      var imp=c01((t-3.8)/0.5), kill=c01((t-4.6)/0.5);
      __E['ln_imp'].style.opacity=ease(imp)*(1-ease(kill));
      doc('impx').style.opacity=ease(kill);doc('impx').style.transform='translate('+(kill*Math.sin(t*60)*10)+'px,0) rotate('+(kill*8)+'deg)';
      var flip=c01((t-6.2)/1.0);
      __N['impl'].style.transform='rotateY('+(ease(flip)*180)+'deg)';
      __N['impl'].querySelector('.lab').textContent = flip>0.5 ? 'fs-e2b' : 'fs-local';
      __N['impl'].style.borderColor= flip>0.5?'#7C3AED':'#00FF9F';
      __N['impl'].style.boxShadow= flip>0.5?'0 0 16px #7C3AED':'0 0 16px #00FF9F';
      doc('flipn').style.opacity=ease(c01((t-6.6)/0.8));
"""
    return {"kicker": None, "title": None, "nodes": nodes, "edges": edges, "annos": annos,
            "raw": raw, "seek_setup": "function doc(i){return document.getElementById(i);}", "seek": seek}


# ---------- Shot 3: inject DAG ----------
def shot_03_spec(W, H, D):
    nodes = [
        {"id": "n_llm", "label": "ctx.llm", "x": 1280, "y": 360, "w": 240, "h": 120, "color": "cyan", "mono": True},
        {"id": "n_ses", "label": "ctx.sessions", "x": 1280, "y": 680, "w": 280, "h": 120, "color": "cyan", "mono": True},
        {"id": "n_plg", "label": "某插件", "x": 680, "y": 540, "w": 280, "h": 140, "color": "purple"},
    ]
    edges = [
        {"id": "e_lm", "from": "n_llm", "to": "n_plg", "color": "cyan"},
        {"id": "e_ses", "from": "n_ses", "to": "n_plg", "color": "cyan"},
    ]
    raw = ('<svg id="extra" style="position:absolute;inset:0;width:100%%;height:100%%;pointer-events:none" viewBox="0 0 %d %d">'
           '<circle id="ring" cx="820" cy="610" r="86" fill="none" stroke="#FF2E97" stroke-width="6" '
           'stroke-dasharray="540" opacity="0"/></svg>' % (W, H))
    annos = [
        {"id": "kik", "text": "支柱二 · 声明优于编排", "x": 0, "y": 0, "w": W, "align": "center", "size": 30, "color": "magenta", "cls": "kicker"},
        {"id": "tit", "text": [("inject 声明依赖，就绪才挂载", "cyan")], "x": 0, "y": 0, "w": W, "align": "center", "size": 50, "cls": "title"},
        {"id": "inj", "text": "inject:&nbsp;[llm,&nbsp;sessions]", "x": 680, "y": 700, "w": 280, "align": "center", "size": 24, "color": "green"},
        {"id": "boot", "text": "手写 boot 序列 · 脆弱", "x": 60, "y": 300, "w": 360, "align": "center", "size": 26, "color": "magenta"},
        {"id": "b0", "text": "① 加载持久化", "x": 80, "y": 360, "w": 320, "size": 24, "color": "gray"},
        {"id": "b1", "text": "② 加载工具", "x": 80, "y": 420, "w": 320, "size": 24, "color": "gray"},
        {"id": "b2", "text": "③ 加载模型", "x": 80, "y": 480, "w": 320, "size": 24, "color": "gray"},
        {"id": "ck0", "text": "✓", "x": 1570, "y": 392, "w": 60, "size": 44, "color": "green"},
        {"id": "ck1", "text": "✓", "x": 1570, "y": 712, "w": 60, "size": 44, "color": "green"},
    ]
    seek = """
      doc('kik').style.opacity=ease(c01(t/0.8));doc('tit').style.opacity=ease(c01((t-0.4)/0.8));
      doc('boot').style.opacity=ease(c01((t-1.2)/0.7));
      for (var i=0;i<3;i++){var sp=doc('b'+i);sp.style.opacity=ease(c01((t-1.6+i*0.3)/0.5));sp.style.textDecoration='line-through';sp.style.textDecorationColor='rgba(255,46,151,'+ease(c01((t-1.8+i*0.3)/0.5))+')';}
      __N['n_llm'].style.opacity=ease(c01((t-2.6)/0.7));__N['n_llm'].style.boxShadow='0 0 '+(14+8*Math.sin(t*2.4))+'px #00F0FF';
      __N['n_ses'].style.opacity=ease(c01((t-3.0)/0.7));__N['n_ses'].style.boxShadow='0 0 '+(14+8*Math.sin(t*2.4+1))+'px #00F0FF';
      doc('ck0').style.opacity=ease(c01((t-3.6)/0.5));doc('ck1').style.opacity=ease(c01((t-4.0)/0.5));
      __E['e_lm'].style.opacity=ease(c01((t-3.8)/0.6));__E['e_ses'].style.opacity=ease(c01((t-4.2)/0.6));
      __N['n_plg'].style.opacity=ease(c01((t-3.2)/0.7));doc('inj').style.opacity=ease(c01((t-3.6)/0.6));
      var ready=(t>4.3);
      if(!ready){__N['n_plg'].style.borderColor='#FF2E97';__N['n_plg'].style.boxShadow='0 0 '+(18*(0.4+0.4*Math.sin(t*2.2)))+'px #FF2E97';doc('ring').style.opacity='0.9';doc('ring').style.strokeDashoffset=(540*(1-c01(t*1.2)%1)).toFixed(1);}
      else{doc('ring').style.opacity='0';__N['n_plg'].style.borderColor='#00FF9F';__N['n_plg'].style.boxShadow='0 0 '+(16+8*Math.sin(t*3))+'px #00FF9F';var act=c01((t-4.3)/0.5);__N['n_plg'].style.transform='translateX('+((1-act)*Math.sin(t*70)*8)+'px)';}
"""
    return {"kicker": None, "title": None, "nodes": nodes, "edges": edges, "annos": annos,
            "raw": raw, "seek_setup": "function doc(i){return document.getElementById(i);}", "seek": seek}


# ---------- Shot 4: 四派发模式 ----------
def shot_04_spec(W, H, D):
    nodes = [
        {"id": "c1", "html": '<div class="lab c-cyan">emit</div><div class="sub">观察广播 · 不 await · 无返回</div>', "x": 40, "y": 180, "w": 900, "h": 380, "color": "cyan"},
        {"id": "c2", "html": '<div class="lab c-magenta">waterfall</div><div class="sub">经 next 委托 · 不 await · 有返回</div>', "x": 980, "y": 180, "w": 900, "h": 380, "color": "magenta"},
        {"id": "c3", "html": '<div class="lab c-purple">parallel</div><div class="sub">全并发 · await · 无返回</div>', "x": 40, "y": 600, "w": 900, "h": 300, "color": "purple"},
        {"id": "c4", "html": '<div class="lab c-green">serial</div><div class="sub">顺序 · await · 有返回</div>', "x": 980, "y": 600, "w": 900, "h": 300, "color": "green"},
    ]
    # 各格演示元素（raw，置于格子内）
    raw = (
      '<div id="em_src" style="position:absolute;left:200px;top:360px;width:30px;height:30px;border-radius:50%;background:#00F0FF;box-shadow:0 0 16px #00F0FF;opacity:0;"></div>'
      '<div id="em_w" style="position:absolute;left:215px;top:375px;width:0;height:0;border:3px solid #00F0FF;border-radius:50%;opacity:0;"></div>'
      '<div id="wf_ball" style="position:absolute;left:1040px;top:345px;width:26px;height:26px;border-radius:50%;background:#FF2E97;box-shadow:0 0 16px #FF2E97;opacity:0;"></div>'
      '<div class="wlay" id="wl0" style="position:absolute;left:1240px;top:230px;width:5px;height:280px;background:#FF2E97;opacity:0.35;"></div>'
      '<div class="wlay" id="wl1" style="position:absolute;left:1400px;top:230px;width:5px;height:280px;background:#FF2E97;opacity:0.35;"></div>'
      '<div class="wlay" id="wl2" style="position:absolute;left:1560px;top:230px;width:5px;height:280px;background:#FF2E97;opacity:0.35;"></div>'
      '<div id="pl0" style="position:absolute;left:200px;bottom:auto;top:820px;width:80px;height:0;background:linear-gradient(180deg,#7C3AED,#00F0FF);border-radius:8px;"></div>'
      '<div id="pl1" style="position:absolute;left:360px;top:820px;width:80px;height:0;background:linear-gradient(180deg,#7C3AED,#00F0FF);border-radius:8px;"></div>'
      '<div id="pl2" style="position:absolute;left:520px;top:820px;width:80px;height:0;background:linear-gradient(180deg,#7C3AED,#00F0FF);border-radius:8px;"></div>'
      '<div id="pl3" style="position:absolute;left:680px;top:820px;width:80px;height:0;background:linear-gradient(180deg,#7C3AED,#00F0FF);border-radius:8px;"></div>'
      '<div id="sr_n0" style="position:absolute;left:1060px;top:700px;width:30px;height:30px;border-radius:50%;background:#00FF9F;opacity:0.4;"></div>'
      '<div id="sr_n1" style="position:absolute;left:1260px;top:700px;width:30px;height:30px;border-radius:50%;background:#00FF9F;opacity:0.4;"></div>'
      '<div id="sr_n2" style="position:absolute;left:1460px;top:700px;width:30px;height:30px;border-radius:50%;background:#00FF9F;opacity:0.4;"></div>'
      '<div id="sr_n3" style="position:absolute;left:1660px;top:700px;width:30px;height:30px;border-radius:50%;background:#00FF9F;opacity:0.4;"></div>'
      '<div id="sr_ball" style="position:absolute;left:1070px;top:708px;width:16px;height:16px;border-radius:50%;background:#fff;box-shadow:0 0 14px #00FF9F;opacity:0;"></div>'
      '<div id="sr_val" style="position:absolute;left:1000px;top:840px;width:900px;text-align:center;font-size:36px;font-family:SF Mono,Menlo,monospace;color:#00FF9F;opacity:0;">ret = 0</div>'
    )
    annos = [
        {"id": "kik", "text": "类型化事件 · @mode 派发", "x": 0, "y": 0, "w": W, "align": "center", "size": 30, "color": "magenta", "cls": "kicker"},
        {"id": "tit", "text": [("emit", "cyan"), (" · ", None), ("waterfall", "magenta"), (" · ", None), ("parallel", "purple"), (" · ", None), ("serial", "green")], "x": 0, "y": 0, "w": W, "align": "center", "size": 50, "cls": "title"},
    ]
    seek = """
      doc('kik').style.opacity=ease(c01(t/0.7));doc('tit').style.opacity=ease(c01((t-0.3)/0.7));
      for (var i=0;i<4;i++){__N['c'+(i+1)].style.opacity=ease(c01((t-0.8-i*0.4)/0.7));}
      // emit 波纹
      var w=(t*0.7)%1.4/1.4,dia=w*620;var we=doc('em_w');we.style.width=dia+'px';we.style.height=dia+'px';we.style.left=(215-dia/2)+'px';we.style.top=(375-dia/2)+'px';we.style.opacity=(1-w)*0.8;doc('em_src').style.opacity=ease(c01((t-1.2)/0.5));
      // waterfall 穿层
      var seg=t/D,wb=doc('wf_ball'),px;
      if(seg<0.5) px=1040+ease(seg/0.5)*560;
      else if(seg<0.62){var bk=ease((seg-0.5)/0.12);px=1600-bk*240;}
      else px=1040+ease((seg-0.62)/0.38)*560;
      wb.style.left=px+'px';wb.style.opacity=ease(c01((t-1.6)/0.5));
      [1240,1400,1560].forEach(function(lx,i){var n=Math.abs(px-lx)<40?1:0.35;doc('wl'+i).style.opacity=n;doc('wl'+i).style.boxShadow=n>0.9?'0 0 12px #FF2E97':'none';});
      // parallel 四柱齐进
      var pg=ease(c01((t-1.8)/(D-2.8)));
      ['pl0','pl1','pl2','pl3'].forEach(function(id,i){var el=doc(id);el.style.height=(pg*180*(1+0.05*Math.sin(t*3+i)))+'px';el.style.opacity=pg;});
      // serial 顺序跳
      var srs=c01((t-2.2)/(D-3.2)),idx=Math.min(3,Math.floor(srs*4)),loc=c01(srs*4-idx),nx=[1075,1275,1475,1675],sb=doc('sr_ball');
      sb.style.left=(nx[idx]-8+(idx<3?loc*192:0))+'px';sb.style.opacity=ease(c01((t-2.4)/0.5));
      for(var s=0;s<4;s++){doc('sr_n'+s).style.opacity=(s<=idx?1:0.4);doc('sr_n'+s).style.boxShadow=(s<=idx?'0 0 12px #00FF9F':'none');}
      var sv=doc('sr_val');sv.style.opacity=ease(c01((t-2.6)/0.5));sv.textContent='ret = '+(idx+(idx<3?Math.floor(loc):1));
"""
    return {"kicker": None, "title": None, "nodes": nodes, "edges": [], "annos": annos,
            "raw": raw, "seek_setup": "function doc(i){return document.getElementById(i);}", "seek": seek}


# ---------- Shot 5: 可逆即默认 ----------
def shot_05_spec(W, H, D):
    nodes = [
        {"id": "plugin", "label": "插件 Plugin", "x": 810, "y": 800, "w": 300, "h": 120, "color": "cyan"},
        {"id": "b0", "label": "prompt 片段", "x": 430, "y": 330, "w": 240, "h": 90, "color": "cyan"},
        {"id": "b1", "label": "工具 schema", "x": 840, "y": 330, "w": 240, "h": 90, "color": "magenta"},
        {"id": "b2", "label": "监听器 on()", "x": 1250, "y": 330, "w": 240, "h": 90, "color": "purple"},
        {"id": "d0", "label": "disposer ①", "x": 1560, "y": 330, "w": 300, "h": 64, "color": "green", "mono": True},
        {"id": "d1", "label": "disposer ②", "x": 1560, "y": 540, "w": 300, "h": 64, "color": "green", "mono": True},
        {"id": "d2", "label": "disposer ③", "x": 1560, "y": 750, "w": 300, "h": 64, "color": "green", "mono": True},
    ]
    edges = [
        {"id": "l0", "from": "plugin", "to": "b0", "color": "cyan"},
        {"id": "l1", "from": "plugin", "to": "b1", "color": "magenta"},
        {"id": "l2", "from": "plugin", "to": "b2", "color": "purple"},
    ]
    annos = [
        {"id": "kik", "text": "支柱三 · 可逆即默认", "x": 0, "y": 0, "w": W, "align": "center", "size": 30, "color": "magenta", "cls": "kicker"},
        {"id": "tit", "text": [("effect / on 返回 disposer，卸载逆序撤销", "cyan")], "x": 0, "y": 0, "w": W, "align": "center", "size": 50, "cls": "title"},
        {"id": "phase", "text": "", "x": 0, "y": 690, "w": W, "align": "center", "size": 30, "color": "cyan"},
    ]
    seek = """
      doc('kik').style.opacity=ease(c01(t/0.8));doc('tit').style.opacity=ease(c01((t-0.4)/0.8));
      __N['plugin'].style.opacity=ease(c01((t-1.0)/0.8));__N['plugin'].style.boxShadow='0 0 '+(14+8*Math.sin(t*2.4))+'px #00F0FF';
      var unload=5.4, mT=[1.4,2.2,3.0], bcol=['#00F0FF','#FF2E97','#C4B5FD'];
      var ph=doc('phase');ph.style.opacity=ease(c01((t-1.6)/0.6));ph.style.color=unload<t?'#FF2E97':'#00F0FF';ph.textContent=unload<t?'卸载中 · 逆序调用 disposer':'注册即副作用 · 返回 disposer';
      var uT=[unload+1.2,unload+0.6,unload+0.0];
      for (var i=0;i<3;i++){
        if (t<unload){var m=ease(c01((t-mT[i])/(unload-mT[i]-1)));__N['b'+i].style.opacity=m;__N['b'+i].style.transform='translateY('+((1-m)*-40)+'px)';__E['l'+i].style.opacity=m*0.7;__N['d'+i].style.opacity=ease(c01((t-mT[i]-0.4)/0.6));}
        else {var u=ease(c01((t-uT[i])/0.7));__N['b'+i].style.opacity=1-u;__N['b'+i].style.transform='translateY('+((u)*40)+'px)';__E['l'+i].style.opacity=(1-u)*0.7;__N['d'+i].style.opacity=1-u;__N['d'+i].style.transform='translateX('+(u*100)+'px) rotate('+(u*8)+'deg)';}
        __N['b'+i].style.boxShadow='0 0 '+(10+6*Math.sin(t*2.4+i))+'px '+bcol[i];
      }
"""
    return {"kicker": None, "title": None, "nodes": nodes, "edges": edges, "annos": annos,
            "seek_setup": "function doc(i){return document.getElementById(i);}", "seek": seek}


# ---------- Shot 6: 启动即组合 ----------
def shot_06_spec(W, H, D):
    layers = [
        ("dsh-base", "模型·工具·持久化·沙箱·审批", "第1层 base", "cyan"),
        ("dsh-web · dsh-headless", "bundle 按 profile 序堆叠", "第2层 bundle", "purple"),
        ("profile 补丁", "用户自有 out-of-tree 插件", "第3层 patch", "magenta"),
        ("home 补丁", "Harness home 家目录级覆盖", "第4层 home", "magenta"),
        ("--patch overlay", "命令行最高优先级覆盖", "第5层 CLI", "magenta"),
    ]
    nodes = []
    for i, (name, sub, metric, col) in enumerate(layers):
        nodes.append({"id": "ly%d" % i, "label": name, "sub": sub, "x": 320, "y": 200 + i * 120,
                      "w": 900, "h": 96, "color": col})
    nodes.append({"id": "prio", "label": "覆盖优先级 ↑", "x": 1280, "y": 200, "w": 300, "h": 96, "color": "green", "mono": True})
    edges = []
    annos = [
        {"id": "kik", "text": "启动即组合 · 分层覆盖", "x": 0, "y": 0, "w": W, "align": "center", "size": 30, "color": "magenta", "cls": "kicker"},
        {"id": "tit", "text": [("空条目 → bundle → patch，补丁按 id 整行替换", "cyan")], "x": 0, "y": 0, "w": W, "align": "center", "size": 50, "cls": "title"},
        {"id": "empty", "text": "entries = [ ]", "x": 60, "y": 760, "w": 400, "size": 30, "color": "gray"},
        {"id": "repl", "text": "", "x": 320, "y": 860, "w": 900, "align": "center", "size": 28, "color": "green"},
    ]
    seek = """
      doc('kik').style.opacity=ease(c01(t/0.8));doc('tit').style.opacity=ease(c01((t-0.4)/0.8));
      doc('empty').style.opacity=ease(c01((t-1.0)/0.6));
      for (var i=0;i<5;i++){var a=ease(c01((t-1.4-i*0.5)/0.7));__N['ly'+i].style.opacity=a;__N['ly'+i].style.transform='translateX('+((1-a)*120)+'px)';}
      __N['prio'].style.opacity=ease(c01((t-4.0)/0.6));
      var r=ease(c01((t-6.0)/1.2));doc('repl').style.opacity=r;doc('repl').textContent='patch 按 id 定位 row → 整行替换 replace-whole-config';
      __N['ly0'].style.borderColor = t>7?'#00FF9F':'#00F0FF';__N['ly0'].style.boxShadow = t>7?'0 0 16px #00FF9F':'none';
"""
    return {"kicker": None, "title": None, "nodes": nodes, "edges": edges, "annos": annos,
            "seek_setup": "function doc(i){return document.getElementById(i);}", "seek": seek}


# ---------- Shot 7: agent loop 横向时间线 ----------
def shot_07_spec(W, H, D):
    # 10 节点： (id, label, x, durable)
    ev = [
        ("t0", "turn/start", 40, True),
        ("t1", "claim", 220, False),
        ("t2", "agent/pre-step", 410, False),
        ("t3", "step/start", 600, True),
        ("t4", "llm/stream", 790, False),
        ("t5", "tool/call", 970, True),
        ("t6", "tool/result", 1140, True),
        ("t7", "step/end", 1310, True),
        ("t8", "turn-stopping", 1480, False),
        ("t9", "turn/end", 1660, True),
    ]
    nodes = []
    for (eid, lab, x, dur) in ev:
        nodes.append({"id": eid, "label": (lab if dur else lab), "x": x, "y": (440 if dur else 620),
                      "w": 170, "h": 70, "color": ("cyan" if dur else "magenta"), "mono": True})
    gate = '<div id="gate" style="position:absolute;left:455px;top:478px;width:120px;height:120px;border:2px solid #FF2E97;transform:rotate(45deg);background:rgba(255,46,151,0.1);opacity:0;"></div>'
    ball = '<div id="ball" style="position:absolute;width:22px;height:22px;border-radius:50%;background:#fff;box-shadow:0 0 16px #00F0FF;top:534px;"></div>'
    track = '<div id="track" style="position:absolute;left:40px;top:548px;width:1840px;height:4px;background:rgba(255,255,255,0.14);"></div>'
    chunks = ''.join('<div class="chunk" id="ck%d" style="position:absolute;left:%dpx;top:300px;width:120px;height:40px;border-radius:8px;background:rgba(124,58,237,0.2);border:1px solid #7C3AED;font-size:22px;display:flex;align-items:center;justify-content:center;opacity:0;">chunk</div>' % (i, 880 + i * 140) for i in range(3))
    tcards = '<div id="tc0" style="position:absolute;left:950px;top:740px;width:150px;height:60px;border-radius:10px;border:2px solid #00F0FF;background:rgba(0,240,255,0.08);font-size:24px;display:flex;align-items:center;justify-content:center;opacity:0;">工具A</div><div id="tc1" style="position:absolute;left:1120px;top:740px;width:150px;height:60px;border-radius:10px;border:2px solid #00F0FF;background:rgba(0,240,255,0.08);font-size:24px;display:flex;align-items:center;justify-content:center;opacity:0;">工具B</div>'
    ring = '<svg style="position:absolute;inset:0;width:100%%;height:100%%;pointer-events:none" viewBox="0 0 %d %d"><circle id="ring" cx="1215" cy="555" r="36" fill="none" stroke="#00FF9F" stroke-width="6" stroke-dasharray="226" opacity="0"/></svg>' % (W, H)
    reject = '<div id="reject" style="position:absolute;left:400px;top:380px;font-size:22px;color:#FF2E97;font-family:SF Mono,monospace;opacity:0;">✕ reject → 零步 turn 仍落底</div>'
    raw = gate + ball + track + chunks + tcards + ring + reject
    annos = [
        {"id": "kik", "text": "agent loop · turn 与 step", "x": 0, "y": 0, "w": W, "align": "center", "size": 30, "color": "magenta", "cls": "kicker"},
        {"id": "tit", "text": [("pre-step", "cyan"), (" 决定模型实际看到哪些消息", None)], "x": 0, "y": 0, "w": W, "align": "center", "size": 50, "cls": "title"},
        {"id": "legend", "text": "● 持久 session 事件  ● 实时 agent 事件", "x": 40, "y": 880, "w": 800, "size": 26, "color": "gray"},
    ]
    seek_setup = ("function doc(i){return document.getElementById(i);} "
                  "var ids=['t0','t1','t2','t3','t4','t5','t6','t7','t8','t9']; "
                  "var cx=ids.map(function(i){return __geo.nodes[i].cx;}); "
                  "var lightAt=[0.5,1.3,2.1,2.9,3.7,4.6,5.6,6.4,7.2,8.2]; "
                  "var cols=['#00F0FF','#FF2E97','#FF2E97','#00F0FF','#FF2E97','#00F0FF','#00F0FF','#00F0FF','#FF2E97','#00F0FF'];")
    seek = """
      doc('kik').style.opacity=ease(c01(t/0.7));doc('tit').style.opacity=ease(c01((t-0.3)/0.7));doc('legend').style.opacity=ease(c01((t-1.0)/0.6));
      var prog=ease(c01(t/(D-0.6)));var bx=40+prog*1840;doc('ball').style.left=bx+'px';
      for (var i=0;i<10;i++){var on=t>lightAt[i];__N[ids[i]].style.opacity=on?1:0;__N[ids[i]].style.boxShadow=on?'0 0 10px '+cols[i]:'none';__N[ids[i]].style.borderColor=on?cols[i]:'#3E5570';}
      doc('gate').style.opacity=ease(c01((t-2.1)/0.5));
      doc('reject').style.opacity=ease(c01((t-2.6)/0.4))*(1-ease(c01((t-3.2)/0.4)));
      for (var c=0;c<3;c++){doc('ck'+c).style.opacity=ease(c01((t-3.9-c*0.25)/0.5));}
      var tCon=ease(c01((t-4.6)/0.5));doc('tc0').style.opacity=tCon;doc('tc1').style.opacity=tCon;
      var rp=ease(c01((t-4.9)/0.7));doc('ring').setAttribute('opacity',(rp*0.9).toFixed(2));doc('ring').style.strokeDashoffset=(226*(1-rp)).toFixed(1);
"""
    return {"kicker": None, "title": None, "nodes": nodes, "edges": [], "annos": annos,
            "raw": raw, "seek_setup": seek_setup, "seek": seek}


# ---------- Shot 8: session log ----------
def shot_08_spec(W, H, D):
    evnames = ["user/message", "assistant/chunk", "assistant/message", "tool/call", "tool/result"]
    nodes = []
    for i, nm in enumerate(evnames):
        nodes.append({"id": "ev%d" % i, "label": nm, "x": 60, "y": 210 + i * 104, "w": 360, "h": 84, "color": "cyan", "mono": True})
    nodes.append({"id": "dm", "label": "deriveMessages()", "x": 600, "y": 460, "w": 380, "h": 120, "color": "green", "mono": True})
    nodes.append({"id": "m0", "label": "user", "x": 1060, "y": 230, "w": 420, "h": 80, "color": "purple"})
    nodes.append({"id": "m1", "label": "assistant", "x": 1060, "y": 430, "w": 420, "h": 80, "color": "purple"})
    nodes.append({"id": "m2", "label": "tool/call → result", "x": 1060, "y": 530, "w": 420, "h": 80, "color": "purple", "mono": True})
    brnames = ["fork 分叉", "续跑 resume", "转写 transcript", "遥测 telemetry", "持久化 persistence"]
    for i, nm in enumerate(brnames):
        nodes.append({"id": "br%d" % i, "label": nm, "x": 1560, "y": 200 + i * 92, "w": 320, "h": 70, "color": "cyan"})
    edges = [{"id": "ge", "from": "ev2", "to": "dm", "color": "cyan"}, {"id": "gm", "from": "dm", "to": "m1", "color": "green"}] + \
            [{"id": "gb%d" % i, "from": "dm", "to": "br%d" % i, "color": "cyan"} for i in range(5)]
    raw = '<div id="bad" style="position:absolute;left:60px;top:780px;width:360px;height:80px;border-radius:12px;border:2px solid #FF2E97;background:rgba(255,46,151,0.12);display:flex;align-items:center;font-size:24px;padding-left:18px;color:#FF2E97;opacity:0;">✕ 试图改写/插入</div>'
    annos = [
        {"id": "kik", "text": "session log · 模型可见即已记录", "x": 0, "y": 0, "w": W, "align": "center", "size": 30, "color": "magenta", "cls": "kicker"},
        {"id": "tit", "text": [("只增日志 → ", None), ("deriveMessages", "green"), (" 投影 → 流派生", None)], "x": 0, "y": 0, "w": W, "align": "center", "size": 50, "cls": "title"},
        {"id": "iron", "text": "模型可见 ⟺ 已记录", "x": 600, "y": 350, "w": 380, "align": "center", "size": 30, "color": "magenta"},
        {"id": "ap", "text": "append-only · 永不改写", "x": 460, "y": 880, "w": 400, "size": 24, "color": "gray"},
    ]
    seek_setup = "function doc(i){return document.getElementById(i);}"
    seek = """
      doc('kik').style.opacity=ease(c01(t/0.7));doc('tit').style.opacity=ease(c01((t-0.3)/0.7));
      var ip=0.7+0.3*Math.sin(t*2.4);doc('iron').style.opacity=ease(c01((t-0.8)/0.7));doc('iron').style.textShadow='0 0 '+(16*ip)+'px #FF2E97';
      var evAt=[1.2,2.0,2.8,3.6,4.4];
      for (var i=0;i<5;i++){var a=ease(c01((t-evAt[i])/0.5));__N['ev'+i].style.opacity=a;__N['ev'+i].style.transform='translateY('+((1-a)*40)+'px)';}
      doc('ap').style.opacity=ease(c01((t-5.0)/0.6));
      var bA=ease(c01((t-6.0)/0.4)),bK=ease(c01((t-6.6)/0.5));doc('bad').style.opacity=bA*(1-bK);doc('bad').style.transform='translateX('+(-bK*60)+'px) rotate('+(-bK*12)+'deg)';
      __N['dm'].style.opacity=ease(c01((t-2.0)/0.6));__N['dm'].style.transform='scaleY('+(0.95+0.05*Math.sin(t*3))+')';
      var mAt=[1.6,3.2,4.2];for (var j=0;j<3;j++){__N['m'+j].style.opacity=ease(c01((t-mAt[j])/0.5));}
      __E['ge'].style.opacity=ease(c01((t-3.0)/0.5));__E['gm'].style.opacity=ease(c01((t-3.4)/0.5));
      for (var k=0;k<5;k++){__E['gb'+k].style.opacity=ease(c01((t-7.0-k*0.25)/0.5));__N['br'+k].style.opacity=ease(c01((t-7.2-k*0.25-pseudo(k)*0.15)/0.5));__N['br'+k].style.transform='translateX('+((1-ease(c01((t-7.0-k*0.25)/0.5)))*50)+'px)';}
"""
    return {"kicker": None, "title": None, "nodes": nodes, "edges": edges, "annos": annos,
            "raw": raw, "seek_setup": seek_setup, "seek": seek}


# ---------- Shot 9: capability seam ----------
def shot_09_spec(W, H, D):
    nodes = [
        {"id": "deff", "label": "Service Definition", "sub": "声明接口", "x": 90, "y": 300, "w": 380, "h": 150, "color": "cyan"},
        {"id": "prov", "label": "Service Provider", "sub": "fs-local", "x": 760, "y": 300, "w": 380, "h": 150, "color": "magenta"},
        {"id": "cons", "label": "Consumer", "sub": "常是模型工具", "x": 1430, "y": 300, "w": 380, "h": 150, "color": "purple"},
        {"id": "world", "label": "共享执行世界", "x": 760, "y": 580, "w": 380, "h": 120, "color": "green"},
        {"id": "cap0", "label": "ctx.fs", "x": 380, "y": 720, "w": 200, "h": 64, "color": "cyan", "mono": True},
        {"id": "cap1", "label": "ctx.subprocess", "x": 1060, "y": 720, "w": 280, "h": 64, "color": "cyan", "mono": True},
        {"id": "ci0", "label": "Bash", "x": 1430, "y": 560, "w": 180, "h": 60, "color": "purple"},
        {"id": "ci1", "label": "PTY", "x": 1430, "y": 640, "w": 180, "h": 60, "color": "purple"},
        {"id": "ci2", "label": "LSP", "x": 1430, "y": 720, "w": 180, "h": 60, "color": "purple"},
    ]
    edges = [
        {"id": "il1", "from": "deff", "to": "prov", "color": "cyan"},
        {"id": "il2", "from": "prov", "to": "cons", "color": "purple"},
        {"id": "wl1", "from": "cap0", "to": "world", "color": "cyan"},
        {"id": "wl2", "from": "cap1", "to": "world", "color": "cyan"},
    ]
    raw = '<div id="cloud" style="position:absolute;left:1240px;top:560px;font-size:80px;opacity:0;">☁</div>'
    annos = [
        {"id": "kik", "text": "capability seam · 一换底整套搬", "x": 0, "y": 0, "w": W, "align": "center", "size": 30, "color": "magenta", "cls": "kicker"},
        {"id": "tit", "text": [("三角色 + ", None), ("共享执行世界", "green")], "x": 0, "y": 0, "w": W, "align": "center", "size": 50, "cls": "title"},
        {"id": "note", "text": "一键把 Bash / PTY / LSP 搬去远程沙箱 · 无需 provider 分叉", "x": 0, "y": 850, "w": W, "align": "center", "size": 30, "color": "green"},
        {"id": "swapn", "text": "fs-local → fs-e2b", "x": 760, "y": 880, "w": 380, "align": "center", "size": 24, "color": "magenta"},
    ]
    seek = """
      doc('kik').style.opacity=ease(c01(t/0.7));doc('tit').style.opacity=ease(c01((t-0.3)/0.7));
      __N['deff'].style.opacity=ease(c01((t-1.0)/0.7));__N['prov'].style.opacity=ease(c01((t-1.6)/0.7));__N['cons'].style.opacity=ease(c01((t-2.2)/0.7));
      __E['il1'].style.opacity=ease(c01((t-2.8)/0.6))*(0.6+0.4*Math.sin(t*2));__E['il2'].style.opacity=ease(c01((t-3.2)/0.6))*(0.6+0.4*Math.sin(t*2+1));
      __N['world'].style.opacity=ease(c01((t-3.8)/0.7));__N['world'].style.boxShadow='0 0 '+(16+8*Math.sin(t*2.4))+'px #00FF9F';
      __N['cap0'].style.opacity=ease(c01((t-4.2)/0.5));__N['cap1'].style.opacity=ease(c01((t-4.6)/0.5));
      __E['wl1'].style.opacity=ease(c01((t-4.4)/0.5));__E['wl2'].style.opacity=ease(c01((t-4.8)/0.5));
      var sw=c01((t-6.4)/1.0), mig=ease(c01((t-7.2)/0.9));
      __N['prov'].querySelector('.sub').textContent = sw>0.5?'fs-e2b':'fs-local';
      __N['prov'].style.borderColor=sw>0.5?'#7C3AED':'#FF2E97';__N['prov'].style.background=sw>0.5?'rgba(124,58,237,0.16)':'rgba(255,255,255,0.04)';
      __N['world'].style.opacity=ease(c01((t-3.8)/0.7))*(1-mig*0.9);__E['wl1'].style.opacity*=1-mig;__E['wl2'].style.opacity*=1-mig;
      doc('cloud').style.opacity=mig;doc('cloud').style.transform='translateY('+(-Math.sin(t*3)*8)+'px)';
      doc('swapn').style.opacity=ease(c01((t-6.6)/0.6));
      for (var i=0;i<3;i++){__N['ci'+i].style.opacity=ease(c01((t-6.8-i*0.2)/0.5));__N['ci'+i].style.boxShadow=(t>7.0+i*0.2)?'0 0 14px #7C3AED':'none';}
      doc('note').style.opacity=ease(c01((t-8.6)/0.8));doc('note').style.textShadow='0 0 '+(12+8*Math.sin(t*2.4))+'px #00FF9F';
"""
    return {"kicker": None, "title": None, "nodes": nodes, "edges": edges, "annos": annos,
            "raw": raw, "seek_setup": "function doc(i){return document.getElementById(i);}", "seek": seek}


# ---------- Shot 10: tool 流水线 ----------
def shot_10_spec(W, H, D):
    g = [("pre-execute", "钩子 / 权限 / 沙箱", "cyan"), ("单调守卫", "deny / abstain", "magenta"),
         ("tools/execute", "超时 / 重试 / 指标", "purple"), ("post-execute", "accept / block / replace", "green"),
         ("tools/result", "冻结权威", "cyan")]
    gx = [60, 430, 820, 1230, 1620]
    nodes = []
    for i, (nm, sub, col) in enumerate(g):
        nodes.append({"id": "g%d" % i, "label": nm, "sub": sub, "x": gx[i], "y": 420, "w": 280, "h": 320, "color": col, "mono": (nm in ("tools/execute", "post-execute", "tools/result"))})
    raw = ('<div id="track" style="position:absolute;left:60px;top:600px;width:1840px;height:4px;background:rgba(255,255,255,0.12);"></div>'
           '<div id="ball" style="position:absolute;width:38px;height:38px;border-radius:50%;background:#fff;box-shadow:0 0 18px #00F0FF;top:581px;left:60px;"></div>'
           '<div id="lock" style="position:absolute;left:550px;top:510px;font-size:38px;opacity:0;">🔒</div>'
           '<div id="gear" style="position:absolute;left:920px;top:500px;font-size:80px;color:#FF2E97;opacity:0;text-shadow:0 0 16px #FF2E97;">⚙</div>'
           '<div id="ice" style="position:absolute;left:1710px;top:500px;font-size:64px;color:#00F0FF;opacity:0;text-shadow:0 0 16px #00F0FF;">❄</div>')
    annos = [
        {"id": "kik", "text": "tool execution pipeline · 不可乱序", "x": 0, "y": 0, "w": W, "align": "center", "size": 30, "color": "magenta", "cls": "kicker"},
        {"id": "tit", "text": [("tool/call 闯五关 → ", None), ("冻结 result", "cyan")], "x": 0, "y": 0, "w": W, "align": "center", "size": 50, "cls": "title"},
    ]
    seek_setup = ("function doc(i){return document.getElementById(i);} "
                  "var gx=[200,570,960,1370,1760]; var gateAt=[1.2,2.6,4.2,6.6,8.6]; "
                  "var segs=[0,1.6,3.2,5.4,7.4,9.2,D]; var gcol=['#00F0FF','#FF2E97','#7C3AED','#00FF9F','#00F0FF'];")
    seek = """
      doc('kik').style.opacity=ease(c01(t/0.7));doc('tit').style.opacity=ease(c01((t-0.3)/0.7));
      var i=0;while(i<6 && t>=segs[i+1]) i++;var loc=c01((t-segs[i])/(segs[i+1]-segs[i]));
      var bx=gx[Math.max(0,i)]+(i<5?ease(loc)*(gx[i+1]-gx[i]):0);doc('ball').style.left=bx+'px';
      for (var k=0;k<5;k++){var on=t>gateAt[k];__N['g'+k].style.opacity=on?1:0.4;__N['g'+k].style.borderColor=on?gcol[k]:'#3E5570';__N['g'+k].style.boxShadow=on?'0 0 16px '+gcol[k]:'none';}
      doc('lock').style.opacity=ease(c01((t-2.6)/0.5));
      var ge=c01((t-4.2)/0.5)*(1-c01((t-6.4)/0.4));doc('gear').style.opacity=ge;doc('gear').style.transform='rotate('+((t*220)%360)+'deg)';
      doc('ice').style.opacity=ease(c01((t-8.6)/0.5));doc('ice').style.transform='scale('+(1+0.1*Math.sin(t*2))+')';
      if(t>8.6){doc('ball').style.background='#00F0FF';doc('ball').style.boxShadow='0 0 22px #00F0FF';}
"""
    return {"kicker": None, "title": None, "nodes": nodes, "edges": [], "annos": annos,
            "raw": raw, "seek_setup": seek_setup, "seek": seek}


# ---------- Shot 11: 范式回响 ----------
def shot_11_spec(W, H, D):
    pillX = [255, 810, 1365]
    pillNames = ["去特权化", "可逆即默认", "声明优于编排"]
    pillCols = ["cyan", "purple", "green"]
    nodes = []
    for i in range(3):
        nodes.append({"id": "pp%d" % i, "label": pillNames[i], "sub": "支柱 %d" % (i + 1), "x": pillX[i], "y": 130, "w": 300, "h": 180, "color": pillCols[i]})
    items_l = ["· 心智门槛高（从声明反推，无核心流程图）", "· 中间态自净窗口（服务消失→子树自净→重跑）", "· O(F) 广播而非 O(命中) 通知"]
    items_r = ["· agent 改自己运行时成为一等能力", "· 可逆测试世界：装插件→断言→卸载回滚", "· 热替换是产权问题，而非性能问题"]
    for i in range(3):
        nodes.append({"id": "il%d" % i, "label": items_l[i], "x": 140, "y": 380 + i * 84, "w": 660, "h": 72, "color": "magenta"})
        nodes.append({"id": "ir%d" % i, "label": items_r[i], "x": 1080, "y": 380 + i * 84, "w": 660, "h": 72, "color": "green"})
    annos = [
        {"id": "kik", "text": "范式回响 · 一问收束", "x": 0, "y": 0, "w": W, "align": "center", "size": 30, "color": "magenta", "cls": "kicker"},
        {"id": "hc1", "text": "诚实的代价", "x": 140, "y": 340, "w": 660, "size": 32, "color": "magenta"},
        {"id": "hc2", "text": "有趣的变化", "x": 1080, "y": 340, "w": 660, "size": 32, "color": "green"},
        {"id": "question", "text": "框架会消亡吗？", "x": 0, "y": 700, "w": W, "align": "center", "size": 60, "color": "magenta"},
        {"id": "qsub", "text": "还是只是从编译期特权，挪到了装配期顺序？", "x": 0, "y": 790, "w": W, "align": "center", "size": 30, "color": "cyan"},
    ]
    seek_setup = "function doc(i){return document.getElementById(i);} var pc=['#00F0FF','#7C3AED','#00FF9F'];"
    seek = """
      doc('kik').style.opacity=ease(c01(t/0.7));
      for (var i=0;i<3;i++){var a=ease(c01((t-0.3-i*0.2)/1.0));__N['pp'+i].style.opacity=a;__N['pp'+i].style.transform='translateY('+((1-a)*30)+'px)';__N['pp'+i].style.boxShadow='0 0 '+(16+8*Math.sin(t*2.4+i))+'px '+pc[i];}
      doc('hc1').style.opacity=ease(c01((t-1.2)/0.6));doc('hc2').style.opacity=ease(c01((t-1.4)/0.6));
      for (var k=0;k<3;k++){var la=ease(c01((t-1.6-k*0.35)/0.6)),ra=ease(c01((t-1.7-k*0.35)/0.6));__N['il'+k].style.opacity=la;__N['il'+k].style.transform='translateX('+((1-la)*50)+'px)';__N['ir'+k].style.opacity=ra;__N['ir'+k].style.transform='translateX('+((1-ra)*50)+'px)';}
      var bp=c01((t-3.8)/0.6),jit=(1-bp)*Math.sin(t*90)*10;doc('question').style.opacity=ease(c01((t-3.8)/0.5));doc('question').style.transform='translateX('+jit+'px) scale('+(1+0.05*Math.sin(t*1.5))+')';
      var p=0.75+0.25*Math.sin(t*2.4);doc('question').style.textShadow='0 0 '+(22*p)+'px #FF2E97,0 0 '+(60*p)+'px #FF2E97';
      doc('qsub').style.opacity=ease(c01((t-4.6)/0.8));
"""
    return {"kicker": None, "title": None, "nodes": nodes, "edges": [], "annos": annos,
            "seek_setup": seek_setup, "seek": seek}
