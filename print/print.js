(function () {
  'use strict';

  var API_TODAY_RESERVATIONS = '/api/reservations/today';
  var BRANCH_KEY = 'reserve_branch_id';

  var listEl = document.getElementById('print-list');
  var statusEl = document.getElementById('print-status');
  var dateLabelEl = document.getElementById('print-date-label');
  var toastEl = document.getElementById('print-toast');
  var refreshBtn = document.getElementById('print-refresh-btn');

  var reservations = [];
  var selectedFilter = 'all';
  var printWs = null;

  function getBranch() {
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
    } catch (e2) {}
    try {
      var v = localStorage.getItem(BRANCH_KEY);
      if (v && String(v).trim()) return String(v).trim().toLowerCase();
    } catch (e3) {}
    return typeof reserveInferDefaultBranch === 'function' ? reserveInferDefaultBranch() : 'default';
  }

  function branchQuery() {
    return 'branch=' + encodeURIComponent(getBranch());
  }

  function withBranch(url) {
    var sep = url.indexOf('?') >= 0 ? '&' : '?';
    return url + sep + branchQuery();
  }

  function dateKey(d) {
    return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
  }

  function formatDate(d) {
    var y = d.getFullYear();
    var m = String(d.getMonth() + 1).padStart(2, '0');
    var day = String(d.getDate()).padStart(2, '0');
    var week = ['일', '월', '화', '수', '목', '금', '토'][d.getDay()];
    return y + '.' + m + '.' + day + ' (' + week + ')';
  }

  function timeSlot(timeText) {
    var hour = parseInt((timeText || '').split(':')[0], 10);
    if (hour >= 12 && hour <= 14) return 'lunch';
    if (hour >= 17 && hour <= 19) return 'dinner';
    return 'other';
  }

  function escapeHtml(text) {
    return String(text || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function normalizeRoomLabel(value) {
    return String(value || '').replace(/\s+/g, ' ').trim();
  }

  function parseRooms(rawRooms, rawRoom) {
    var values = [];
    if (Array.isArray(rawRooms)) values = rawRooms.slice();
    else if (rawRooms != null && String(rawRooms).trim()) values = [rawRooms];
    else if (rawRoom != null && String(rawRoom).trim()) values = [rawRoom];
    var out = [];
    values.forEach(function (raw) {
      String(raw || '').split(',').forEach(function (part) {
        var room = normalizeRoomLabel(part);
        if (!room || out.indexOf(room) >= 0) return;
        out.push(room);
      });
    });
    return out;
  }

  function roomTextFromItem(item) {
    var rooms = parseRooms(item && item.rooms, item && item.room);
    return rooms.length ? rooms.join(', ') : '—';
  }

  function partyLine(item) {
    var a = item && item.adult;
    var c = item && item.child;
    var i = item && item.infant;
    if (a == null && c == null && i == null) {
      return item && item.count != null ? String(item.count) + '명' : '—';
    }
    var parts = [];
    if (a) parts.push('어른 ' + a);
    if (c) parts.push('어린이 ' + c);
    if (i) parts.push('유아 ' + i);
    return parts.length ? parts.join(', ') : (item && item.count != null ? String(item.count) + '명' : '—');
  }

  function receiptPartyLine(item) {
    var a = item && item.adult;
    var c = item && item.child;
    var i = item && item.infant;
    if (a == null && c == null && i == null) {
      return item && item.count != null ? '총 ' + String(item.count) + '명' : '—';
    }
    var parts = [];
    if (a != null) parts.push('성인 ' + (parseInt(a, 10) || 0) + '명');
    if (c != null) parts.push('어린이 ' + (parseInt(c, 10) || 0) + '명');
    if (i != null) parts.push('유아 ' + (parseInt(i, 10) || 0) + '명');
    return parts.join(', ');
  }

  function sourceLabel(source) {
    return String(source || '') === 'tel' ? '전화예약' : '관리자';
  }

  function normalizeReservation(item) {
    var out = Object.assign({}, item || {});
    out.source = String(out.source || 'admin');
    out.slot = timeSlot(out.time || '');
    out.date = out.date || dateKey(new Date());
    return out;
  }

  function showToast(msg) {
    if (!toastEl) return;
    toastEl.textContent = msg || '';
    toastEl.classList.add('show');
    clearTimeout(toastEl._t);
    toastEl._t = setTimeout(function () {
      toastEl.classList.remove('show');
    }, 2200);
  }

  function updateStatus(text) {
    if (statusEl) statusEl.textContent = text;
  }

  function formatStatusText(count) {
    return formatDate(new Date()) + ' · 총 ' + count + '건 · 지점 ' + getBranch();
  }

  function buildReceiptHtml(item) {
    var rows = [
      ['방문일자', String(item.date || '').replace(/-/g, '') || '—'],
      ['예약명', item.name || '—'],
      ['호실', roomTextFromItem(item)],
      ['예약시간', item.time || '—'],
      ['고객수', receiptPartyLine(item)],
      ['접수구분', sourceLabel(item.source)]
    ];
    if (String(item.phone || '').trim()) {
      rows.push(['전화번호', item.phone]);
    }
    return '<!DOCTYPE html><html lang="ko"><head><meta charset="UTF-8">' +
      '<title>예약 현황 인쇄</title>' +
      '<style>' +
      '@page{size:80mm auto;margin:0;}' +
      'html,body{margin:0;padding:0;background:#fff;color:#000;font-family:"Malgun Gothic","Noto Sans KR",sans-serif;}' +
      'body{width:80mm;box-sizing:border-box;margin:0 auto;padding:1mm 2mm 2mm;}' +
      '.wrap{text-align:left;line-height:1.15;font-size:17px;}' +
      '.title{text-align:center;font-size:25px;font-weight:700;letter-spacing:0.08em;margin:0 0 5px;}' +
      '.line{border-top:1px dashed #000;margin:5px 0;}' +
      '.row{display:grid;grid-template-columns:28mm 4mm 1fr;align-items:flex-start;column-gap:2mm;margin:0;}' +
      '.label{font-weight:700;white-space:nowrap;}' +
      '.colon{font-weight:700;text-align:center;white-space:nowrap;}' +
      '.value{white-space:pre-wrap;word-break:keep-all;}' +
      '</style></head><body><div class="wrap"><div class="title">예약 현황</div><div class="line"></div>' +
      rows.map(function (row) {
        return '<div class="row"><div class="label">' + escapeHtml(row[0]) + '</div><div class="colon">:</div><div class="value">' + escapeHtml(row[1]) + '</div></div>';
      }).join('') +
      '</div><script>window.onload=function(){setTimeout(function(){window.print();},150);};</script></body></html>';
  }

  function printReservation(item) {
    if (!item) {
      showToast('인쇄할 예약을 찾을 수 없습니다.');
      return;
    }
    var win = window.open('', '_blank', 'width=420,height=700');
    if (!win) {
      showToast('팝업이 차단되어 인쇄 창을 열 수 없습니다.');
      return;
    }
    win.document.open();
    win.document.write(buildReceiptHtml(item));
    win.document.close();
    try {
      win.focus();
    } catch (e) {}
  }

  function filteredReservations() {
    return reservations.filter(function (item) {
      if (selectedFilter === 'all') return true;
      return item.slot === selectedFilter;
    });
  }

  function render() {
    if (!listEl) return;
    var rows = filteredReservations();
    if (dateLabelEl) {
      dateLabelEl.textContent = formatDate(new Date()) + ' · ' + (selectedFilter === 'all' ? '전체' : (selectedFilter === 'lunch' ? '점심' : '저녁'));
    }
    updateStatus(formatStatusText(rows.length));
    if (!rows.length) {
      listEl.innerHTML = '<div class="print-empty">표시할 당일 예약이 없습니다.</div>';
      return;
    }
    listEl.innerHTML = rows.map(function (item, index) {
      var phone = String(item.phone || '').trim();
      return (
        '<article class="print-card" data-index="' + index + '">' +
          '<div class="print-time">' + escapeHtml(item.time || '—') + '</div>' +
          '<div class="print-main">' +
            '<div class="print-name-row">' +
              '<strong class="print-name">' + escapeHtml(item.name || '이름없음') + '</strong>' +
              '<span class="print-source">' + escapeHtml(sourceLabel(item.source)) + '</span>' +
            '</div>' +
            '<div class="print-meta">호실: ' + escapeHtml(roomTextFromItem(item)) + '</div>' +
            '<div class="print-meta">인원: ' + escapeHtml(partyLine(item)) + '</div>' +
            (phone ? '<div class="print-phone">전화번호: ' + escapeHtml(phone) + '</div>' : '') +
          '</div>' +
          '<div><button type="button" class="print-row-btn" data-index="' + index + '">인쇄</button></div>' +
        '</article>'
      );
    }).join('');

    listEl.querySelectorAll('.print-row-btn').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var idx = parseInt(btn.getAttribute('data-index'), 10);
        if (isNaN(idx)) return;
        printReservation(rows[idx]);
      });
    });
  }

  function applyReservationPayload(data) {
    reservations = (Array.isArray(data) ? data : []).map(normalizeReservation);
    render();
  }

  function fetchReservations() {
    updateStatus('서버에서 당일 예약을 불러오는 중...');
    return fetch(withBranch(API_TODAY_RESERVATIONS), { credentials: 'same-origin' })
      .then(function (r) {
        if (!r.ok) throw new Error('당일 예약을 불러오지 못했습니다.');
        return r.json();
      })
      .then(function (data) {
        applyReservationPayload(data);
      })
      .catch(function (err) {
        reservations = [];
        render();
        updateStatus('예약 목록을 불러오지 못했습니다.');
        showToast((err && err.message) || '당일 예약을 불러오지 못했습니다.');
      });
  }

  function connectRealtime() {
    if (printWs) {
      try {
        printWs.close();
      } catch (e) {}
      printWs = null;
    }
    var protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    var ws = new WebSocket(protocol + '//' + window.location.host + '/ws?' + branchQuery());
    printWs = ws;
    ws.onmessage = function (ev) {
      try {
        var data = JSON.parse(ev.data);
        if (Array.isArray(data)) {
          applyReservationPayload(data);
        }
      } catch (e) {}
    };
    ws.onclose = function () {
      setTimeout(connectRealtime, 3000);
    };
    ws.onerror = function () {
      ws.close();
    };
  }

  document.querySelectorAll('.print-chip').forEach(function (btn) {
    btn.addEventListener('click', function () {
      selectedFilter = btn.getAttribute('data-filter') || 'all';
      document.querySelectorAll('.print-chip').forEach(function (chip) {
        chip.classList.toggle('active', chip === btn);
      });
      render();
    });
  });

  if (refreshBtn) {
    refreshBtn.addEventListener('click', function () {
      fetchReservations();
    });
  }

  fetchReservations();
  connectRealtime();
})();
