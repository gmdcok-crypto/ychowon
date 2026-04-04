/**
 * 초원농원 예약 현황판 - PWA DID
 * 시간 / 이름 / 호실 세로형 디스플레이
 */

(function () {
  'use strict';

  const API_BASE = '';
  const ROWS_PER_BLOCK = 15;
  const MIN_BLOCKS = 2;
  const blocksEl = document.getElementById('reservation-blocks');
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
    var url = (API_BASE || '') + '/api/reservations/today';
    fetch(url, { credentials: 'same-origin' })
      .then(function (r) { return r.json(); })
      .then(renderList)
      .catch(function () { renderList([]); });
  }

  function connectWs() {
    var protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    var host = window.location.host;
    var ws = new WebSocket(protocol + '//' + host + (API_BASE || '') + '/ws');
    ws.onmessage = function (ev) {
      try {
        var data = JSON.parse(ev.data);
        if (Array.isArray(data)) {
          renderList(data);
          return;
        }
        if (data && data.type === 'display_content' && typeof window.__displayApplyPayload === 'function') {
          window.__displayApplyPayload(data);
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

    function applyPayload(data) {
      var act = data && Array.isArray(data.active_slides) ? data.active_slides : [];
      var use = act.length ? act : FALLBACK;
      var key = slidesKey(use);
      if (key === lastKey && mediaEl.children.length) return;
      lastKey = key;
      startRotation(use);
    }

    function fetchContent() {
      var url = (API_BASE || '') + '/api/display/content';
      fetch(url, { credentials: 'same-origin' })
        .then(function (r) { return r.json(); })
        .then(applyPayload)
        .catch(function () {
          if (!mediaEl.children.length) {
            lastKey = '';
            startRotation(FALLBACK);
          }
        });
    }

    fetchContent();
    setInterval(fetchContent, 60 * 1000);

    window.__displayApplyPayload = function (data) {
      applyPayload(data);
    };
  })();

  connectWs();

  // PWA Service Worker
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('sw.js').catch(function () {});
  }
})();
