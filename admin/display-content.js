/**
 * 현황판(display) 하단 광고 — 목록 표·기본 간격만 (항목 추가 패널 없음)
 */
(function () {
  'use strict';

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

  function apiUrl(path) {
    var base = window.location.origin;
    if (!base || base === 'null' || window.location.protocol === 'file:') {
      base = 'http://127.0.0.1:8000';
    }
    return base + (path.charAt(0) === '/' ? path : '/' + path);
  }

  function apiUrlWithBranch(path) {
    var u = apiUrl(path);
    return u + (u.indexOf('?') >= 0 ? '&' : '?') + 'branch=' + encodeURIComponent(getBranch());
  }

  function contentApiUrl() {
    return apiUrlWithBranch('/api/display/content');
  }

  var defaultIntervalEl = document.getElementById('dc-default-interval');
  var toastEl = document.getElementById('dc-toast');
  var items = [];

  function getDefaultSec() {
    var di = defaultIntervalEl ? parseInt(defaultIntervalEl.value, 10) : 8;
    if (isNaN(di)) di = 8;
    return Math.max(3, Math.min(600, di));
  }

  function urlToLabel(url) {
    var u = String(url || '').trim();
    if (!u) return '—';
    try {
      var noQ = u.split('?')[0];
      var parts = noQ.split('/').filter(function (x) {
        return x.length;
      });
      var last = parts[parts.length - 1];
      if (last) {
        return last.length > 96 ? last.slice(0, 93) + '…' : last;
      }
    } catch (e) {}
    return u.length > 96 ? u.slice(0, 93) + '…' : u;
  }

  function contentDisplayName(it) {
    var n = it.name != null ? String(it.name).trim() : '';
    if (n) return n.length > 120 ? n.slice(0, 117) + '…' : n;
    return urlToLabel(it.url);
  }

  function formatDisplayTime(it) {
    if (it.type === 'video') return '재생 끝까지';
    var d = it.duration_sec;
    if (d != null && d !== '' && !isNaN(parseInt(d, 10))) {
      return parseInt(d, 10) + '초';
    }
    var def = getDefaultSec();
    return '기본(' + def + '초)';
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

  function renderSummary() {
    var tbody = document.getElementById('dc-summary-body');
    var emptyEl = document.getElementById('dc-summary-empty');
    var tableWrap = document.querySelector('#dc-summary-wrap .dc-summary-table-wrap');
    if (!tbody) return;
    while (tbody.firstChild) {
      tbody.removeChild(tbody.firstChild);
    }
    if (!items.length) {
      if (emptyEl) emptyEl.hidden = false;
      if (tableWrap) tableWrap.hidden = true;
      return;
    }
    if (emptyEl) emptyEl.hidden = true;
    if (tableWrap) tableWrap.hidden = false;
    var n = items.length;
    items.forEach(function (it, i) {
      var tr = document.createElement('tr');
      var typeLabel = it.type === 'video' ? '동영상' : '이미지';
      var td1 = document.createElement('td');
      td1.className = 'col-order';
      td1.textContent = String(i + 1);
      var td2 = document.createElement('td');
      td2.className = 'col-type';
      td2.textContent = typeLabel;
      var td3 = document.createElement('td');
      td3.textContent = formatDisplayTime(it);
      var td4 = document.createElement('td');
      td4.className = 'col-name';
      td4.textContent = contentDisplayName(it);
      var tdMove = document.createElement('td');
      tdMove.className = 'col-move';
      var btnUp = document.createElement('button');
      btnUp.type = 'button';
      btnUp.className = 'btn dc-move dc-summary-move-up';
      btnUp.setAttribute('data-index', String(i));
      btnUp.setAttribute('title', '위로');
      btnUp.setAttribute('aria-label', '위로');
      btnUp.disabled = i === 0;
      btnUp.textContent = '↑';
      var btnDn = document.createElement('button');
      btnDn.type = 'button';
      btnDn.className = 'btn dc-move dc-summary-move-down';
      btnDn.setAttribute('data-index', String(i));
      btnDn.setAttribute('title', '아래로');
      btnDn.setAttribute('aria-label', '아래로');
      btnDn.disabled = i >= n - 1;
      btnDn.textContent = '↓';
      tdMove.appendChild(btnUp);
      tdMove.appendChild(btnDn);
      var td5 = document.createElement('td');
      td5.className = 'col-del';
      var delBtn = document.createElement('button');
      delBtn.type = 'button';
      delBtn.className = 'btn btn-del dc-summary-del';
      delBtn.setAttribute('data-index', String(i));
      delBtn.setAttribute('title', '이 항목 삭제');
      delBtn.setAttribute('aria-label', '삭제');
      delBtn.textContent = '삭제';
      td5.appendChild(delBtn);
      tr.appendChild(td1);
      tr.appendChild(td2);
      tr.appendChild(td3);
      tr.appendChild(td4);
      tr.appendChild(tdMove);
      tr.appendChild(td5);
      tbody.appendChild(tr);
    });
  }

  function render() {
    renderSummary();
  }

  function save() {
    var prevSnap = items.map(function (it) {
      return {
        type: it.type,
        url: it.url,
        name: it.name,
        duration_sec: it.duration_sec
      };
    });
    items.forEach(function (it, i) {
      if (!String(it.name || '').trim() && prevSnap[i] && String(prevSnap[i].url || '') === String(it.url || '') && String(prevSnap[i].name || '').trim()) {
        it.name = String(prevSnap[i].name).trim();
      }
    });
    var di = defaultIntervalEl ? parseInt(defaultIntervalEl.value, 10) : 8;
    if (isNaN(di)) di = 8;
    fetch(contentApiUrl(), {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        items: items.map(function (it) {
          return {
            type: it.type,
            url: it.url,
            name: it.name != null && it.name !== undefined ? String(it.name) : '',
            duration_sec: it.duration_sec === undefined ? null : it.duration_sec
          };
        }),
        default_interval_sec: di
      })
    })
      .then(function (r) {
        if (!r.ok) return r.json().then(function (j) {
          throw new Error((j && j.detail) ? (typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail)) : '저장 실패');
        });
        return r.json();
      })
      .then(function () {
        showToast('저장했습니다.');
        return load({ hideUrlInForm: true });
      })
      .then(function () {
        var wrap = document.getElementById('dc-summary-wrap');
        if (wrap) {
          wrap.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
      })
      .catch(function (err) {
        showToast(err.message || '저장에 실패했습니다.');
      });
  }

  function load(options) {
    options = options || {};
    return fetch(contentApiUrl(), { credentials: 'same-origin' })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        var raw = Array.isArray(data.items) ? data.items : [];
        items = raw.map(function (x) {
          var isVid = x.type === 'video';
          return {
            id: x.id || '',
            type: isVid ? 'video' : 'image',
            url: x.url || '',
            name: x.name != null ? String(x.name) : '',
            duration_sec: isVid ? null : (x.duration_sec != null ? x.duration_sec : null)
          };
        });
        if (defaultIntervalEl) {
          var di = parseInt(data.default_interval_sec, 10);
          if (!isNaN(di)) defaultIntervalEl.value = String(Math.max(3, Math.min(600, di)));
        }
        render();
      })
      .catch(function () {
        items = [];
        render();
        showToast('목록을 불러오지 못했습니다.');
      });
  }

  var summaryWrap = document.getElementById('dc-summary-wrap');
  if (summaryWrap) {
    summaryWrap.addEventListener('click', function (e) {
      var del = e.target.closest('.dc-summary-del');
      if (del) {
        e.preventDefault();
        var ix = parseInt(del.getAttribute('data-index'), 10);
        if (isNaN(ix)) return;
        items.splice(ix, 1);
        render();
        save();
        return;
      }
      var up = e.target.closest('.dc-summary-move-up');
      if (up && !up.disabled) {
        e.preventDefault();
        var iu = parseInt(up.getAttribute('data-index'), 10);
        if (isNaN(iu) || iu <= 0) return;
        var tmp = items[iu - 1];
        items[iu - 1] = items[iu];
        items[iu] = tmp;
        render();
        save();
        return;
      }
      var dn = e.target.closest('.dc-summary-move-down');
      if (dn && !dn.disabled) {
        e.preventDefault();
        var id = parseInt(dn.getAttribute('data-index'), 10);
        if (isNaN(id) || id >= items.length - 1) return;
        var t2 = items[id + 1];
        items[id + 1] = items[id];
        items[id] = t2;
        render();
        save();
      }
    });
  }

  var clearBtn = document.getElementById('dc-summary-clear');
  if (clearBtn) {
    clearBtn.addEventListener('click', function () {
      if (!items.length) return;
      if (!confirm('등록된 항목을 모두 삭제할까요?')) return;
      items = [];
      render();
      save();
    });
  }

  load();
})();
