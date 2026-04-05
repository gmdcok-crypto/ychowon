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
      return v && String(v).trim() ? String(v).trim() : 'default';
    } catch (e2) {
      return 'default';
    }
  }

  function withBranch(url) {
    var sep = url.indexOf('?') >= 0 ? '&' : '?';
    return url + sep + 'branch=' + encodeURIComponent(getBranch());
  }

  var filterFrom = document.getElementById('filter-from');
  var filterTo = document.getElementById('filter-to');
  var btnSearch = document.getElementById('btn-search');
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
        renderTable(rows);
        resultCount.textContent = countText(rows.length, filterFrom.value, filterTo.value);
      })
      .catch(function () {
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
        '<td>' + escapeHtml(r.room || '—') + '</td>' +
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
        var rm = window.prompt('룸/테이블', row.room || '');
        if (rm === null) return;
        var ph = window.prompt('전화번호 (비우면 유지)', row.phone || '');
        if (ph === null) return;
        var body = { time: t.trim(), name: n.trim(), room: rm.trim() };
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
