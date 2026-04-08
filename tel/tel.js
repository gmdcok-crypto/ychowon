(function () {
  'use strict';

  var API_TEL_RESERVATIONS = '/api/tel/reservations';
  var API_TEL_ROOMS = '/api/tel/rooms';
  var BRANCH_KEY = 'reserve_branch_id';

  function getTelBranch() {
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
    return 'branch=' + encodeURIComponent(getTelBranch());
  }

  function withBranch(url) {
    var sep = url.indexOf('?') >= 0 ? '&' : '?';
    return url + sep + branchQuery();
  }

  var today = new Date();
  var currentMonth = today.getMonth();
  var currentYear = today.getFullYear();
  var selectedDate = today;
  var selectedFilter = 'all';
  var selectedRoomSection = 'all';
  var telReservations = [];
  var roomStatus = [];

  var monthLabel = document.getElementById('month-label');
  var calGrid = document.getElementById('calendar-grid');
  var selectedDateLabel = document.getElementById('selected-date-label');
  var formDateLabel = document.getElementById('form-date-label');
  var toastEl = document.getElementById('tel-toast');
  var reserveListEl = document.getElementById('reserve-list');
  var formEl = document.getElementById('tel-form');
  var roomInput = document.getElementById('tel-room');
  var timeInput = document.getElementById('tel-time');
  var phoneInput = document.getElementById('tel-phone');
  var nameInput = document.getElementById('tel-name');
  var adultInput = document.getElementById('tel-count-adult');
  var childInput = document.getElementById('tel-count-child');
  var infantInput = document.getElementById('tel-count-infant');
  var roomDialog = document.getElementById('room-dialog');
  var roomDialogMeta = document.getElementById('room-dialog-meta');
  var roomGroupTabs = document.getElementById('room-group-tabs');
  var roomGrid = document.getElementById('room-grid');

  function formatDate(d) {
    var y = d.getFullYear();
    var m = String(d.getMonth() + 1).padStart(2, '0');
    var day = String(d.getDate()).padStart(2, '0');
    var week = ['일', '월', '화', '수', '목', '금', '토'][d.getDay()];
    return y + '.' + m + '.' + day + ' (' + week + ')';
  }

  function sameDate(a, b) {
    return a && b &&
      a.getFullYear() === b.getFullYear() &&
      a.getMonth() === b.getMonth() &&
      a.getDate() === b.getDate();
  }

  function dateKey(d) {
    return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
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

  /** 예약조회(all.js)와 동일한 인원 표기 */
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

  function showToast(msg) {
    if (!toastEl) return;
    toastEl.textContent = msg;
    toastEl.classList.add('show');
    clearTimeout(toastEl._t);
    toastEl._t = setTimeout(function () {
      toastEl.classList.remove('show');
    }, 2200);
  }

  function updateDateLabels() {
    selectedDateLabel.textContent = formatDate(selectedDate);
    formDateLabel.textContent = formatDate(selectedDate) + ' 예약 접수';
  }

  function renderCalendar() {
    var firstDay = new Date(currentYear, currentMonth, 1);
    var startDay = firstDay.getDay();
    var daysInMonth = new Date(currentYear, currentMonth + 1, 0).getDate();

    monthLabel.textContent = currentYear + '년 ' + (currentMonth + 1) + '월';
    calGrid.innerHTML = '';

    for (var i = 0; i < startDay; i++) {
      calGrid.appendChild(document.createElement('div'));
    }

    for (var d = 1; d <= daysInMonth; d++) {
      (function (dayNum) {
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'day-cell';
        var dd = new Date(currentYear, currentMonth, dayNum);

        var num = document.createElement('span');
        num.className = 'num';
        num.textContent = dayNum;
        btn.appendChild(num);

        if (sameDate(dd, today)) btn.classList.add('today');
        if (sameDate(dd, selectedDate)) btn.classList.add('selected');

        btn.addEventListener('click', function () {
          selectedDate = dd;
          updateDateLabels();
          renderCalendar();
          fetchTelReservations();
          refreshRoomAvailability(false);
        });

        calGrid.appendChild(btn);
      })(d);
    }
  }

  function renderReserveList() {
    if (!reserveListEl) return;
    var list = telReservations.filter(function (item) {
      if (selectedFilter === 'all') return true;
      return item.slot === selectedFilter;
    });

    if (!list.length) {
      reserveListEl.innerHTML = '<div class="empty">선택한 날짜의 예약이 없습니다.</div>';
      return;
    }

    /* 열 순서: 시간 → 이름 → 룸/테이블 → 인원 */
    var head =
      '<div class="reserve-row reserve-head">' +
        '<span class="col-time">시간</span>' +
        '<span class="col-name">이름</span>' +
        '<span class="col-room">룸/테이블</span>' +
        '<span class="col-party">인원</span>' +
      '</div>';
    reserveListEl.innerHTML = head + list.map(function (item) {
      return (
        '<div class="reserve-row">' +
          '<span class="time col-time">' + escapeHtml(item.time) + '</span>' +
          '<span class="name col-name">' + escapeHtml(item.name) + '</span>' +
          '<span class="room col-room">' + escapeHtml(item.room) + '</span>' +
          '<span class="party col-party">' + escapeHtml(partyLine(item)) + '</span>' +
        '</div>'
      );
    }).join('');
  }

  function fetchTelReservations() {
    return fetch(withBranch(API_TEL_RESERVATIONS + '?date=' + encodeURIComponent(dateKey(selectedDate))), { credentials: 'same-origin' })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        telReservations = Array.isArray(data) ? data : [];
        renderReserveList();
      })
      .catch(function () {
        telReservations = [];
        renderReserveList();
      });
  }

  function renderRoomDialog() {
    if (!roomGrid || !roomGroupTabs) return;
    if (!timeInput.value) {
      roomGroupTabs.innerHTML = '';
      roomGrid.innerHTML = '<div class="empty">예약 시간을 먼저 선택하세요.</div>';
      return;
    }

    var sections = ['all'];
    roomStatus.forEach(function (room) {
      var section = room.section || '기타';
      if (sections.indexOf(section) === -1) {
        sections.push(section);
      }
    });

    if (sections.indexOf(selectedRoomSection) === -1) {
      selectedRoomSection = 'all';
    }

    roomGroupTabs.innerHTML = sections.map(function (section) {
      var label = section === 'all' ? '전체' : section;
      var activeClass = selectedRoomSection === section ? ' active' : '';
      return '<button type="button" class="room-group-tab' + activeClass + '" data-section="' + escapeHtml(section) + '">' + escapeHtml(label) + '</button>';
    }).join('');

    roomGroupTabs.querySelectorAll('.room-group-tab').forEach(function (btn) {
      btn.addEventListener('click', function () {
        selectedRoomSection = btn.getAttribute('data-section') || 'all';
        renderRoomDialog();
      });
    });

    var filteredRooms = roomStatus.filter(function (room) {
      if (selectedRoomSection === 'all') return true;
      return (room.section || '기타') === selectedRoomSection;
    });

    roomGrid.innerHTML = filteredRooms.map(function (room) {
      var className = 'room-option';
      var roomName = room.display_label || room.label;
      var selectedTimeText = timeInput.value ? (timeInput.value + ' 기준') : '';
      var occupiedRanges = Array.isArray(room.occupied_ranges) ? room.occupied_ranges : [];
      if (room.reserved) className += ' reserved';
      if (roomInput.value === room.label) className += ' selected';
      var base = selectedRoomSection === 'all' && room.section ? room.section + ' · ' : '';
      var statusText = room.reserved ? '예약 완료' : '선택 가능';
      var timeText = room.reserved ? (room.reservation_range || room.time || timeInput.value || '') : selectedTimeText;
      var nameText = room.reserved && room.reservation_name ? (' · ' + room.reservation_name) : '';
      var sub = base + statusText + (timeText ? (' · ' + timeText) : '') + nameText;
      var timeSummary = occupiedRanges.length ? ('점유 시간: ' + occupiedRanges.join(', ')) : '점유 시간 없음';
      return (
        '<button type="button" class="' + className + '" data-room="' + escapeHtml(room.label) + '"' +
        (room.reserved ? ' disabled' : '') + '>' +
          '<span class="room-name">' + escapeHtml(roomName) + '</span>' +
          '<span class="room-sub">' + escapeHtml(sub) + '</span>' +
          '<span class="room-sub">' + escapeHtml(timeSummary) + '</span>' +
        '</button>'
      );
    }).join('');

    if (!filteredRooms.length) {
      roomGrid.innerHTML = '<div class="empty">이 구역에 등록된 자리가 없습니다.</div>';
    }

    roomGrid.querySelectorAll('.room-option').forEach(function (btn) {
      btn.addEventListener('click', function () {
        if (btn.disabled) return;
        roomInput.value = btn.getAttribute('data-room') || '';
        closeRoomDialog();
      });
    });
  }

  function refreshRoomAvailability(openIfNeeded) {
    if (!selectedDate || !timeInput.value) {
      roomStatus = [];
      if (openIfNeeded) renderRoomDialog();
      return Promise.resolve();
    }

    var query = '?date=' + encodeURIComponent(dateKey(selectedDate)) + '&time=' + encodeURIComponent(timeInput.value) + '&' + branchQuery();
    roomDialogMeta.textContent = formatDate(selectedDate) + ' · ' + timeInput.value + ' 기준';

    return fetch(API_TEL_ROOMS + query, { credentials: 'same-origin' })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        roomStatus = Array.isArray(data.rooms) ? data.rooms : [];
        var current = roomStatus.filter(function (room) { return room.label === roomInput.value; })[0];
        if (current && current.reserved) {
          roomInput.value = '';
          showToast('선택한 시간에 이미 예약된 자리입니다. 다시 선택하세요.');
        }
        if (openIfNeeded || !roomDialog.classList.contains('hidden')) {
          renderRoomDialog();
        }
      })
      .catch(function () {
        roomStatus = [];
        roomGroupTabs.innerHTML = '';
        if (openIfNeeded || !roomDialog.classList.contains('hidden')) {
          roomGrid.innerHTML = '<div class="empty">호실 정보를 불러오지 못했습니다.</div>';
        }
      });
  }

  function openRoomDialog() {
    if (!selectedDate) {
      showToast('먼저 예약 날짜를 선택하세요.');
      return;
    }
    if (!timeInput.value) {
      showToast('먼저 예약 시간을 선택하세요.');
      return;
    }
    roomDialog.classList.remove('hidden');
    roomDialog.setAttribute('aria-hidden', 'false');
    refreshRoomAvailability(true);
  }

  function closeRoomDialog() {
    roomDialog.classList.add('hidden');
    roomDialog.setAttribute('aria-hidden', 'true');
  }

  function setupTime() {
    var tabs = document.querySelectorAll('.time-tab');
    var lunchBox = document.getElementById('time-buttons-lunch');
    var dinnerBox = document.getElementById('time-buttons-dinner');
    var timeButtons = document.querySelectorAll('.time-btn');

    function setTab(slot) {
      tabs.forEach(function (t) {
        t.classList.toggle('active', t.getAttribute('data-slot') === slot);
      });
      if (slot === 'lunch') {
        lunchBox.classList.remove('hidden');
        dinnerBox.classList.add('hidden');
      } else {
        lunchBox.classList.add('hidden');
        dinnerBox.classList.remove('hidden');
      }
    }

    function setTime(value) {
      timeInput.value = value;
      timeButtons.forEach(function (b) {
        b.classList.toggle('active', b.getAttribute('data-time') === value);
      });
      refreshRoomAvailability(false);
      renderReserveList();
    }

    tabs.forEach(function (tab) {
      tab.addEventListener('click', function () {
        setTab(tab.getAttribute('data-slot') || 'lunch');
      });
    });

    timeButtons.forEach(function (btn) {
      btn.addEventListener('click', function () {
        setTime(btn.getAttribute('data-time') || '');
      });
    });

    if (!timeInput.value) setTime('12:00');
    setTab('lunch');
  }

  function setupCount() {
    document.querySelectorAll('.step[data-target]').forEach(function (btn) {
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
      });
    });
  }

  function setupFocusScroll() {
    var inputs = formEl.querySelectorAll('input');
    inputs.forEach(function (input) {
      input.addEventListener('focus', function () {
        var el = this;
        if (el.readOnly) return;
        function doScroll() {
          var panel = el.closest && el.closest('.panel');
          if (panel && panel.scrollHeight > panel.clientHeight) {
            var elTop = el.getBoundingClientRect().top;
            var panelTop = panel.getBoundingClientRect().top;
            var margin = 24;
            var newScroll = panel.scrollTop + (elTop - panelTop) - margin;
            panel.scrollTop = Math.max(0, Math.min(newScroll, panel.scrollHeight - panel.clientHeight));
          }
          el.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
        setTimeout(doScroll, 350);
        setTimeout(doScroll, 700);
      });
    });
  }

  function setupFilters() {
    document.querySelectorAll('.chip').forEach(function (chip) {
      chip.addEventListener('click', function () {
        selectedFilter = chip.getAttribute('data-filter') || 'all';
        document.querySelectorAll('.chip').forEach(function (item) {
          item.classList.toggle('chip-on', item === chip);
        });
        renderReserveList();
      });
    });
  }

  function setupRoomDialog() {
    document.getElementById('tel-room-open').addEventListener('click', openRoomDialog);
    roomInput.addEventListener('click', openRoomDialog);
    document.getElementById('room-dialog-close').addEventListener('click', closeRoomDialog);
    document.getElementById('room-dialog-backdrop').addEventListener('click', closeRoomDialog);
  }

  function requestFullscreenOn(el) {
    if (!el) return Promise.reject(new Error('no element'));
    var req =
      el.requestFullscreen ||
      el.webkitRequestFullscreen ||
      el.mozRequestFullScreen ||
      el.msRequestFullscreen;
    if (req) return req.call(el);
    return Promise.reject(new Error('no fullscreen'));
  }

  /** document → body 순으로 시도 (브라우저마다 동작이 다름). */
  function tryEnterFullscreen() {
    if (document.fullscreenElement) return Promise.resolve();
    return requestFullscreenOn(document.documentElement).catch(function () {
      return requestFullscreenOn(document.body);
    });
  }

  /**
   * HTTPS + 크롬/파이어폭스: 전체화면 API.
   * iOS Safari 일반 탭: 문서 전체 전체화면 미지원 → 주소창 유지. 홈 화면 추가 후 아이콘 실행이 가장 확실.
   * PC(마우스): 재시도 스케줄 생략 — 태블릿·터치 기기에서만 키오스크식 재시도.
   */
  function setupFullscreen() {
    /* admin 등 상위 페이지 안 iframe: 태블릿용 전체화면·제스처만 iframe 문서로 가서 PC에서 혼란 — 비활성화 */
    try {
      if (window.self !== window.top) return;
    } catch (e) {
      return;
    }

    var gestureEvents = ['pointerdown', 'touchstart', 'touchend', 'click'];
    var iosHintShown = false;

    /** 태블릿/폰 위주로 공격적 전체화면 시도 (PC는 사용자가 클릭할 때만) */
    function preferKioskFullscreen() {
      if (window.matchMedia && window.matchMedia('(pointer: coarse)').matches) return true;
      if (typeof window.orientation !== 'undefined') return true;
      if ('ontouchstart' in window) return true;
      if (window.innerWidth < 900) return true;
      return false;
    }

    /** 브라우저 UI가 거의 없는 모드(설치 앱·아이콘 실행). minimal-ui는 주소줄이 남을 수 있어 제외 → 전체화면 API로 보완 */
    function isStandalonePwa() {
      return (
        (window.matchMedia && window.matchMedia('(display-mode: fullscreen)').matches) ||
        (window.matchMedia && window.matchMedia('(display-mode: standalone)').matches) ||
        window.navigator.standalone === true
      );
    }

    function maybeShowIosHint() {
      if (iosHintShown || isStandalonePwa()) return;
      var iOS = /iPad|iPhone|iPod/.test(navigator.userAgent) ||
        (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
      if (!iOS || document.fullscreenElement) return;
      try {
        if (sessionStorage.getItem('tel-fs-hint')) return;
        sessionStorage.setItem('tel-fs-hint', '1');
      } catch (e) {}
      iosHintShown = true;
      showToast('Safari에서는 주소창이 남을 수 있습니다. 홈 화면에 추가 후 아이콘으로 열면 전체처럼 쓸 수 있습니다.');
    }

    function detachGesture() {
      gestureEvents.forEach(function (ev) {
        window.removeEventListener(ev, onGesture, true);
      });
    }

    function onGesture() {
      if (document.fullscreenElement) {
        detachGesture();
        return;
      }
      tryEnterFullscreen()
        .then(function () {
          detachGesture();
        })
        .catch(function () {});
    }

    function scheduleRetries() {
      [0, 80, 250, 600].forEach(function (ms) {
        setTimeout(function () {
          if (!document.fullscreenElement) tryEnterFullscreen().catch(function () {});
        }, ms);
      });
    }

    if (!isStandalonePwa()) {
      var kiosk = preferKioskFullscreen();
      tryEnterFullscreen().catch(function () {});
      if (kiosk) {
        scheduleRetries();
        window.addEventListener('load', function () {
          setTimeout(function () {
            tryEnterFullscreen().catch(function () {});
          }, 0);
        });
      }
    }

    gestureEvents.forEach(function (ev) {
      window.addEventListener(ev, onGesture, true);
    });

    setTimeout(function () {
      if (!document.fullscreenElement) maybeShowIosHint();
    }, 1200);

    // iOS 인앱 브라우저 등: 스크롤로 주소창 최소화 시도(완전 제거는 불가한 경우 많음)
    if (/iPad|iPhone|iPod/.test(navigator.userAgent)) {
      setTimeout(function () {
        window.scrollTo(0, 1);
      }, 350);
    }
  }

  formEl.addEventListener('submit', function (e) {
    e.preventDefault();
    if (!selectedDate) {
      showToast('먼저 왼쪽에서 예약 일자를 선택하세요.');
      return;
    }

    var adult = parseInt(adultInput.value, 10) || 0;
    var child = parseInt(childInput.value, 10) || 0;
    var infant = parseInt(infantInput.value, 10) || 0;
    var total = adult + child + infant;

    var payload = {
      date: dateKey(selectedDate),
      time: (timeInput.value || '').trim(),
      phone: (phoneInput.value || '').trim(),
      name: (nameInput.value || '').trim(),
      room: (roomInput.value || '').trim(),
      count: total,
      adult: adult,
      child: child,
      infant: infant,
      slot: timeSlot(timeInput.value)
    };

    if (!payload.phone || !payload.name || !payload.time || !payload.room) {
      showToast('전화번호, 이름, 시간, 룸을 모두 입력하세요.');
      return;
    }
    if (total < 1) {
      showToast('인원은 1명 이상이어야 합니다.');
      return;
    }

    fetch(withBranch(API_TEL_RESERVATIONS), {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })
      .then(function (r) {
        return r.json().then(function (data) {
          return { ok: r.ok, data: data };
        });
      })
      .then(function (result) {
        if (!result.ok) {
          throw new Error(result.data.detail || '예약 저장에 실패했습니다.');
        }
        phoneInput.value = '';
        nameInput.value = '';
        roomInput.value = '';
        adultInput.value = '2';
        childInput.value = '0';
        infantInput.value = '0';
        showToast('예약이 등록되었습니다.');
        return fetchTelReservations().then(function () {
          return refreshRoomAvailability(false);
        });
      })
      .catch(function (err) {
        showToast(err.message || '예약 저장에 실패했습니다.');
      });
  });

  document.getElementById('month-prev').addEventListener('click', function () {
    currentMonth--;
    if (currentMonth < 0) { currentMonth = 11; currentYear--; }
    renderCalendar();
  });

  document.getElementById('month-next').addEventListener('click', function () {
    currentMonth++;
    if (currentMonth > 11) { currentMonth = 0; currentYear++; }
    renderCalendar();
  });

  updateDateLabels();
  renderCalendar();
  setupTime();
  setupCount();
  setupFocusScroll();
  setupFilters();
  setupRoomDialog();
  setupFullscreen();
  fetchTelReservations();
})();
