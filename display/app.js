/**
 * 초원농원 예약 현황판 - PWA DID
 * 시간 / 이름 / 호실 세로형 디스플레이
 */

(function () {
  'use strict';

  const API_BASE = '';
  const BRANCH_KEY = 'reserve_branch_id';

  function getDisplayBranch() {
    try {
      var u = new URL(window.location.href);
      var b = u.searchParams.get('branch');
      if (b && String(b).trim()) {
        var id = String(b).trim().toLowerCase();
        try {
          localStorage.setItem(BRANCH_KEY, id);
        } catch (e) {}
        return id;
      }
    } catch (e) {}
    try {
      var v = localStorage.getItem(BRANCH_KEY);
      if (v && String(v).trim()) return String(v).trim().toLowerCase();
    } catch (e2) {}
    return typeof reserveInferDefaultBranch === 'function' ? reserveInferDefaultBranch() : 'default';
  }

  function branchQuery() {
    return 'branch=' + encodeURIComponent(getDisplayBranch());
  }

  function withBranch(url) {
    var sep = url.indexOf('?') >= 0 ? '&' : '?';
    return url + sep + branchQuery();
  }

  const ROWS_PER_BLOCK = 15;
  const MIN_BLOCKS = 2;
  const blocksEl = document.getElementById('reservation-blocks');
  const topContentAreaEl = document.getElementById('top-content-area');
  const dateEl = document.querySelector('.datetime .date');
  const timeEl = document.querySelector('.datetime .time');

  function formatDate(d) {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    const week = ['일', '월', '화', '수', '목', '금', '토'][d.getDay()];
    return `${y}.${m}.${day} (${week})`;
  }

  function formatTime(d) {
    return [d.getHours(), d.getMinutes(), d.getSeconds()]
      .map(function (n) { return String(n).padStart(2, '0'); })
      .join(':');
  }

  function updateClock() {
    var now = new Date();
    if (dateEl) dateEl.textContent = formatDate(now);
    if (timeEl) timeEl.textContent = formatTime(now);
  }

  function renderRow(item) {
    const row = document.createElement('div');
    row.className = 'row';
    row.setAttribute('data-id', item.id || '');
    const roomClass = (item.room && String(item.room).toUpperCase().includes('VIP')) ? 'col-room vip' : 'col-room';
    row.innerHTML =
      '<div class="col col-time">' + (item.time || '—') + '</div>' +
      '<div class="col col-name">' + (item.name || '—') + '</div>' +
      '<div class="col ' + roomClass + '">' + (item.room || '—') + '</div>';
    return row;
  }

  function renderEmptyRow() {
    const row = document.createElement('div');
    row.className = 'row empty-row';
    row.innerHTML =
      '<div class="col col-time">—</div>' +
      '<div class="col col-name">—</div>' +
      '<div class="col col-room">—</div>';
    return row;
  }

  function renderList(items) {
    if (!blocksEl) return;
    var list = Array.isArray(items) ? items : [];
    if (typeof window.__displaySetReservations === 'function') {
      window.__displaySetReservations(list);
    }
    var chunks = [];
    for (var i = 0; i < list.length; i += ROWS_PER_BLOCK) {
      chunks.push(list.slice(i, i + ROWS_PER_BLOCK));
    }
    if (chunks.length === 0) chunks.push([]);
    while (chunks.length < MIN_BLOCKS) {
      chunks.push([]);
    }
    blocksEl.innerHTML = '';
    chunks.forEach(function (chunk) {
      var block = document.createElement('div');
      block.className = 'block';
      var header = document.createElement('div');
      header.className = 'table-header';
      header.innerHTML =
        '<div class="col col-time">시간</div>' +
        '<div class="col col-name">이름</div>' +
        '<div class="col col-room">호실</div>';
      var body = document.createElement('div');
      body.className = 'table-body';
      chunk.forEach(function (item) {
        body.appendChild(renderRow(item));
      });
      var needEmpty = ROWS_PER_BLOCK - chunk.length;
      for (var j = 0; j < needEmpty; j++) {
        body.appendChild(renderEmptyRow());
      }
      block.appendChild(header);
      block.appendChild(body);
      blocksEl.appendChild(block);
    });
  }

  function fetchReservations() {
    var url = withBranch((API_BASE || '') + '/api/reservations/today');
    fetch(url, { credentials: 'same-origin' })
      .then(function (r) { return r.json(); })
      .then(renderList)
      .catch(function () { renderList([]); });
  }

  function connectWs() {
    var protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    var host = window.location.host;
    var ws = new WebSocket(protocol + '//' + host + (API_BASE || '') + '/ws?' + branchQuery());
    ws.onmessage = function (ev) {
      try {
        var data = JSON.parse(ev.data);
        if (Array.isArray(data)) {
          renderList(data);
          return;
        }
        if (data && data.type === 'display_content') {
          if (typeof window.__displayApplyTopContentPayload === 'function') {
            window.__displayApplyTopContentPayload(data);
          }
          if (typeof window.__displayApplyBottomContentPayload === 'function') {
            window.__displayApplyBottomContentPayload(data);
          }
        }
      } catch (e) {}
    };
    ws.onclose = function () {
      setTimeout(connectWs, 1000);
    };
    ws.onerror = function () {
      ws.close();
    };
  }

  updateClock();
  setInterval(updateClock, 1000);
  fetchReservations();
  setInterval(fetchReservations, 5 * 1000);

  /* 전체화면: 브라우저 정책상 사용자 클릭/터치 후에만 대부분 허용 → pointerdown으로 유도 */
  (function () {
    function goFullscreen() {
      var el = document.documentElement;
      var req =
        el.requestFullscreen ||
        el.webkitRequestFullscreen ||
        el.webkitRequestFullScreen ||
        el.msRequestFullscreen;
      if (!req) return;
      req.call(el).catch(function () {});
    }
    function tryFullscreen() {
      if (document.fullscreenElement) return;
      goFullscreen();
    }
    tryFullscreen();
    setTimeout(tryFullscreen, 500);
    setTimeout(tryFullscreen, 1500);
    setTimeout(tryFullscreen, 3000);
    document.body.addEventListener(
      'pointerdown',
      function () {
        if (!document.fullscreenElement) goFullscreen();
      },
      { once: true }
    );
  })();

  /* 광고 슬라이드: 이미지는 표시 시간 후 전환, 동영상은 재생 종료(ended) 후 전환 */
  (function () {
    var mediaEl = document.getElementById('top-content-media');
    if (!mediaEl || !blocksEl || !topContentAreaEl) return;
    var slides = [];
    var reservations = null;
    var lastKey = '';
    var rotateTimer = null;
    var idx = 0;

    function videoMime(url) {
      var u = String(url || '').toLowerCase();
      if (u.indexOf('.webm') !== -1) return 'video/webm';
      if (u.indexOf('.ogg') !== -1) return 'video/ogg';
      return 'video/mp4';
    }

    function slidesKey(list) {
      return JSON.stringify((list || []).map(function (s) {
        if (s.type === 'video') return { type: 'video', url: s.url };
        return { type: 'image', url: s.url, duration_sec: s.duration_sec };
      }));
    }

    function buildSlidesFromItems(items, defaultIntervalSec) {
      var di = parseInt(defaultIntervalSec, 10);
      if (isNaN(di)) di = 8;
      di = Math.max(3, Math.min(600, di));
      var out = [];
      (items || []).forEach(function (it) {
        var url = it && it.url != null ? String(it.url).trim() : '';
        if (!url) return;
        var t = (it.type || 'image').toLowerCase();
        if (t === 'video') {
          out.push({ type: 'video', url: url });
          return;
        }
        var dur = di;
        if (it.duration_sec != null && it.duration_sec !== '' && !isNaN(parseInt(it.duration_sec, 10))) {
          dur = Math.max(3, Math.min(600, parseInt(it.duration_sec, 10)));
        }
        out.push({ type: 'image', url: url, duration_sec: dur });
      });
      return out;
    }

    function clearRotation() {
      if (rotateTimer) {
        clearTimeout(rotateTimer);
        rotateTimer = null;
      }
    }

    function pauseAllVideos() {
      mediaEl.querySelectorAll('video').forEach(function (node) {
        node.pause();
        try {
          node.currentTime = 0;
        } catch (e) {}
      });
    }

    function syncVisibility() {
      var hasReservationData = Array.isArray(reservations);
      var showTopContent = hasReservationData && !reservations.length && slides.length > 0;
      blocksEl.hidden = showTopContent;
      topContentAreaEl.hidden = !showTopContent;
      if (!showTopContent) {
        clearRotation();
        pauseAllVideos();
      } else if (slides.length) {
        showCurrent();
      }
    }

    function buildElements(list) {
      mediaEl.innerHTML = '';
      list.forEach(function (s) {
        var el;
        if (s.type === 'video') {
          el = document.createElement('video');
          el.className = 'top-content-slide';
          el.muted = true;
          el.loop = false;
          el.playsInline = true;
          var src = document.createElement('source');
          src.src = s.url;
          src.type = videoMime(s.url);
          el.appendChild(src);
        } else {
          el = document.createElement('img');
          el.className = 'top-content-slide';
          el.alt = '';
          el.src = s.url;
        }
        mediaEl.appendChild(el);
      });
    }

    function advance() {
      if (!slides.length) return;
      idx = (idx + 1) % slides.length;
      showCurrent();
    }

    function showCurrent() {
      clearRotation();
      if (topContentAreaEl.hidden) return;
      var els = mediaEl.querySelectorAll('.top-content-slide');
      if (!els.length || !slides.length) return;
      var cur = slides[idx];
      var el = els[idx];
      els.forEach(function (node, i) {
        node.classList.toggle('active', i === idx);
        if (node.tagName.toLowerCase() === 'video' && i !== idx) {
          node.pause();
          try {
            node.currentTime = 0;
          } catch (e) {}
        }
      });
      if (!el || !cur) return;
      if (cur.type === 'video') {
        var onDone = function () {
          advance();
        };
        el.addEventListener('ended', onDone, { once: true });
        el.addEventListener('error', onDone, { once: true });
        try {
          el.currentTime = 0;
        } catch (e2) {}
        var playPromise = el.play();
        if (playPromise && typeof playPromise.catch === 'function') {
          playPromise.catch(function () {
            rotateTimer = setTimeout(advance, 3000);
          });
        }
        return;
      }
      var sec = cur.duration_sec != null ? Number(cur.duration_sec) : 8;
      if (isNaN(sec)) sec = 8;
      rotateTimer = setTimeout(advance, Math.max(3000, Math.min(600000, sec * 1000)));
    }

    function startRotation(list) {
      clearRotation();
      slides = list && list.length ? list.slice() : [];
      idx = 0;
      buildElements(slides);
      syncVisibility();
    }

    function applyPayload(data, force) {
      var act = data && Array.isArray(data.active_top_slides) ? data.active_top_slides : [];
      if (!act.length && data && Array.isArray(data.top_items) && data.top_items.length) {
        act = buildSlidesFromItems(data.top_items, data.top_default_interval_sec);
      }
      var key = slidesKey(act);
      if (!force && key === lastKey && mediaEl.children.length) {
        syncVisibility();
        return;
      }
      lastKey = key;
      startRotation(act);
    }

    window.__displaySetReservations = function (list) {
      reservations = Array.isArray(list) ? list.slice() : [];
      syncVisibility();
    };

    window.__displayApplyTopContentPayload = function (data) {
      applyPayload(data, false);
    };
  })();

  (function () {
    var mediaEl = document.getElementById('ad-media');
    if (!mediaEl) return;
    var FALLBACK = [
      { type: 'video', url: 'https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4' }
    ];
    var lastKey = '';
    var rotateTimer = null;
    var slides = [];
    var idx = 0;

    function videoMime(url) {
      var u = String(url || '').toLowerCase();
      if (u.indexOf('.webm') !== -1) return 'video/webm';
      if (u.indexOf('.ogg') !== -1) return 'video/ogg';
      return 'video/mp4';
    }

    function slidesKey(list) {
      return JSON.stringify(list.map(function (s) {
        if (s.type === 'video') {
          return { type: 'video', url: s.url };
        }
        return { type: 'image', url: s.url, duration_sec: s.duration_sec };
      }));
    }

    /** active_slides 가 비어 있을 때 서버 items 로 복구 (DB·API 불일치 대비) */
    function buildSlidesFromItems(items, defaultIntervalSec) {
      var di = parseInt(defaultIntervalSec, 10);
      if (isNaN(di)) di = 8;
      di = Math.max(3, Math.min(600, di));
      var out = [];
      (items || []).forEach(function (it) {
        var url = it && it.url != null ? String(it.url).trim() : '';
        if (!url) return;
        var t = (it.type || 'image').toLowerCase();
        if (t === 'video') {
          out.push({ type: 'video', url: url });
        } else {
          var durRaw = it.duration_sec;
          var durI = di;
          if (durRaw != null && durRaw !== '' && !isNaN(parseInt(durRaw, 10))) {
            durI = Math.max(3, Math.min(600, parseInt(durRaw, 10)));
          }
          out.push({ type: 'image', url: url, duration_sec: durI });
        }
      });
      return out;
    }

    function clearRotation() {
      if (rotateTimer) {
        clearTimeout(rotateTimer);
        rotateTimer = null;
      }
    }

    function buildElements(list) {
      mediaEl.innerHTML = '';
      list.forEach(function (s) {
        var el;
        if (s.type === 'video') {
          el = document.createElement('video');
          el.className = 'ad-slide';
          el.setAttribute('data-ad-slide', '');
          el.muted = true;
          el.loop = false;
          el.playsInline = true;
          var src = document.createElement('source');
          src.src = s.url;
          src.type = videoMime(s.url);
          el.appendChild(src);
        } else {
          el = document.createElement('img');
          el.className = 'ad-slide';
          el.setAttribute('data-ad-slide', '');
          el.alt = '';
          el.src = s.url;
        }
        mediaEl.appendChild(el);
      });
    }

    function advance() {
      if (!slides.length) return;
      idx = (idx + 1) % slides.length;
      showCurrent();
    }

    function showCurrent() {
      clearRotation();
      var els = mediaEl.querySelectorAll('[data-ad-slide]');
      if (!els.length || !slides.length) return;
      var cur = slides[idx];
      var el = els[idx];
      els.forEach(function (node, i) {
        node.classList.toggle('active', i === idx);
        if (node.tagName.toLowerCase() === 'video') {
          if (i !== idx) {
            node.pause();
            try {
              node.currentTime = 0;
            } catch (e) {}
          }
        }
      });
      if (!el || !cur) return;

      var isVideo = cur.type === 'video' || el.tagName.toLowerCase() === 'video';
      if (isVideo) {
        el.loop = false;
        try {
          el.currentTime = 0;
        } catch (e2) {}
        var onDone = function () {
          advance();
        };
        el.addEventListener('ended', onDone, { once: true });
        el.addEventListener('error', onDone, { once: true });
        var p = el.play();
        if (p && typeof p.catch === 'function') {
          p.catch(function () {
            rotateTimer = setTimeout(advance, 3000);
          });
        }
        return;
      }

      var sec = cur.duration_sec != null ? Number(cur.duration_sec) : 8;
      if (isNaN(sec)) sec = 8;
      var durMs = Math.max(3000, Math.min(600000, sec * 1000));
      rotateTimer = setTimeout(advance, durMs);
    }

    function startRotation(list) {
      clearRotation();
      slides = list && list.length ? list.slice() : FALLBACK.slice();
      buildElements(slides);
      idx = 0;
      showCurrent();
    }

    function applyPayload(data, force) {
      var act = data && Array.isArray(data.active_slides) ? data.active_slides : [];
      if (!act.length && data && Array.isArray(data.items) && data.items.length) {
        act = buildSlidesFromItems(data.items, data.default_interval_sec);
      }
      var use = act.length ? act : FALLBACK;
      var key = slidesKey(use);
      if (!force && key === lastKey && mediaEl.children.length) return;
      lastKey = key;
      startRotation(use);
    }

    function fetchContent() {
      var base = withBranch((API_BASE || '') + '/api/display/content');
      var url = base + (base.indexOf('?') >= 0 ? '&' : '?') + '_=' + Date.now();
      fetch(url, { credentials: 'same-origin', cache: 'no-store' })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (typeof window.__displayApplyTopContentPayload === 'function') {
            window.__displayApplyTopContentPayload(data);
          }
          applyPayload(data, true);
        })
        .catch(function () {
          if (!mediaEl.children.length) {
            lastKey = '';
            startRotation(FALLBACK);
          }
        });
    }

    fetchContent();
    setInterval(fetchContent, 15 * 1000);

    window.__displayApplyBottomContentPayload = function (data) {
      applyPayload(data, false);
    };
  })();

  connectWs();

  // PWA Service Worker
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('sw.js').catch(function () {});
  }
})();
