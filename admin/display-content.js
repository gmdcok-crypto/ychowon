/**
 * 현황판(display) 하단 광고 — 추가 패널 + 목록 표만 사용
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
      return v && String(v).trim() ? String(v).trim() : 'default';
    } catch (e2) {
      return 'default';
    }
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

  var API = apiUrlWithBranch('/api/display/content');
  var API_UPLOAD = apiUrl('/api/display/upload');
  var addPanelEl = document.getElementById('dc-add-panel');
  var defaultIntervalEl = document.getElementById('dc-default-interval');
  var toastEl = document.getElementById('dc-toast');
  var items = [];
  var addPanelBound = false;

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

  function looksLikeUrl(v) {
    var s = String(v || '').trim();
    return s.indexOf('http://') === 0 || s.indexOf('https://') === 0 || s.indexOf('/') === 0;
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

  function uploadDisplayFile(file) {
    var fd = new FormData();
    fd.append('file', file);
    return fetch(API_UPLOAD, { method: 'POST', credentials: 'same-origin', body: fd }).then(function (r) {
      if (!r.ok) {
        return r.json().then(function (j) {
          var d = j && j.detail;
          throw new Error(typeof d === 'string' ? d : (d ? JSON.stringify(d) : '업로드 실패'));
        });
      }
      return r.json();
    });
  }

  function guessTypeFromFile(f) {
    var mt = (f && f.type) ? String(f.type) : '';
    if (mt.indexOf('video') === 0) return 'video';
    if (mt.indexOf('image') === 0) return 'image';
    var ext = ((f && f.name) ? f.name : '').split('.').pop().toLowerCase();
    if ({ mp4: 1, webm: 1, mov: 1, m4v: 1 }[ext]) return 'video';
    return 'image';
  }

  function displayNameFromUpload(data, f, url) {
    var fromServer = data && data.original_name != null ? String(data.original_name).trim() : '';
    if (fromServer) return fromServer;
    if (f && f.name) return String(f.name).trim();
    try {
      var parts = String(url || '').split('/').filter(function (x) {
        return x.length;
      });
      return parts.length ? parts[parts.length - 1] : '';
    } catch (e) {
      return '';
    }
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

  function updateAddPanelDurationVisibility() {
    var typeEl = document.getElementById('dc-add-type');
    var lab = document.querySelector('.dc-add-duration-label');
    var inp = document.getElementById('dc-add-duration');
    if (!typeEl || !inp) return;
    var hide = typeEl.value === 'video';
    if (lab) lab.hidden = hide;
    inp.hidden = hide;
  }

  function resetAddPanel() {
    var nameEl = document.getElementById('dc-add-name');
    var realEl = document.getElementById('dc-add-url-real');
    var urlEl = document.getElementById('dc-add-url');
    var typeEl = document.getElementById('dc-add-type');
    var durEl = document.getElementById('dc-add-duration');
    var fileEl = document.getElementById('dc-add-file');
    if (nameEl) nameEl.value = '';
    if (realEl) realEl.value = '';
    if (urlEl) urlEl.value = '';
    if (typeEl) typeEl.value = 'image';
    if (durEl) durEl.value = '';
    if (fileEl) fileEl.value = '';
    updateAddPanelDurationVisibility();
  }

  function readAddPanel() {
    var typeEl = document.getElementById('dc-add-type');
    var urlEl = document.getElementById('dc-add-url');
    var realEl = document.getElementById('dc-add-url-real');
    var nameEl = document.getElementById('dc-add-name');
    var durEl = document.getElementById('dc-add-duration');
    var visRaw = urlEl && urlEl.value ? urlEl.value.trim() : '';
    var urlVal = '';
    if (realEl && realEl.value.trim()) {
      urlVal = realEl.value.trim();
    } else if (visRaw && looksLikeUrl(visRaw)) {
      urlVal = visRaw;
    }
    var nameVal = '';
    if (urlVal && visRaw && !looksLikeUrl(visRaw)) {
      nameVal = visRaw;
    } else if (nameEl && nameEl.value.trim()) {
      nameVal = nameEl.value.trim();
    }
    var isVid = typeEl && typeEl.value === 'video';
    var durRaw = durEl && durEl.value ? durEl.value.trim() : '';
    var dur = durRaw === '' ? null : parseInt(durRaw, 10);
    if (dur !== null && (isNaN(dur) || dur < 3 || dur > 600)) dur = null;
    return {
      id: '',
      type: isVid ? 'video' : 'image',
      url: urlVal,
      name: nameVal,
      duration_sec: isVid ? null : dur
    };
  }

  function showAddPanel() {
    if (!addPanelEl) return;
    addPanelEl.hidden = false;
    resetAddPanel();
  }

  function hideAddPanel() {
    if (!addPanelEl) return;
    addPanelEl.hidden = true;
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
    fetch(API, {
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
    return fetch(API, { credentials: 'same-origin' })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        var raw = Array.isArray(data.items) ? data.items : [];
        items = raw.map(function (x) {
          var isVid = x.type === 'video';
          var o = {
            id: x.id || '',
            type: isVid ? 'video' : 'image',
            url: x.url || '',
            name: x.name != null ? String(x.name) : '',
            duration_sec: isVid ? null : (x.duration_sec != null ? x.duration_sec : null)
          };
          if (options.hideUrlInForm && o.url) o._hideUrlInForm = true;
          return o;
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

  function commitAddPanelFromUrl() {
    var it = readAddPanel();
    if (!String(it.url || '').trim()) {
      showToast('URL을 입력하거나 파일을 선택하세요.');
      return;
    }
    items.push(it);
    resetAddPanel();
    saveQuiet();
  }

  function bindAddPanel() {
    if (addPanelBound) return;
    addPanelBound = true;
    var typeEl = document.getElementById('dc-add-type');
    if (typeEl) {
      typeEl.addEventListener('change', updateAddPanelDurationVisibility);
    }
    var urlEl = document.getElementById('dc-add-url');
    var realEl = document.getElementById('dc-add-url-real');
    var nameEl = document.getElementById('dc-add-name');
    if (urlEl) {
      urlEl.addEventListener('keydown', function (e) {
        if (e.key === 'Enter') {
          e.preventDefault();
          commitAddPanelFromUrl();
        }
      });
      urlEl.addEventListener('input', function () {
        var v = urlEl.value.trim();
        if (realEl && realEl.value.trim() && v && !looksLikeUrl(v) && nameEl) {
          nameEl.value = v;
        }
      });
      urlEl.addEventListener('blur', function () {
        var v = urlEl.value.trim();
        if (!v) {
          if (realEl && realEl.value.trim()) return;
          if (realEl) realEl.value = '';
          if (nameEl) nameEl.value = '';
          return;
        }
        if (looksLikeUrl(v)) {
          if (realEl) realEl.value = v;
          if (nameEl) nameEl.value = '';
          return;
        }
        if (realEl && realEl.value.trim() && nameEl) {
          nameEl.value = v;
        }
      });
    }
    var fileEl = document.getElementById('dc-add-file');
    if (fileEl) {
      fileEl.addEventListener('change', function () {
        var f = fileEl.files && fileEl.files[0];
        fileEl.value = '';
        if (!f) return;
        showToast('업로드 중…');
        uploadDisplayFile(f)
          .then(function (data) {
            var u = (data && data.url) ? data.url : '';
            var picked = displayNameFromUpload(data, f, u);
            var typeSel = document.getElementById('dc-add-type');
            if (typeSel) {
              typeSel.value = guessTypeFromFile(f);
              updateAddPanelDurationVisibility();
            }
            var durEl = document.getElementById('dc-add-duration');
            var durRaw = durEl && durEl.value ? durEl.value.trim() : '';
            var dur = durRaw === '' ? null : parseInt(durRaw, 10);
            if (dur !== null && (isNaN(dur) || dur < 3 || dur > 600)) dur = null;
            var isVid = typeSel && typeSel.value === 'video';
            var newItem = {
              id: '',
              type: isVid ? 'video' : 'image',
              url: u,
              name: picked || '',
              duration_sec: isVid ? null : dur
            };
            items.push(newItem);
            resetAddPanel();
            return saveQuiet();
          })
          .catch(function (err) {
            showToast(err.message || '업로드에 실패했습니다.');
          });
      });
    }
    var closeBtn = document.getElementById('dc-add-close');
    if (closeBtn) {
      closeBtn.addEventListener('click', function () {
        hideAddPanel();
      });
    }
  }

  function saveQuiet() {
    var di = defaultIntervalEl ? parseInt(defaultIntervalEl.value, 10) : 8;
    if (isNaN(di)) di = 8;
    return fetch(API, {
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
        showToast('목록·현황판에 반영했습니다.');
        return load({ hideUrlInForm: true });
      })
      .catch(function (err) {
        items.pop();
        showToast(err.message || '저장에 실패했습니다.');
      });
  }

  var addBtn = document.getElementById('dc-add');
  if (addBtn) {
    addBtn.addEventListener('click', function () {
      showAddPanel();
    });
  }

  bindAddPanel();

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
