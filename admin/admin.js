/**
 * 직원용 예약 입력 - 저장 시 현황판에 실시간 반영 (WebSocket)
 */
(function () {
  'use strict';

  const API = '/api/reservations/today';
  const API_TEL = '/api/tel/reservations';
  const API_TEL_ROOMS = '/api/tel/rooms';
  const BRANCH_KEY = 'reserve_branch_id';

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

  function branchQuery() {
    return 'branch=' + encodeURIComponent(getBranch());
  }

  function withBranch(url) {
    var sep = url.indexOf('?') >= 0 ? '&' : '?';
    return url + sep + branchQuery();
  }

  function getBuildVersion() {
    try {
      return String(window.__RESERVE_BUILD_VERSION__ || '').trim();
    } catch (e) {}
    return '';
  }

  function syncAdminIframes() {
    var b = getBranch();
    var q = 'branch=' + encodeURIComponent(b);
    var version = getBuildVersion();
    if (version) q += '&v=' + encodeURIComponent(version);
    var tel = document.getElementById('iframe-tel-admin');
    if (tel) tel.src = '/tel/?' + q;
    var all = document.getElementById('iframe-all-admin');
    if (all) all.src = '/admin/all.html?embed=1&' + q;
    var dc = document.getElementById('iframe-display-admin');
    if (dc) dc.src = '/admin/display-content.html?embed=1&' + q;
  }

  function refreshAllIframe() {
    var all = document.getElementById('iframe-all-admin');
    if (!all || !all.contentWindow) return;
    try {
      all.contentWindow.postMessage({ type: 'reserve-all-refresh' }, window.location.origin);
    } catch (e) {}
  }
  const listEl = document.getElementById('list');
  const addForm = document.getElementById('add-form');
  const toastEl = document.getElementById('toast');
  const formTitle = document.getElementById('form-title');
  const submitBtn = document.getElementById('submit-btn');
  const cancelEditBtn = document.getElementById('cancel-edit-btn');
  const refreshBtn = document.getElementById('btn-refresh-list');
  const timeInput = document.getElementById('time');
  const roomInput = document.getElementById('room');
  const staffRoomDialog = document.getElementById('staff-room-dialog');
  const staffRoomBackdrop = document.getElementById('staff-room-dialog-backdrop');
  const staffRoomMeta = document.getElementById('staff-room-dialog-meta');
  const staffRoomClose = document.getElementById('staff-room-dialog-close');
  const staffRoomGroupTabs = document.getElementById('staff-room-group-tabs');
  const staffRoomGrid = document.getElementById('staff-room-grid');
  const staffTimeBackdrop = document.getElementById('staff-time-dialog-backdrop');
  const staffTimeClose = document.getElementById('staff-time-dialog-close');
  const staffPartyDialog = document.getElementById('staff-party-dialog');
  const staffPartyBackdrop = document.getElementById('staff-party-dialog-backdrop');
  const staffPartyClose = document.getElementById('staff-party-dialog-close');
  const partyDisplayInput = document.getElementById('party-display');
  const roomSwapBtn = document.getElementById('room-swap-btn');
  const roomSwapConfirmBtn = document.getElementById('room-swap-confirm-btn');

  function staffTimeDialogEl() {
    return document.getElementById('staff-time-dialog');
  }

  var staffTimeOpenLock = false;
  function openStaffTimeDialogGuarded() {
    if (staffTimeOpenLock) return;
    staffTimeOpenLock = true;
    openStaffTimeDialog();
    setTimeout(function () {
      staffTimeOpenLock = false;
    }, 450);
  }

  var staffPartyTapLock = false;
  function openStaffPartyDialogGuarded() {
    if (staffPartyTapLock) return;
    staffPartyTapLock = true;
    openStaffPartyDialog();
    setTimeout(function () {
      staffPartyTapLock = false;
    }, 450);
  }

  var staffRoomTapLock = false;
  function openStaffRoomDialogGuarded() {
    if (staffRoomTapLock) return;
    staffRoomTapLock = true;
    openStaffRoomDialog();
    setTimeout(function () {
      staffRoomTapLock = false;
    }, 450);
  }

  function bindTapOpen(el, fn) {
    if (!el) return;
    function go(e) {
      if (e) {
        if (e.type === 'touchend') e.preventDefault();
        e.stopPropagation();
      }
      fn();
    }
    el.addEventListener('click', go);
    el.addEventListener('touchend', go, { passive: false });
  }

  let list = [];
  let editingIndex = -1;
  let staffRoomStatus = [];
  let staffSelectedRoomSection = 'all';
  let selectedStaffRooms = [];
  let roomSwapMode = false;
  let roomSwapTargets = [];

  function dateKey(d) {
    return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
  }

  function formatStaffDate(d) {
    var y = d.getFullYear();
    var m = String(d.getMonth() + 1).padStart(2, '0');
    var day = String(d.getDate()).padStart(2, '0');
    var week = ['일', '월', '화', '수', '목', '금', '토'][d.getDay()];
    return y + '.' + m + '.' + day + ' (' + week + ')';
  }

  function normalizeTimeValue(t) {
    if (t == null || t === '') return '';
    var s = String(t).trim();
    var m = s.match(/^(\d{1,2}):(\d{2})(?::\d{2})?/);
    if (!m) return '';
    var h = Math.min(23, Math.max(0, parseInt(m[1], 10)));
    var min = Math.min(59, Math.max(0, parseInt(m[2], 10)));
    return String(h).padStart(2, '0') + ':' + String(min).padStart(2, '0');
  }

  function staffTimeOk(val) {
    var t = val !== undefined && val !== null && val !== ''
      ? String(val).trim()
      : (timeInput && timeInput.value ? timeInput.value : '').trim();
    return /^([01]\d|2[0-3]):[0-5]\d$/.test(t);
  }

  function staffSlotFromTime(t) {
    var n = normalizeTimeValue(t);
    if (!n) return 'lunch';
    var h = parseInt(n.split(':')[0], 10);
    if (!isNaN(h) && h >= 17 && h <= 19) return 'dinner';
    return 'lunch';
  }

  function setStaffTimeTab(slot) {
    var lunchBox = document.getElementById('staff-time-buttons-lunch');
    var dinnerBox = document.getElementById('staff-time-buttons-dinner');
    document.querySelectorAll('.staff-time-tab').forEach(function (t) {
      t.classList.toggle('active', t.getAttribute('data-slot') === slot);
    });
    if (slot === 'dinner') {
      if (lunchBox) lunchBox.classList.add('hidden');
      if (dinnerBox) dinnerBox.classList.remove('hidden');
    } else {
      if (lunchBox) lunchBox.classList.remove('hidden');
      if (dinnerBox) dinnerBox.classList.add('hidden');
    }
  }

  function syncStaffTimeDialogButtons(selectedTime) {
    var norm = normalizeTimeValue(selectedTime);
    document.querySelectorAll('.staff-time-btn').forEach(function (b) {
      b.classList.toggle('active', Boolean(norm && b.getAttribute('data-time') === norm));
    });
  }

  function closeStaffTimeDialog() {
    var dlg = staffTimeDialogEl();
    if (!dlg) return;
    dlg.classList.add('hidden');
    dlg.setAttribute('aria-hidden', 'true');
  }

  function openStaffTimeDialog() {
    var dlg = staffTimeDialogEl();
    var inp = timeInput || document.getElementById('time');
    if (!dlg || !inp) return;
    var t = (inp.value || '').trim();
    if (!staffTimeOk(t)) {
      inp.value = '12:00';
      t = '12:00';
    } else {
      t = normalizeTimeValue(t);
      inp.value = t;
    }
    setStaffTimeTab(staffSlotFromTime(t));
    syncStaffTimeDialogButtons(t);
    dlg.classList.remove('hidden');
    dlg.setAttribute('aria-hidden', 'false');
  }

  function applyStaffTimeChoice(value) {
    var n = normalizeTimeValue(value);
    if (!n) return;
    timeInput.value = n;
    timeInput.dispatchEvent(new Event('input', { bubbles: true }));
    timeInput.dispatchEvent(new Event('change', { bubbles: true }));
    refreshStaffRoomAvailability(false);
    closeStaffTimeDialog();
  }

  function setupStaffTimeDialog() {
    if (!timeInput) return;
    /* readonly 입력·라벨 탭으로만 팝업 (별도 버튼 없음) */
    /* readonly + label(for): 라벨 탭은 input으로 이벤트가 안 올 수 있음 */
    var timeLabel = document.querySelector('label[for="time"]');
    if (timeLabel) {
      timeLabel.addEventListener('click', function (e) {
        e.preventDefault();
        openStaffTimeDialogGuarded();
      });
    }
    bindTapOpen(timeInput, openStaffTimeDialogGuarded);
    timeInput.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        openStaffTimeDialogGuarded();
      }
    });
    if (staffTimeClose) staffTimeClose.addEventListener('click', closeStaffTimeDialog);
    if (staffTimeBackdrop) staffTimeBackdrop.addEventListener('click', closeStaffTimeDialog);
    document.querySelectorAll('.staff-time-tab').forEach(function (tab) {
      tab.addEventListener('click', function () {
        setStaffTimeTab(tab.getAttribute('data-slot') || 'lunch');
      });
    });
    document.querySelectorAll('.staff-time-btn').forEach(function (btn) {
      btn.addEventListener('click', function () {
        applyStaffTimeChoice(btn.getAttribute('data-time') || '');
      });
    });
  }

  function openStaffPartyDialog() {
    if (!staffPartyDialog) return;
    syncPartyDisplayFromInputs();
    staffPartyDialog.classList.remove('hidden');
    staffPartyDialog.setAttribute('aria-hidden', 'false');
  }

  function closeStaffPartyDialog() {
    if (!staffPartyDialog) return;
    staffPartyDialog.classList.add('hidden');
    staffPartyDialog.setAttribute('aria-hidden', 'true');
    syncPartyDisplayFromInputs();
  }

  function setupStaffPartyDialog() {
    if (partyDisplayInput) {
      bindTapOpen(partyDisplayInput, openStaffPartyDialogGuarded);
      partyDisplayInput.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          openStaffPartyDialogGuarded();
        }
      });
    }
    var partyLabel = document.querySelector('label[for="party-display"]');
    if (partyLabel) {
      partyLabel.addEventListener('click', function (e) {
        e.preventDefault();
        openStaffPartyDialogGuarded();
      });
    }
    if (staffPartyClose) staffPartyClose.addEventListener('click', closeStaffPartyDialog);
    if (staffPartyBackdrop) staffPartyBackdrop.addEventListener('click', closeStaffPartyDialog);
    document.querySelectorAll('#staff-party-dialog .step[data-target]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var targetId = btn.getAttribute('data-target');
        var input = targetId ? document.getElementById(targetId) : null;
        if (!input) return;
        var delta = parseInt(btn.getAttribute('data-delta'), 10) || 0;
        var cur = parseInt(input.value, 10) || 0;
        cur += delta;
        if (cur < 0) cur = 0;
        if (cur > 99) cur = 99;
        input.value = String(cur);
        syncPartyDisplayFromInputs();
      });
    });
    ['staff-count-adult', 'staff-count-child', 'staff-count-infant'].forEach(function (id) {
      var el = document.getElementById(id);
      if (!el) return;
      el.addEventListener('input', function () {
        syncPartyDisplayFromInputs();
      });
      el.addEventListener('blur', function () {
        var n = parseInt(el.value, 10);
        if (isNaN(n) || n < 0) n = 0;
        if (n > 99) n = 99;
        el.value = String(n);
        syncPartyDisplayFromInputs();
      });
    });
  }

  function renderStaffRoomDialog() {
    if (!staffRoomGrid || !staffRoomGroupTabs) return;
    if (!staffTimeOk()) {
      staffRoomGroupTabs.innerHTML = '';
      staffRoomGrid.innerHTML = '<div class="empty">예약 시간을 먼저 입력하세요 (예: 12:00).</div>';
      return;
    }

    var sections = ['all'];
    staffRoomStatus.forEach(function (room) {
      var section = room.section || '기타';
      if (sections.indexOf(section) === -1) {
        sections.push(section);
      }
    });

    if (sections.indexOf(staffSelectedRoomSection) === -1) {
      staffSelectedRoomSection = 'all';
    }

    staffRoomGroupTabs.innerHTML = sections.map(function (section) {
      var label = section === 'all' ? '전체' : section;
      var activeClass = staffSelectedRoomSection === section ? ' active' : '';
      return '<button type="button" class="room-group-tab' + activeClass + '" data-section="' + escapeHtml(section) + '">' + escapeHtml(label) + '</button>';
    }).join('');

    staffRoomGroupTabs.querySelectorAll('.room-group-tab').forEach(function (btn) {
      btn.addEventListener('click', function () {
        staffSelectedRoomSection = btn.getAttribute('data-section') || 'all';
        renderStaffRoomDialog();
      });
    });

    var filteredRooms = staffRoomStatus.filter(function (room) {
      if (staffSelectedRoomSection === 'all') return true;
      return (room.section || '기타') === staffSelectedRoomSection;
    });

    var timeVal = (timeInput.value || '').trim();
    staffRoomGrid.innerHTML = filteredRooms.map(function (room) {
      var className = 'room-option';
      var roomName = room.display_label || room.label;
      var selectedTimeText = timeVal ? (timeVal + ' 기준') : '';
      var occupiedRanges = Array.isArray(room.occupied_ranges) ? room.occupied_ranges : [];
      if (room.reserved) className += ' reserved';
      if (!roomSwapMode && selectedStaffRooms.indexOf(room.label) >= 0) className += ' selected';
      if (roomSwapMode) {
        className += room.reserved ? ' swap-candidate' : ' swap-disabled';
        if (isRoomSwapTarget(room)) className += ' swap-selected';
      }
      var base = staffSelectedRoomSection === 'all' && room.section ? room.section + ' · ' : '';
      var statusText = room.reserved ? (roomSwapMode ? '교환 대상' : '예약 완료') : (roomSwapMode ? '예약 없음' : '선택 가능');
      var timeText = room.reserved ? (room.reservation_range || room.time || timeVal || '') : selectedTimeText;
      var nameText = room.reserved && room.reservation_name ? (' · ' + room.reservation_name) : '';
      var sub = base + statusText + (timeText ? (' · ' + timeText) : '') + nameText;
      var timeSummary = occupiedRanges.length ? ('점유 시간: ' + occupiedRanges.join(', ')) : '점유 시간 없음';
      return (
        '<button type="button" class="' + className + '" data-room="' + escapeHtml(room.label) + '"' +
        (!roomSwapMode && room.reserved ? ' disabled' : '') + '>' +
          '<span class="room-name">' + escapeHtml(roomName) + '</span>' +
          '<span class="room-sub">' + escapeHtml(sub) + '</span>' +
          '<span class="room-sub">' + escapeHtml(timeSummary) + '</span>' +
        '</button>'
      );
    }).join('');

    if (!filteredRooms.length) {
      staffRoomGrid.innerHTML = '<div class="empty">이 구역에 등록된 자리가 없습니다.</div>';
    }

    staffRoomGrid.querySelectorAll('.room-option').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var room = btn.getAttribute('data-room') || '';
        if (roomSwapMode) {
          toggleRoomSwapTarget(room);
          return;
        }
        if (btn.disabled) return;
        var next = selectedStaffRooms.slice();
        var idx = next.indexOf(room);
        if (idx >= 0) next.splice(idx, 1);
        else next.push(room);
        setStaffSelectedRooms(next);
        renderStaffRoomDialog();
      });
    });
  }

  function refreshStaffRoomAvailability(openIfNeeded) {
    if (!staffTimeOk()) {
      staffRoomStatus = [];
      if (openIfNeeded) renderStaffRoomDialog();
      return Promise.resolve();
    }

    var today = new Date();
    var q = '?date=' + encodeURIComponent(dateKey(today)) + '&time=' + encodeURIComponent((timeInput.value || '').trim()) + '&' + branchQuery() + currentStaffRoomStatusExtras();
    if (staffRoomMeta) {
      staffRoomMeta.textContent = formatStaffDate(today) + ' · ' + (timeInput.value || '').trim() + ' 기준' + (roomSwapMode ? ' · 교환할 자리 2개 선택' : '');
    }

    return fetch(API_TEL_ROOMS + q, { credentials: 'same-origin' })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        staffRoomStatus = Array.isArray(data.rooms) ? data.rooms : [];
        if (!roomSwapMode) {
          var blocked = selectedStaffRooms.filter(function (selected) {
            return staffRoomStatus.some(function (room) {
              return room.label === selected && room.reserved;
            });
          });
          if (blocked.length) {
            setStaffSelectedRooms(selectedStaffRooms.filter(function (selected) {
              return blocked.indexOf(selected) === -1;
            }));
            showToast('선택한 시간에 이미 예약된 자리입니다. 다시 선택하세요.');
          }
        }
        if (openIfNeeded || (staffRoomDialog && !staffRoomDialog.classList.contains('hidden'))) {
          renderStaffRoomDialog();
        }
      })
      .catch(function () {
        staffRoomStatus = [];
        if (staffRoomGroupTabs) staffRoomGroupTabs.innerHTML = '';
        if (openIfNeeded || (staffRoomDialog && !staffRoomDialog.classList.contains('hidden'))) {
          if (staffRoomGrid) {
            staffRoomGrid.innerHTML = '<div class="empty">호실 정보를 불러오지 못했습니다.</div>';
          }
        }
      });
  }

  function openStaffRoomDialog() {
    if (!staffTimeOk()) {
      showToast('먼저 예약 시간을 선택하세요.');
      openStaffTimeDialog();
      return;
    }
    if (staffRoomDialog) {
      staffRoomDialog.classList.remove('hidden');
      staffRoomDialog.setAttribute('aria-hidden', 'false');
    }
    updateRoomSwapButtonUi();
    refreshStaffRoomAvailability(true);
  }

  function closeStaffRoomDialog() {
    if (staffRoomDialog) {
      staffRoomDialog.classList.add('hidden');
      staffRoomDialog.setAttribute('aria-hidden', 'true');
    }
  }

  function setupStaffRoomDialog() {
    if (roomInput) {
      bindTapOpen(roomInput, openStaffRoomDialogGuarded);
    }
    if (staffRoomClose) {
      staffRoomClose.addEventListener('click', closeStaffRoomDialog);
    }
    if (staffRoomBackdrop) {
      staffRoomBackdrop.addEventListener('click', closeStaffRoomDialog);
    }
    if (timeInput) {
      timeInput.addEventListener('change', function () {
        refreshStaffRoomAvailability(false);
      });
      timeInput.addEventListener('blur', function () {
        var n = normalizeTimeValue(timeInput.value);
        if (n) timeInput.value = n;
        refreshStaffRoomAvailability(false);
      });
    }
    document.addEventListener('keydown', function (ev) {
      if (ev.key !== 'Escape') return;
      var timeDlg = staffTimeDialogEl();
      if (timeDlg && !timeDlg.classList.contains('hidden')) {
        ev.preventDefault();
        closeStaffTimeDialog();
        return;
      }
      if (staffPartyDialog && !staffPartyDialog.classList.contains('hidden')) {
        ev.preventDefault();
        closeStaffPartyDialog();
        return;
      }
      if (!staffRoomDialog || staffRoomDialog.classList.contains('hidden')) return;
      ev.preventDefault();
      closeStaffRoomDialog();
    });
  }

  function showToast(msg) {
    if (!toastEl) return;
    toastEl.textContent = msg;
    toastEl.classList.add('show');
    clearTimeout(toastEl._t);
    toastEl._t = setTimeout(function () {
      toastEl.classList.remove('show');
    }, 2500);
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
    var text = roomTextFromSelection(item && item.rooms, item && item.room);
    return text || '—';
  }

  function setStaffSelectedRooms(rooms) {
    selectedStaffRooms = parseRoomSelection(rooms);
    if (roomInput) roomInput.value = roomTextFromSelection(selectedStaffRooms);
  }

  function currentStaffRoomStatusExtras() {
    if (roomSwapMode) return '';
    if (editingIndex < 0) return '';
    var current = list[editingIndex];
    if (!current || current.id == null) return '';
    var source = current.source === 'tel' ? 'tel' : 'staff';
    var excludeId = source === 'tel' ? telNumericId(current) : current.id;
    if (excludeId == null || excludeId === '') return '';
    return '&exclude_source=' + encodeURIComponent(source) + '&exclude_id=' + encodeURIComponent(String(excludeId));
  }

  /** 예약조회·전화예약(tel)과 동일한 인원 표기 */
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

  function parseStaffCount(id) {
    var el = document.getElementById(id);
    var n = parseInt(el && el.value, 10);
    if (isNaN(n) || n < 0) return 0;
    if (n > 99) return 99;
    return n;
  }

  function syncPartyDisplayFromInputs() {
    if (!partyDisplayInput) return;
    var adult = parseStaffCount('staff-count-adult');
    var child = parseStaffCount('staff-count-child');
    var infant = parseStaffCount('staff-count-infant');
    partyDisplayInput.value = partyLine({
      adult: adult,
      child: child,
      infant: infant,
      count: adult + child + infant
    });
  }

  function partyFromItem(item) {
    var a = item.adult;
    var c = item.child;
    var i = item.infant;
    if (a == null && c == null && i == null) {
      var cnt = item.count != null ? parseInt(item.count, 10) : 2;
      if (isNaN(cnt) || cnt < 1) cnt = 2;
      return { adult: cnt, child: 0, infant: 0 };
    }
    return {
      adult: a != null ? a : 0,
      child: c != null ? c : 0,
      infant: i != null ? i : 0
    };
  }

  function applyPartyFromItem(item) {
    var p = partyFromItem(item);
    var ad = document.getElementById('staff-count-adult');
    var ch = document.getElementById('staff-count-child');
    var inf = document.getElementById('staff-count-infant');
    if (ad) ad.value = String(p.adult);
    if (ch) ch.value = String(p.child);
    if (inf) inf.value = String(p.infant);
    syncPartyDisplayFromInputs();
  }

  function resetPartyInputs() {
    var ad = document.getElementById('staff-count-adult');
    var ch = document.getElementById('staff-count-child');
    var inf = document.getElementById('staff-count-infant');
    if (ad) ad.value = '2';
    if (ch) ch.value = '0';
    if (inf) inf.value = '0';
    syncPartyDisplayFromInputs();
  }

  function getStaffPartyPayload() {
    var adult = parseStaffCount('staff-count-adult');
    var child = parseStaffCount('staff-count-child');
    var infant = parseStaffCount('staff-count-infant');
    var total = adult + child + infant;
    return { adult: adult, child: child, infant: infant, count: total };
  }

  function normalizeRow(r) {
    if (!r) return r;
    var rooms = parseRoomSelection(r.rooms, r.room);
    if (r.source === 'tel' || r.source === 'admin') return { ...r, rooms: rooms, room: roomTextFromSelection(rooms) };
    return { time: r.time, name: r.name, room: roomTextFromSelection(rooms), rooms: rooms, id: r.id, source: 'admin' };
  }

  function errorDetailText(detail, fallback) {
    if (typeof detail === 'string' && detail.trim()) return detail;
    if (Array.isArray(detail) && detail.length) {
      var first = detail[0];
      if (typeof first === 'string' && first.trim()) return first;
      if (first && typeof first === 'object') {
        if (typeof first.msg === 'string' && first.msg.trim()) return first.msg;
        if (Array.isArray(first.loc) && first.loc.length && typeof first.loc[first.loc.length - 1] === 'string') {
          return String(first.loc[first.loc.length - 1]) + ' 항목을 확인하세요.';
        }
      }
    }
    if (detail && typeof detail === 'object') {
      if (typeof detail.msg === 'string' && detail.msg.trim()) return detail.msg;
      try {
        var text = JSON.stringify(detail);
        if (text && text !== '{}') return text;
      } catch (e) {}
    }
    return fallback;
  }

  function load() {
    fetch(withBranch(API), { credentials: 'same-origin' })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        list = Array.isArray(data) ? data.map(normalizeRow) : [];
        updateRoomSwapButtonUi();
        render();
      })
      .catch(function () {
        list = [];
        updateRoomSwapButtonUi();
        render();
      });
  }

  function telNumericId(item) {
    if (!item || item.source !== 'tel') return null;
    if (typeof item.id === 'string' && item.id.indexOf('tel-') === 0) {
      return parseInt(item.id.slice(4), 10);
    }
    return null;
  }

  function updateRoomSwapButtonUi() {
    if (!roomSwapBtn || !roomSwapConfirmBtn) return;
    roomSwapBtn.classList.toggle('hidden', !staffTimeOk());
    roomSwapBtn.classList.toggle('is-active', roomSwapMode);
    roomSwapBtn.textContent = roomSwapMode ? '교환취소' : '자리교환';
    roomSwapConfirmBtn.classList.toggle('hidden', !roomSwapMode);
    roomSwapConfirmBtn.disabled = roomSwapTargets.length !== 2;
    roomSwapConfirmBtn.textContent = '확인 (' + roomSwapTargets.length + '/2)';
  }

  function roomSwapTargetKey(ref) {
    return ref ? (String(ref.source || '') + ':' + String(ref.id || '')) : '';
  }

  function roomReservationRef(room) {
    if (!room || !room.reserved || !room.reservation_source || !room.reservation_id) return null;
    return {
      room: room.label || '',
      source: String(room.reservation_source || ''),
      id: String(room.reservation_id || ''),
      name: String(room.reservation_name || '')
    };
  }

  function isRoomSwapTarget(room) {
    var ref = roomReservationRef(room);
    if (!ref) return false;
    var key = roomSwapTargetKey(ref);
    return roomSwapTargets.some(function (target) {
      return roomSwapTargetKey(target) === key && String(target.room || '') === String(ref.room || '');
    });
  }

  function clearSwapSelection(silent) {
    roomSwapMode = false;
    roomSwapTargets = [];
    updateRoomSwapButtonUi();
    if (!silent) showToast('자리 교환 대기를 취소했습니다.');
    renderStaffRoomDialog();
  }

  function startSwapSelection() {
    roomSwapMode = true;
    roomSwapTargets = [];
    updateRoomSwapButtonUi();
    refreshStaffRoomAvailability(true);
    showToast('교환할 예약된 자리 2개를 선택한 뒤 확인을 누르세요.');
  }

  function toggleRoomSwapTarget(roomLabel) {
    var room = staffRoomStatus.filter(function (item) {
      return String(item.label || '') === String(roomLabel || '');
    })[0] || null;
    var ref = roomReservationRef(room);
    if (!ref) {
      showToast('예약된 자리만 교환 대상으로 선택할 수 있습니다.');
      return;
    }
    var existingIndex = -1;
    for (var i = 0; i < roomSwapTargets.length; i++) {
      if (roomSwapTargetKey(roomSwapTargets[i]) === roomSwapTargetKey(ref) && String(roomSwapTargets[i].room || '') === String(ref.room || '')) {
        existingIndex = i;
        break;
      }
    }
    if (existingIndex >= 0) {
      roomSwapTargets.splice(existingIndex, 1);
    } else {
      if (roomSwapTargets.length >= 2) {
        showToast('교환할 자리는 2개까지만 선택할 수 있습니다.');
        return;
      }
      roomSwapTargets.push(ref);
    }
    updateRoomSwapButtonUi();
    renderStaffRoomDialog();
  }

  function swapReservations() {
    if (roomSwapTargets.length !== 2) {
      showToast('교환할 예약된 자리 2개를 선택하세요.');
      return;
    }
    if (roomSwapTargetKey(roomSwapTargets[0]) === roomSwapTargetKey(roomSwapTargets[1])) {
      showToast('같은 예약에 묶인 자리는 서로 교환할 수 없습니다.');
      return;
    }
    fetch(withBranch(API + '/swap-rooms'), {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        first_source: roomSwapTargets[0].source,
        first_id: String(roomSwapTargets[0].id),
        second_source: roomSwapTargets[1].source,
        second_id: String(roomSwapTargets[1].id)
      })
    })
      .then(function (r) {
        if (!r.ok) return r.json().then(function (j) { throw new Error((j && j.detail) || '교환 실패'); });
        return r.json();
      })
      .then(function () {
        clearSwapSelection(true);
        showToast('자리 교환을 완료했습니다.');
        load();
        refreshStaffRoomAvailability(true);
      })
      .catch(function (err) {
        showToast((err && err.message) || '교환에 실패했습니다.');
      });
  }

  function render() {
    if (!listEl) return;
    listEl.innerHTML = '';
    list.forEach(function (item, i) {
      var row = document.createElement('div');
      row.className = 'row';
      row.setAttribute('data-index', i);
      row.innerHTML =
        '<span class="row-no">' + (i + 1) + '</span>' +
        '<span class="time">' + escapeHtml(item.time || '—') + '</span>' +
        '<span class="name">' + escapeHtml(item.name || '—') + '</span>' +
        '<span class="room">' + escapeHtml(roomTextFromItem(item)) + '</span>' +
        '<span class="party">' + escapeHtml(partyLine(item)) + '</span>' +
        '<div class="row-actions">' +
          '<button type="button" class="btn btn-edit" data-index="' + i + '">수정</button>' +
          '<button type="button" class="btn btn-del" data-index="' + i + '">삭제</button>' +
        '</div>';
      listEl.appendChild(row);
    });
    listEl.querySelectorAll('.btn-del').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var i = parseInt(btn.getAttribute('data-index'), 10);
        var item = list[i];
        if (!item) return;
        if (item.source === 'tel') {
          var tid = telNumericId(item);
          if (tid == null) {
            showToast('전화 예약 ID를 찾을 수 없습니다.');
            return;
          }
          fetch(withBranch(API_TEL + '/' + tid), { method: 'DELETE', credentials: 'same-origin' })
            .then(function (r) {
              if (!r.ok) throw new Error('삭제 실패');
              return r.json();
            })
            .then(function () {
              if (editingIndex === i) cancelEdit();
              else if (editingIndex > i) editingIndex--;
              showToast('전화 예약을 삭제했습니다.');
              load();
            })
            .catch(function () {
              showToast('삭제에 실패했습니다.');
            });
          return;
        }
        if (item.id == null) {
          showToast('삭제할 당일 예약 ID를 찾을 수 없습니다.');
          return;
        }
        fetch(withBranch(API + '/' + encodeURIComponent(String(item.id))), {
          method: 'DELETE',
          credentials: 'same-origin'
        })
          .then(function (r) {
            if (!r.ok) {
              return r.json()
                .catch(function () { return {}; })
                .then(function (j) {
                  throw new Error(errorDetailText(j && j.detail, '삭제 실패'));
                });
            }
            return r.json();
          })
          .then(function () {
            if (editingIndex === i) cancelEdit();
            else if (editingIndex > i) editingIndex--;
            showToast('삭제되었습니다. 예약현황판에 바로 반영됩니다.');
            load();
          })
          .catch(function (err) {
            load();
            showToast((err && err.message) || '삭제에 실패했습니다.');
          });
      });
    });
    listEl.querySelectorAll('.btn-edit').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var i = parseInt(btn.getAttribute('data-index'), 10);
        var item = list[i];
        if (!item) return;
        document.getElementById('time').value = normalizeTimeValue(item.time || '');
        document.getElementById('name').value = item.name || '';
        setStaffSelectedRooms(parseRoomSelection(item.rooms, item.room));
        applyPartyFromItem(item);
        editingIndex = i;
        roomSwapMode = false;
        roomSwapTargets = [];
        if (formTitle) formTitle.textContent = '예약 수정';
        if (submitBtn) { submitBtn.textContent = '수정'; submitBtn.classList.add('btn-edit-submit'); }
        if (cancelEditBtn) cancelEditBtn.style.display = 'inline-block';
        updateRoomSwapButtonUi();
        document.getElementById('time').focus();
      });
    });
  }

  function cancelEdit() {
    editingIndex = -1;
    roomSwapMode = false;
    roomSwapTargets = [];
    document.getElementById('time').value = '';
    document.getElementById('name').value = '';
    setStaffSelectedRooms([]);
    resetPartyInputs();
    if (formTitle) formTitle.textContent = '예약 추가';
    if (submitBtn) { submitBtn.textContent = '추가'; submitBtn.classList.remove('btn-edit-submit'); }
    if (cancelEditBtn) cancelEditBtn.style.display = 'none';
    updateRoomSwapButtonUi();
  }

  function saveAndNotify(msg) {
    var adminOnly = list.filter(function (r) { return r.source !== 'tel'; });
    var payload = {
      reservations: adminOnly.map(function (r, i) {
        var id = typeof r.id === 'number' ? r.id : (i + 1);
        var p = partyFromItem(r);
        var total = p.adult + p.child + p.infant;
        return {
          id: id,
          time: r.time || '',
          name: r.name || '',
          room: roomTextFromSelection(r.rooms, r.room),
          rooms: parseRoomSelection(r.rooms, r.room),
          count: total > 0 ? total : (r.count != null ? r.count : 2),
          adult: p.adult,
          child: p.child,
          infant: p.infant
        };
      })
    };
    fetch(withBranch(API), {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })
      .then(function (r) {
        if (!r.ok) {
          return r.json()
            .catch(function () { return {}; })
            .then(function (j) {
              throw new Error(errorDetailText(j && j.detail, '저장 실패'));
            });
        }
        return r.json();
      })
      .then(function () {
        showToast(msg || '저장되었습니다. 예약현황판에 바로 반영됩니다.');
        load();
      })
      .catch(function (err) {
        load();
        showToast((err && err.message) || '저장에 실패했습니다.');
      });
  }

  addForm.addEventListener('submit', function (e) {
    e.preventDefault();
    var time = normalizeTimeValue((document.getElementById('time').value || '').trim());
    var name = (document.getElementById('name').value || '').trim();
    var rooms = parseRoomSelection(selectedStaffRooms);
    var room = roomTextFromSelection(rooms);
    if (!time || !name || !rooms.length) {
      showToast('시간, 이름, 호실을 모두 입력하세요.');
      return;
    }
    var partyP = getStaffPartyPayload();
    if (partyP.count < 1) {
      showToast('인원은 1명 이상이어야 합니다.');
      return;
    }
    if (!staffTimeOk(time)) {
      showToast('예약 시간을 선택하세요.');
      return;
    }
    document.getElementById('time').value = time;
    if (editingIndex >= 0) {
      var cur = list[editingIndex];
      if (cur && cur.source === 'tel') {
        var tid = telNumericId(cur);
        if (tid == null) {
          showToast('전화 예약 ID를 찾을 수 없습니다.');
          return;
        }
        fetch(withBranch(API_TEL + '/' + tid), {
          method: 'PATCH',
          credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            time: time,
            name: name,
            room: room,
            rooms: rooms,
            count: partyP.count,
            adult: partyP.adult,
            child: partyP.child,
            infant: partyP.infant
          })
        })
          .then(function (r) {
            if (!r.ok) return r.json().then(function (j) { throw new Error(j.detail || '수정 실패'); });
            return r.json();
          })
          .then(function () {
            cancelEdit();
            showToast('전화 예약을 수정했습니다.');
            load();
          })
          .catch(function (err) {
            showToast(err.message || '수정에 실패했습니다.');
          });
        return;
      }
      list[editingIndex] = {
        time: time,
        name: name,
        room: room,
        rooms: rooms.slice(),
        id: list[editingIndex].id,
        source: 'admin',
        count: partyP.count,
        adult: partyP.adult,
        child: partyP.child,
        infant: partyP.infant
      };
      list.sort(function (a, b) { return (a.time || '').localeCompare(b.time || ''); });
      cancelEdit();
      render();
      showToast('수정했습니다. 현황판에 반영 중…');
      saveAndNotify('수정되었습니다. 예약현황판에 바로 반영됩니다.');
    } else {
      list.push({
        time: time,
        name: name,
        room: room,
        rooms: rooms.slice(),
        source: 'admin',
        count: partyP.count,
        adult: partyP.adult,
        child: partyP.child,
        infant: partyP.infant
      });
      list.sort(function (a, b) { return (a.time || '').localeCompare(b.time || ''); });
      render();
      document.getElementById('time').value = '';
      document.getElementById('name').value = '';
      setStaffSelectedRooms([]);
      resetPartyInputs();
      document.getElementById('time').focus();
      showToast('추가했습니다. 현황판에 반영 중…');
      saveAndNotify('추가되었습니다. 예약현황판에 바로 반영됩니다.');
    }
  });

  if (cancelEditBtn) cancelEditBtn.addEventListener('click', cancelEdit);
  if (roomSwapBtn) roomSwapBtn.addEventListener('click', function () {
    if (roomSwapMode) {
      clearSwapSelection(false);
      return;
    }
    startSwapSelection();
  });
  if (roomSwapConfirmBtn) roomSwapConfirmBtn.addEventListener('click', swapReservations);

  var staffWs = null;

  function connectWs() {
    if (staffWs) {
      try {
        staffWs.close();
      } catch (e) {}
      staffWs = null;
    }
    var protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    var ws = new WebSocket(protocol + '//' + window.location.host + '/ws?' + branchQuery());
    staffWs = ws;
    ws.onmessage = function (ev) {
      try {
        var data = JSON.parse(ev.data);
        if (Array.isArray(data)) {
          list = data.map(normalizeRow);
          render();
        }
      } catch (e) {}
    };
    ws.onclose = function () {
      setTimeout(connectWs, 3000);
    };
    ws.onerror = function () {
      ws.close();
    };
  }

  if (refreshBtn) {
    refreshBtn.addEventListener('click', function () {
      showToast('목록을 불러오는 중…');
      load();
    });
  }

  (function setupTabs() {
    var tabs = document.querySelectorAll('.admin-tab');
    var panelStaff = document.getElementById('panel-staff');
    var panelTel = document.getElementById('panel-tel');
    var panelAll = document.getElementById('panel-all');
    var panelDisplay = document.getElementById('panel-display');
    var panelAccounts = document.getElementById('panel-accounts');
    if (!tabs.length || !panelStaff || !panelTel || !panelAll || !panelDisplay || !panelAccounts) return;
    tabs.forEach(function (btn) {
      btn.addEventListener('click', function () {
        var tab = btn.getAttribute('data-tab');
        tabs.forEach(function (b) {
          var on = b === btn;
          b.classList.toggle('active', on);
          b.setAttribute('aria-selected', on ? 'true' : 'false');
        });
        panelStaff.classList.toggle('hidden', tab !== 'staff');
        panelTel.classList.toggle('hidden', tab !== 'tel');
        panelAll.classList.toggle('hidden', tab !== 'all');
        panelDisplay.classList.toggle('hidden', tab !== 'display');
        panelAccounts.classList.toggle('hidden', tab !== 'accounts');
        if (tab === 'all') {
          refreshAllIframe();
        }
        if (tab === 'accounts' && typeof window.__accountsReload === 'function') {
          window.__accountsReload();
        }
      });
    });
  })();

  function initApp() {
    syncAdminIframes();
    load();
    connectWs();
    if (typeof window.reserveInstallBuildVersionWatcher === 'function') {
      window.reserveInstallBuildVersionWatcher({ intervalMs: 10000 });
    }
  }

  setupStaffTimeDialog();
  setupStaffPartyDialog();
  setupStaffRoomDialog();
  renderStaffRoomDialog();
  resetPartyInputs();
  initApp();

  /* 자정 이후에도 WebSocket이 어제 목록을 유지하는 문제: 주기·탭 복귀 시 서버와 동기화 */
  setInterval(function () {
    load();
  }, 60000);
  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'visible') load();
  });

  (function staffKstClock() {
    var el = document.getElementById('staff-kst-clock');
    if (!el) return;
    function tick() {
      try {
        el.textContent = new Intl.DateTimeFormat('ko-KR', {
          timeZone: 'Asia/Seoul',
          year: 'numeric',
          month: '2-digit',
          day: '2-digit',
          weekday: 'short',
          hour: '2-digit',
          minute: '2-digit',
          second: '2-digit',
          hour12: false
        }).format(new Date());
      } catch (e) {
        el.textContent = '';
      }
    }
    tick();
    setInterval(tick, 1000);
  })();
})();
