/**
 * 전체 예약 조회 (전화 tel 데이터) — 날짜 입력으로 조회
 */
(function () {
  'use strict';

  var API = '/api/tel/reservations';
  var BRANCH_KEY = 'reserve_branch_id';

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
    } catch (e) {}
    try {
      var v = localStorage.getItem(BRANCH_KEY);
      if (v && String(v).trim()) return String(v).trim().toLowerCase();
    } catch (e2) {}
    return typeof reserveInferDefaultBranch === 'function' ? reserveInferDefaultBranch() : 'default';
  }

  function withBranch(url) {
    var sep = url.indexOf('?') >= 0 ? '&' : '?';
    return url + sep + 'branch=' + encodeURIComponent(getBranch());
  }

  if (typeof window.reserveInstallBuildVersionWatcher === 'function') {
    window.reserveInstallBuildVersionWatcher({ intervalMs: 10000 });
  }

  var filterFrom = document.getElementById('filter-from');
  var filterTo = document.getElementById('filter-to');
  var btnSearch = document.getElementById('btn-search');
  var btnPrintDay = document.getElementById('btn-print-day');
  var btnCalFrom = document.getElementById('btn-cal-from');
  var btnCalTo = document.getElementById('btn-cal-to');
  var calBackdrop = document.getElementById('all-cal-backdrop');
  var calPop = document.getElementById('all-cal-pop');
  var calMonthLabel = document.getElementById('all-cal-month-label');
  var calGrid = document.getElementById('all-cal-grid');
  var calPrev = document.getElementById('all-cal-prev');
  var calNext = document.getElementById('all-cal-next');
  var tbody = document.getElementById('all-tbody');
  var emptyMsg = document.getElementById('empty-msg');
  var resultCount = document.getElementById('result-count');
  var toastEl = document.getElementById('toast');

  var calYear;
  var calMonth;
  var activeDateInput = null;
  var today = new Date();
  var rowsCache = [];

  function showToast(msg) {
    if (!toastEl) return;
    toastEl.textContent = msg;
    toastEl.classList.add('show');
    clearTimeout(toastEl._t);
    toastEl._t = setTimeout(function () {
      toastEl.classList.remove('show');
    }, 2200);
  }

  function escapeHtml(text) {
    return String(text || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function normalizeRoomLabel(value) {
    return String(value || '').replace(/\s+/g, ' ').trim();
  }

  function parseRoomSelection(rawRooms, rawRoom) {
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

  function roomTextFromSelection(rawRooms, rawRoom) {
    return parseRoomSelection(rawRooms, rawRoom).join(', ');
  }

  function roomTextFromItem(item) {
    return roomTextFromSelection(item && item.rooms, item && item.room) || '—';
  }

  function dateKey(d) {
    return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
  }

  function parseDateKey(key) {
    var p = (key || '').split('-');
    if (p.length !== 3) return null;
    var y = parseInt(p[0], 10);
    var m = parseInt(p[1], 10) - 1;
    var day = parseInt(p[2], 10);
    if (!y || m < 0 || m > 11 || !day) return null;
    return new Date(y, m, day);
  }

  function sameDate(a, b) {
    return a && b &&
      a.getFullYear() === b.getFullYear() &&
      a.getMonth() === b.getMonth() &&
      a.getDate() === b.getDate();
  }

  function openDatePicker(whichInput) {
    activeDateInput = whichInput;
    var key = (whichInput.value || '').trim();
    var base = parseDateKey(key) || today;
    calYear = base.getFullYear();
    calMonth = base.getMonth();
    renderDatePicker();
    calPop.hidden = false;
    calBackdrop.hidden = false;
    document.body.style.overflow = 'hidden';
    try {
      calPrev.focus();
    } catch (e) {}
  }

  function closeDatePicker() {
    calPop.hidden = true;
    calBackdrop.hidden = true;
    activeDateInput = null;
    document.body.style.overflow = '';
  }

  function renderDatePicker() {
    if (!calGrid || !calMonthLabel) return;
    var first = new Date(calYear, calMonth, 1);
    var startPad = first.getDay();
    var daysInMonth = new Date(calYear, calMonth + 1, 0).getDate();
    calMonthLabel.textContent = calYear + '년 ' + (calMonth + 1) + '월';
    calGrid.innerHTML = '';

    var selectedKey = activeDateInput ? (activeDateInput.value || '').trim() : '';

    for (var i = 0; i < startPad; i++) {
      var ph = document.createElement('div');
      ph.className = 'all-cal-day empty';
      ph.setAttribute('aria-hidden', 'true');
      calGrid.appendChild(ph);
    }

    for (var d = 1; d <= daysInMonth; d++) {
      (function (dayNum) {
        var dd = new Date(calYear, calMonth, dayNum);
        var key = dateKey(dd);
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'all-cal-day';
        btn.textContent = String(dayNum);
        if (sameDate(dd, today)) btn.classList.add('today');
        if (selectedKey && key === selectedKey) btn.classList.add('selected');
        btn.addEventListener('click', function () {
          if (activeDateInput) {
            activeDateInput.value = key;
          }
          closeDatePicker();
        });
        calGrid.appendChild(btn);
      })(d);
    }
  }

  function buildQuery() {
    var from = (filterFrom.value || '').trim();
    var to = (filterTo.value || '').trim();
    var q = [];
    if (from) q.push('date_from=' + encodeURIComponent(from));
    if (to) q.push('date_to=' + encodeURIComponent(to));
    var base = API + (q.length ? ('?' + q.join('&')) : '');
    return withBranch(base);
  }

  function countText(n, from, to) {
    if (!from && !to) return '전체 기간 · ' + n + '건';
    return (from || '…') + ' ~ ' + (to || '…') + ' · ' + n + '건';
  }

  function fetchList() {
    resultCount.textContent = '불러오는 중…';
    fetch(buildQuery(), { credentials: 'same-origin' })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        var rows = Array.isArray(data) ? data : [];
        rowsCache = rows.slice();
        renderTable(rows);
        resultCount.textContent = countText(rows.length, filterFrom.value, filterTo.value);
      })
      .catch(function () {
        rowsCache = [];
        renderTable([]);
        resultCount.textContent = '불러오기 실패';
        showToast('목록을 불러오지 못했습니다.');
      });
  }

  function partyLine(r) {
    var a = r.adult;
    var c = r.child;
    var i = r.infant;
    if (a == null && c == null && i == null) {
      return r.count != null ? String(r.count) + '명' : '—';
    }
    var parts = [];
    if (a) parts.push('어른 ' + a);
    if (c) parts.push('어린이 ' + c);
    if (i) parts.push('유아 ' + i);
    return parts.length ? parts.join(', ') : (r.count != null ? String(r.count) + '명' : '—');
  }

  function displayPartyShort(r) {
    var total = r.count;
    if (total == null) {
      total = (parseInt(r.adult, 10) || 0) + (parseInt(r.child, 10) || 0) + (parseInt(r.infant, 10) || 0);
    }
    total = parseInt(total, 10) || 0;
    return total > 0 ? String(total).padStart(2, '0') + '명' : '—';
  }

  function isYchowonBranch() {
    try {
      if (String(window.location.hostname || '').toLowerCase().indexOf('ychowon') >= 0) return true;
    } catch (e) {}
    try {
      if (typeof reserveInferDefaultBranch === 'function' && reserveInferDefaultBranch() === 'ychowon') return true;
    } catch (e2) {}
    return getBranch() === 'ychowon';
  }

  function formatYchowonPrintRoom(room) {
    var text = String(room || '').trim();
    if (!text) return '—';

    var floorRoom = text.match(/^(\d+F)\s*룸\s*룸?\s*(\d+)\s*(?:호|호실)?$/i);
    if (floorRoom) {
      var floor = floorRoom[1].toUpperCase();
      var number = floorRoom[2];
      if (floor === '4F') return number + '호실';
      if (floor === '5F') return '5층 ' + number + '호실';
    }

    if (/홀/i.test(text)) return '3층';
    return text;
  }

  function ychowonPrintRoomSortKey(room) {
    var text = parseRoomSelection(null, room)[0] || '';
    var floorRoom = text.match(/^(\d+F)\s*룸\s*룸?\s*(\d+)\s*(?:호|호실)?$/i);
    if (floorRoom) {
      var floor = floorRoom[1].toUpperCase();
      var num = parseInt(floorRoom[2], 10);
      if (floor === '4F') return [0, isNaN(num) ? 999 : num, text];
      if (floor === '5F') return [2, isNaN(num) ? 999 : num, text];
    }
    if (/홀/i.test(text)) return [1, text.toUpperCase(), text];
    return [3, text, text];
  }

  function sortYchowonPrintRows(rows) {
    var list = Array.isArray(rows) ? rows.slice() : [];
    if (!isYchowonBranch()) return list;
    list.sort(function (a, b) {
      var roomA = ychowonPrintRoomSortKey(a && a.room);
      var roomB = ychowonPrintRoomSortKey(b && b.room);
      if (roomA[0] !== roomB[0]) return roomA[0] - roomB[0];
      var timeA = String((a && a.time) || '');
      var timeB = String((b && b.time) || '');
      if (timeA !== timeB) return timeA.localeCompare(timeB);
      if (roomA[1] !== roomB[1]) return String(roomA[1]).localeCompare(String(roomB[1]), 'ko');
      return String((a && a.id) || '').localeCompare(String((b && b.id) || ''), 'ko');
    });
    return list;
  }

  function printableRoom(r) {
    var rooms = parseRoomSelection(r && r.rooms, r && r.room);
    if (!rooms.length) return '—';
    if (!isYchowonBranch()) return rooms.join(', ');
    return rooms.map(formatYchowonPrintRoom).join(', ');
  }

  function printableGuestName(r) {
    var name = String((r && r.name) || '').trim();
    if (!name) return '—';
    if (/님\s*$/u.test(name)) return name;
    return name + ' 님';
  }

  function currentPrintDate() {
    var from = (filterFrom.value || '').trim();
    var to = (filterTo.value || '').trim();
    if (from && to && from !== to) return '';
    return from || to || '';
  }

  function formatPrintDate(dateText) {
    var p = String(dateText || '').split('-');
    if (p.length !== 3) return String(dateText || '');
    return p[0] + '년 ' + p[1] + '월 ' + p[2] + '일';
  }

  function buildPrintColumns(rows) {
    var mid = Math.ceil(rows.length / 2);
    return [rows.slice(0, mid), rows.slice(mid)];
  }

  function buildPrintTable(rows) {
    var body = rows.map(function (r) {
      return '<tr>' +
        '<td>' + escapeHtml(r.time || '—') + '</td>' +
        '<td>' + escapeHtml(printableGuestName(r)) + '</td>' +
        '<td>' + escapeHtml(displayPartyShort(r)) + '</td>' +
        '<td>' + escapeHtml(printableRoom(r)) + '</td>' +
      '</tr>';
    }).join('');
    if (!body) {
      body = '<tr class="empty"><td></td><td></td><td></td><td></td></tr>'.repeat(18);
    }
    return '<table class="print-day-table">' +
      '<thead><tr><th>시간</th><th>예약자명</th><th>인원수</th><th>룸번호</th></tr></thead>' +
      '<tbody>' + body + '</tbody></table>';
  }

  function buildDayPrintHtml(dateText, rows) {
    var cols = buildPrintColumns(rows);
    var printDate = escapeHtml(formatPrintDate(dateText));
    return '<!DOCTYPE html><html lang="ko"><head><meta charset="UTF-8"><title>당일 예약현황 인쇄</title><style>' +
      '@page{size:A4 portrait;margin:12mm 10mm 14mm;}' +
      'html,body{margin:0;padding:0;background:#fff;color:#111;font-family:"Malgun Gothic","Noto Sans KR",sans-serif;}' +
      'body{font-size:11pt;line-height:1.3;}' +
      '.sheet{width:100%;}' +
      '.date-line{text-align:right;font-size:14pt;font-weight:600;margin:0 0 8mm;}' +
      '.tables{display:grid;grid-template-columns:1fr 1fr;gap:6mm;align-items:start;}' +
      '.print-day-table{width:100%;border-collapse:collapse;table-layout:fixed;}' +
      '.print-day-table th,.print-day-table td{border:1px solid #999;padding:2.2mm 2mm;font-size:10.5pt;vertical-align:middle;}' +
      '.print-day-table th{background:#f5f5f5;font-weight:700;text-align:center;white-space:nowrap;}' +
      '.print-day-table td:nth-child(1){width:18%;text-align:center;}' +
      '.print-day-table td:nth-child(2){width:34%;font-weight:600;}' +
      '.print-day-table td:nth-child(3){width:18%;text-align:center;}' +
      '.print-day-table td:nth-child(4){width:30%;text-align:center;}' +
      '.print-day-table tbody tr.empty td{height:10mm;}' +
      '</style></head><body><div class="sheet">' +
      '<div class="date-line">' + printDate + '</div>' +
      '<div class="tables">' +
      '<div>' + buildPrintTable(cols[0]) + '</div>' +
      '<div>' + buildPrintTable(cols[1]) + '</div>' +
      '</div></div>' +
      '<script>window.onload=function(){setTimeout(function(){window.print();},150);};</script>' +
      '</body></html>';
  }

  function printCurrentDay() {
    var dateText = currentPrintDate();
    if (!dateText) {
      showToast('당일 출력은 시작일과 종료일을 같은 날짜로 맞춰주세요.');
      return;
    }
    var rows = sortYchowonPrintRows(
      rowsCache.filter(function (r) { return String(r.date || '') === dateText; })
    );
    if (!rows.length) {
      showToast('선택한 날짜의 예약이 없습니다.');
      return;
    }
    var win = window.open('', '_blank', 'width=1024,height=900');
    if (!win) {
      showToast('팝업이 차단되어 인쇄 창을 열 수 없습니다.');
      return;
    }
    win.document.open();
    win.document.write(buildDayPrintHtml(dateText, rows));
    win.document.close();
    try {
      win.focus();
    } catch (e) {}
  }

  function renderTable(rows) {
    tbody.innerHTML = '';
    if (!rows.length) {
      emptyMsg.hidden = false;
      return;
    }
    emptyMsg.hidden = true;
    rows.forEach(function (r) {
      var tr = document.createElement('tr');
      tr.innerHTML =
        '<td>' + escapeHtml(r.date || '—') + '</td>' +
        '<td>' + escapeHtml(r.time || '—') + '</td>' +
        '<td>' + escapeHtml(r.name || '—') + '</td>' +
        '<td>' + escapeHtml(r.phone || '—') + '</td>' +
        '<td>' + escapeHtml(roomTextFromItem(r)) + '</td>' +
        '<td>' + escapeHtml(partyLine(r)) + '</td>' +
        '<td class="col-actions">' +
          '<button type="button" class="btn-mini btn-edit-row" data-id="' + escapeHtml(String(r.id)) + '">수정</button>' +
          '<button type="button" class="btn-mini btn-del-row" data-id="' + escapeHtml(String(r.id)) + '">삭제</button>' +
        '</td>';
      tbody.appendChild(tr);
    });

    tbody.querySelectorAll('.btn-del-row').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var id = parseInt(btn.getAttribute('data-id'), 10);
        if (!id || !window.confirm('이 예약을 삭제할까요?')) return;
        fetch(withBranch(API + '/' + id), { method: 'DELETE', credentials: 'same-origin' })
          .then(function (r) {
            if (!r.ok) throw new Error();
            return r.json();
          })
          .then(function () {
            showToast('삭제했습니다.');
            fetchList();
          })
          .catch(function () {
            showToast('삭제에 실패했습니다.');
          });
      });
    });

    tbody.querySelectorAll('.btn-edit-row').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var id = parseInt(btn.getAttribute('data-id'), 10);
        var row = rows.filter(function (x) { return int(x.id) === id; })[0];
        if (!row) return;
        var t = window.prompt('시간 (12:00)', row.time || '');
        if (t === null) return;
        var n = window.prompt('이름', row.name || '');
        if (n === null) return;
        var rm = window.prompt('룸/테이블 (쉼표로 여러 개)', roomTextFromItem(row));
        if (rm === null) return;
        var ph = window.prompt('전화번호 (비우면 유지)', row.phone || '');
        if (ph === null) return;
        var rooms = parseRoomSelection(null, rm);
        var body = { time: t.trim(), name: n.trim(), room: roomTextFromSelection(rooms), rooms: rooms };
        if (ph.trim()) body.phone = ph.trim();
        fetch(withBranch(API + '/' + id), {
          method: 'PATCH',
          credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body)
        })
          .then(function (r) {
            if (!r.ok) return r.json().then(function (j) {
              var d = j.detail;
              throw new Error(typeof d === 'string' ? d : '수정 실패');
            });
            return r.json();
          })
          .then(function () {
            showToast('수정했습니다.');
            fetchList();
          })
          .catch(function (e) {
            showToast(e.message || '수정에 실패했습니다.');
          });
      });
    });
  }

  function int(x) {
    return parseInt(x, 10) || 0;
  }

  btnSearch.addEventListener('click', fetchList);
  if (btnPrintDay) btnPrintDay.addEventListener('click', printCurrentDay);

  if (btnCalFrom) {
    btnCalFrom.addEventListener('click', function () {
      openDatePicker(filterFrom);
    });
  }
  if (btnCalTo) {
    btnCalTo.addEventListener('click', function () {
      openDatePicker(filterTo);
    });
  }

  if (filterFrom) {
    filterFrom.addEventListener('click', function () {
      openDatePicker(filterFrom);
    });
  }
  if (filterTo) {
    filterTo.addEventListener('click', function () {
      openDatePicker(filterTo);
    });
  }

  if (calPrev) {
    calPrev.addEventListener('click', function () {
      calMonth--;
      if (calMonth < 0) {
        calMonth = 11;
        calYear--;
      }
      renderDatePicker();
    });
  }
  if (calNext) {
    calNext.addEventListener('click', function () {
      calMonth++;
      if (calMonth > 11) {
        calMonth = 0;
        calYear++;
      }
      renderDatePicker();
    });
  }

  if (calBackdrop) {
    calBackdrop.addEventListener('click', closeDatePicker);
  }

  document.addEventListener('keydown', function (ev) {
    if (ev.key === 'Escape' && activeDateInput && calPop && !calPop.hidden) {
      ev.preventDefault();
      closeDatePicker();
    }
  });

  var now = new Date();
  filterFrom.value = dateKey(now);
  filterTo.value = dateKey(now);

  fetchList();
})();
