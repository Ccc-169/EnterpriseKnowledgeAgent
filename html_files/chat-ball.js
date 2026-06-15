/**
 * HNGD Chat Ball Widget
 * 使用方式：
 *   <script>
 *     window.HNGDChatConfig = { server: 'http://localhost:8000', token: 'hngd-embed-2024' };
 *   <\/script>
 *   <script src="http://localhost:8000/static/chat-ball.js"><\/script>
 */
(function () {
  'use strict';

  // ── 配置 ──────────────────────────────────────────────
  const _defaultServer = (window.APP_CONFIG && window.APP_CONFIG.api_base) || 'http://localhost:8000';
  const cfg = Object.assign(
    { server: _defaultServer, token: 'hngd-embed-2024' },
    window.HNGDChatConfig || {}
  );

  // ── CSS（注入到 Shadow DOM）───────────────────────────
  const STYLES = `
    :host { all: initial; }

    /* ── 悬浮球 ── */
    .hb-ball {
      position: fixed;
      right: 24px;
      bottom: 24px;
      width: 56px;
      height: 56px;
      border-radius: 50%;
      cursor: pointer;
      z-index: 2147483647;
      user-select: none;
      touch-action: none;
    }

    /* 渐变旋转层 */
    .hb-gradient {
      position: absolute;
      inset: 0;
      border-radius: 50%;
      background: conic-gradient(
        #4a7adc, #2a5aa8, #1a3a7e, #3a8ae8, #6aaaf8, #2a5aa8, #4a7adc
      );
      animation: hbSpin 4s linear infinite;
    }
    @keyframes hbSpin { to { transform: rotate(360deg); } }

    /* 内层遮罩，让渐变看起来更柔和 */
    .hb-inner {
      position: absolute;
      inset: 3px;
      border-radius: 50%;
      background: radial-gradient(circle at 35% 35%, #5a8ee8, #1a3a7e);
      display: flex;
      align-items: center;
      justify-content: center;
      box-shadow: inset 0 -3px 8px rgba(0,0,30,0.25);
    }

    /* 脉冲扩散环 */
    .hb-ring {
      position: absolute;
      inset: -4px;
      border-radius: 50%;
      border: 2px solid rgba(74,122,220,0.6);
      animation: hbRing 2.4s ease-out infinite;
      pointer-events: none;
    }
    @keyframes hbRing {
      0%   { transform: scale(1);    opacity: 0.7; }
      100% { transform: scale(1.65); opacity: 0;   }
    }

    /* 悬浮抖动 */
    .hb-ball {
      animation: hbFloat 3.8s ease-in-out infinite;
    }
    @keyframes hbFloat {
      0%, 100% { transform: translateY(0);   }
      50%       { transform: translateY(-5px); }
    }
    /* 拖拽时暂停抖动 */
    .hb-ball.dragging {
      animation: none;
      transition: none;
    }

    /* 球内图标 */
    .hb-icon {
      width: 26px;
      height: 26px;
      fill: white;
      flex-shrink: 0;
      filter: drop-shadow(0 1px 2px rgba(0,0,30,0.3));
    }

    /* ── 聊天面板 ── */
    .hb-panel {
      position: fixed;
      z-index: 2147483646;
      width: 320px;
      height: 420px;
      background: white;
      border-radius: 16px;
      box-shadow: 0 8px 32px rgba(10,30,80,0.18), 0 2px 8px rgba(10,30,80,0.1);
      display: flex;
      flex-direction: column;
      overflow: hidden;
      opacity: 0;
      transform: scale(0.92) translateY(8px);
      pointer-events: none;
      transition: opacity 0.2s ease, transform 0.2s ease;
    }
    .hb-panel.open {
      opacity: 1;
      transform: scale(1) translateY(0);
      pointer-events: auto;
    }

    /* 面板 header */
    .hb-ph {
      background: linear-gradient(135deg, #1a3a7e 0%, #2a5aa8 100%);
      padding: 12px 14px;
      display: flex;
      align-items: center;
      gap: 8px;
      flex-shrink: 0;
    }
    .hb-ph-icon {
      width: 28px; height: 28px;
      background: rgba(255,255,255,0.18);
      border-radius: 7px;
      display: flex; align-items: center; justify-content: center;
    }
    .hb-ph-icon svg { width: 16px; height: 16px; fill: white; }
    .hb-ph-title {
      flex: 1;
      font-size: 13.5px;
      font-weight: 700;
      color: white;
    }
    .hb-ph-close {
      width: 26px; height: 26px;
      border-radius: 6px;
      border: none;
      background: transparent;
      color: rgba(255,255,255,0.7);
      font-size: 18px;
      cursor: pointer;
      display: flex; align-items: center; justify-content: center;
      line-height: 1;
      transition: background 0.15s;
    }
    .hb-ph-close:hover { background: rgba(255,255,255,0.15); color: white; }

    /* 消息区 */
    .hb-msgs {
      flex: 1;
      overflow-y: auto;
      padding: 12px;
      display: flex;
      flex-direction: column;
      gap: 10px;
      background: #f4f7fb;
    }
    .hb-msgs::-webkit-scrollbar { width: 3px; }
    .hb-msgs::-webkit-scrollbar-thumb { background: #c4d4e8; border-radius: 2px; }

    /* 欢迎语 */
    .hb-welcome {
      text-align: center;
      color: #9aaac0;
      font-size: 12.5px;
      padding: 16px 8px;
      line-height: 1.6;
    }

    /* 气泡行 */
    .hb-row { display: flex; gap: 6px; max-width: 90%; }
    .hb-row.user { align-self: flex-end; flex-direction: row-reverse; }
    .hb-row.bot  { align-self: flex-start; }

    .hb-av {
      width: 24px; height: 24px; border-radius: 50%;
      font-size: 10px; font-weight: 700;
      display: flex; align-items: center; justify-content: center;
      flex-shrink: 0;
    }
    .hb-row.bot  .hb-av { background: linear-gradient(135deg,#2a5aa8,#4a7adc); color: white; }
    .hb-row.user .hb-av { background: #e0e8f4; color: #3a5a9a; }

    .hb-bbl {
      padding: 7px 11px;
      border-radius: 12px;
      font-size: 12.5px;
      line-height: 1.6;
      word-break: break-word;
      white-space: pre-wrap;
    }
    .hb-row.bot  .hb-bbl {
      background: white;
      color: #1a2a4a;
      border-radius: 3px 12px 12px 12px;
      box-shadow: 0 1px 3px rgba(30,60,120,0.08);
    }
    .hb-row.user .hb-bbl {
      background: linear-gradient(135deg,#2a5aa8,#3a6ec4);
      color: white;
      border-radius: 12px 3px 12px 12px;
    }

    /* 打字中 */
    .hb-typing {
      display: flex; align-items: center; gap: 3px;
      padding: 7px 11px;
      background: white; border-radius: 3px 12px 12px 12px;
      box-shadow: 0 1px 3px rgba(30,60,120,0.08);
    }
    .hb-dot {
      width: 6px; height: 6px; border-radius: 50%;
      background: #a0b8d8;
      animation: hbDot 1.2s ease-in-out infinite;
    }
    .hb-dot:nth-child(2) { animation-delay: 0.2s; }
    .hb-dot:nth-child(3) { animation-delay: 0.4s; }
    @keyframes hbDot {
      0%,80%,100% { transform: scale(0.7); opacity: 0.5; }
      40%         { transform: scale(1);   opacity: 1;   }
    }

    /* 单轮提示标签 */
    .hb-sep {
      text-align: center;
      font-size: 11px;
      color: #b0c0d8;
      padding: 4px 0;
    }

    /* 输入栏 */
    .hb-input-bar {
      background: white;
      border-top: 1px solid #e4eaf4;
      padding: 8px 10px;
      display: flex;
      gap: 7px;
      align-items: center;
    }
    .hb-input {
      flex: 1;
      height: 34px;
      padding: 6px 10px;
      border: 1.5px solid #dce8f4;
      border-radius: 8px;
      font-size: 12.5px;
      font-family: 'PingFang SC', 'Microsoft YaHei', sans-serif;
      color: #1a2a4a;
      outline: none;
      transition: border-color 0.15s;
    }
    .hb-input:focus { border-color: #2a5aa8; }
    .hb-input::placeholder { color: #a0b0c8; }

    .hb-send {
      width: 34px; height: 34px;
      background: #2a5aa8;
      border: none; border-radius: 8px;
      cursor: pointer;
      display: flex; align-items: center; justify-content: center;
      flex-shrink: 0;
      transition: background 0.15s;
    }
    .hb-send:hover:not(:disabled) { background: #1a3a7e; }
    .hb-send:disabled { background: #b8c8e0; cursor: default; }
    .hb-send svg { width: 16px; height: 16px; fill: white; }
  `;

  // ── DOM 构建 ───────────────────────────────────────────
  const host = document.createElement('div');
  host.id = 'hngd-chat-ball';
  document.body.appendChild(host);

  const shadow = host.attachShadow({ mode: 'open' });

  const styleEl = document.createElement('style');
  styleEl.textContent = STYLES;
  shadow.appendChild(styleEl);

  // 球
  const ball = document.createElement('div');
  ball.className = 'hb-ball';
  ball.innerHTML = `
    <div class="hb-ring"></div>
    <div class="hb-gradient"></div>
    <div class="hb-inner">
      <svg class="hb-icon" viewBox="0 0 24 24">
        <path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2z"/>
      </svg>
    </div>
  `;
  shadow.appendChild(ball);

  // 面板
  const panel = document.createElement('div');
  panel.className = 'hb-panel';
  panel.innerHTML = `
    <div class="hb-ph">
      <div class="hb-ph-icon">
        <svg viewBox="0 0 24 24"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2z"/></svg>
      </div>
      <span class="hb-ph-title">智能知识助手</span>
      <button class="hb-ph-close" id="hb-close">×</button>
    </div>
    <div class="hb-msgs" id="hb-msgs">
      <div class="hb-welcome">您好！有什么可以帮助您？<br>每次提问独立处理。</div>
    </div>
    <div class="hb-input-bar">
      <input class="hb-input" id="hb-input" type="text" placeholder="输入问题，按 Enter 发送…" maxlength="500">
      <button class="hb-send" id="hb-send">
        <svg viewBox="0 0 24 24"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg>
      </button>
    </div>
  `;
  shadow.appendChild(panel);

  // 取 shadow 内元素的快捷引用
  const $msgs  = shadow.getElementById('hb-msgs');
  const $input = shadow.getElementById('hb-input');
  const $send  = shadow.getElementById('hb-send');
  const $close = shadow.getElementById('hb-close');

  // ── 面板开关 ────────────────────────────────────────────
  let panelOpen = false;

  function openPanel() {
    panelOpen = true;
    panel.classList.add('open');
    _positionPanel();
    $input.focus();
  }

  function closePanel() {
    panelOpen = false;
    panel.classList.remove('open');
  }

  $close.addEventListener('click', closePanel);

  // ── 面板定位（紧贴球，自适应屏幕边缘）──────────────────
  function _positionPanel() {
    const br   = ball.getBoundingClientRect();
    const pw   = 320, ph = 420;
    const vpW  = window.innerWidth, vpH = window.innerHeight;
    const MARGIN = 10;

    // 水平：球在右侧 → 面板向左展开，否则向右
    let left = br.right + MARGIN < vpW - pw
      ? br.right + MARGIN              // 球左侧有空间：往右
      : br.left - pw - MARGIN;         // 往左

    // 若往左还是超出：贴左屏边
    if (left < MARGIN) left = MARGIN;
    // 若往右超出：贴右屏边
    if (left + pw > vpW - MARGIN) left = vpW - pw - MARGIN;

    // 垂直：底部对齐球底，若超出屏幕则上移
    let top = br.bottom - ph;
    if (top < MARGIN) top = MARGIN;
    if (top + ph > vpH - MARGIN) top = vpH - ph - MARGIN;

    panel.style.left = left + 'px';
    panel.style.top  = top  + 'px';
    panel.style.bottom = '';
    panel.style.right  = '';
  }

  // ── 拖拽逻辑 ────────────────────────────────────────────
  let _dragging = false, _dragMoved = false;
  let _startX, _startY, _ballX, _ballY;

  function _onPointerDown(e) {
    const src = e.touches ? e.touches[0] : e;
    _startX = src.clientX;
    _startY = src.clientY;
    const r = ball.getBoundingClientRect();
    _ballX  = r.left;
    _ballY  = r.top;
    _dragging  = true;
    _dragMoved = false;
    ball.classList.add('dragging');
    e.preventDefault();
  }

  function _onPointerMove(e) {
    if (!_dragging) return;
    const src = e.touches ? e.touches[0] : e;
    const dx  = src.clientX - _startX;
    const dy  = src.clientY - _startY;
    if (Math.abs(dx) > 4 || Math.abs(dy) > 4) _dragMoved = true;

    const vpW = window.innerWidth, vpH = window.innerHeight;
    const bw  = ball.offsetWidth,  bh  = ball.offsetHeight;
    const newX = Math.max(0, Math.min(_ballX + dx, vpW - bw));
    const newY = Math.max(0, Math.min(_ballY + dy, vpH - bh));

    ball.style.right  = '';
    ball.style.bottom = '';
    ball.style.left   = newX + 'px';
    ball.style.top    = newY + 'px';

    if (panelOpen) _positionPanel();
    e.preventDefault();
  }

  function _onPointerUp() {
    if (!_dragging) return;
    _dragging = false;
    ball.classList.remove('dragging');

    if (!_dragMoved) {
      // 点击：切换面板
      panelOpen ? closePanel() : openPanel();
    } else if (panelOpen) {
      _positionPanel();
    }
  }

  ball.addEventListener('mousedown',  _onPointerDown, { passive: false });
  ball.addEventListener('touchstart', _onPointerDown, { passive: false });
  document.addEventListener('mousemove',  _onPointerMove, { passive: false });
  document.addEventListener('touchmove',  _onPointerMove, { passive: false });
  document.addEventListener('mouseup',    _onPointerUp);
  document.addEventListener('touchend',   _onPointerUp);

  // ── 消息渲染 ────────────────────────────────────────────
  function _appendBubble(role, text) {
    const row = document.createElement('div');
    row.className = `hb-row ${role}`;
    const av = document.createElement('div');
    av.className = 'hb-av';
    av.textContent = role === 'bot' ? '智' : '我';
    const bbl = document.createElement('div');
    bbl.className = 'hb-bbl';
    bbl.textContent = text;
    row.appendChild(av);
    row.appendChild(bbl);
    $msgs.appendChild(row);
    $msgs.scrollTop = $msgs.scrollHeight;
  }

  function _appendSep() {
    const sep = document.createElement('div');
    sep.className = 'hb-sep';
    sep.textContent = '── 新对话 ──';
    $msgs.appendChild(sep);
    $msgs.scrollTop = $msgs.scrollHeight;
  }

  function _showTyping() {
    const row = document.createElement('div');
    row.className = 'hb-row bot';
    row.id = 'hb-typing';
    const av = document.createElement('div');
    av.className = 'hb-av';
    av.textContent = '智';
    const t = document.createElement('div');
    t.className = 'hb-typing';
    t.innerHTML = '<div class="hb-dot"></div><div class="hb-dot"></div><div class="hb-dot"></div>';
    row.appendChild(av); row.appendChild(t);
    $msgs.appendChild(row);
    $msgs.scrollTop = $msgs.scrollHeight;
  }

  function _removeTyping() {
    const el = shadow.getElementById('hb-typing');
    if (el) el.remove();
  }

  // ── 发送消息（单轮：每次新 UUID）──────────────────────
  let _busy = false;
  let _msgCount = 0; // 已有消息数，用于在首条前清除欢迎语

  async function _send() {
    const msg = $input.value.trim();
    if (!msg || _busy) return;
    _busy = true;
    $send.disabled = true;
    $input.value = '';

    // 第一条消息时清除欢迎语
    if (_msgCount === 0) {
      const welcome = $msgs.querySelector('.hb-welcome');
      if (welcome) welcome.remove();
    }
    // 非第一条时加分隔线（单轮提示）
    if (_msgCount > 0) _appendSep();
    _msgCount++;

    _appendBubble('user', msg);
    _showTyping();

    // 单轮：每次生成新 thread_id，不传给后端（后端自动生成）
    try {
      const res = await fetch(`${cfg.server}/api/embed/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message:     msg,
          embed_token: cfg.token,
          // 不传 thread_id → 后端每次生成新 UUID → 单轮模式
        }),
      });

      _removeTyping();

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        _appendBubble('bot', `请求失败（${res.status}）：${err.detail || '未知错误'}`);
      } else {
        const data = await res.json();
        _appendBubble('bot', data.response || '（无回复）');
      }
    } catch {
      _removeTyping();
      _appendBubble('bot', '网络错误，请检查服务是否运行。');
    }

    _busy = false;
    $send.disabled = false;
    $input.focus();
  }

  $send.addEventListener('click', _send);
  $input.addEventListener('keydown', e => {
    if (e.key === 'Enter') { e.preventDefault(); _send(); }
  });

})();
