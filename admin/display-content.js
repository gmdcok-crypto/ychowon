/**
 * 현황판(display) 상단/하단 콘텐츠 관리
 */
(function () {
  'use strict';

  var BRANCH_KEY = 'reserve_branch_id';
  var toastEl = document.getElementById('dc-toast');
  var state = {
    top: { items: [] },
    bottom: { items: [] }
  };
  var sections = [
    { key: 'top', label: '상단 콘텐츠', payloadItemsKey: 'top_items', payloadIntervalKey: 'top_default_interval_sec' },
    { key: 'bottom', label: '하단 콘텐츠', payloadItemsKey: 'items', payloadIntervalKey: 'default_interval_sec' }
  ];

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

  function uploadApiUrl() {
    return apiUrlWithBranch('/api/display/upload');
  }

  function el(section, suffix) {
    return document.getElementById('dc-' + section.key + '-' + suffix);
  }

  function cloneItems(items) {
    return (items || []).map(function (it) {
      return {
        id: it.id || '',
        type: it.type === 'video' ? 'video' : 'image',
        url: it.url || '',
        name: it.name != null ? String(it.name) : '',
        duration_sec: it.type === 'video' ? null : (it.duration_sec != null ? it.duration_sec : null)
      };
    });
  }

  function snapshotState() {
    return {
      topItems: cloneItems(state.top.items),
      bottomItems: cloneItems(state.bottom.items),
      topDefault: getDefaultSec(sections[0]),
      bottomDefault: getDefaultSec(sections[1])
    };
  }

  function restoreState(snapshot) {
    state.top.items = cloneItems(snapshot.topItems);
    state.bottom.items = cloneItems(snapshot.bottomItems);
    el(sections[0], 'default-interval').value = String(snapshot.topDefault);
    el(sections[1], 'default-interval').value = String(snapshot.bottomDefault);
    renderAll();
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

  function looksLikeUrl(v) {
    var s = String(v || '').trim();
    return s.indexOf('http://') === 0 || s.indexOf('https://') === 0 || s.indexOf('/') === 0;
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
      if (last) return last.length > 96 ? last.slice(0, 93) + '…' : last;
    } catch (e) {}
    return u.length > 96 ? u.slice(0, 93) + '…' : u;
  }

  function contentDisplayName(it) {
    var n = it.name != null ? String(it.name).trim() : '';
    if (n) return n.length > 120 ? n.slice(0, 117) + '…' : n;
    return urlToLabel(it.url);
  }

  function getDefaultSec(section) {
    var input = el(section, 'default-interval');
    var di = input ? parseInt(input.value, 10) : 8;
    if (isNaN(di)) di = 8;
    return Math.max(3, Math.min(600, di));
  }

  function formatDisplayTime(section, it) {
    if (it.type === 'video') return '재생 끝까지';
    var d = it.duration_sec;
    if (d != null && d !== '' && !isNaN(parseInt(d, 10))) {
      return parseInt(d, 10) + '초';
    }
    return '기본(' + getDefaultSec(section) + '초)';
  }

  function uploadDisplayFile(file) {
    var fd = new FormData();
    fd.append('file', file);
    return fetch(uploadApiUrl(), { method: 'POST', credentials: 'same-origin', body: fd }).then(function (r) {
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

  function payloadFromState() {
    return {
      top_items: state.top.items.map(function (it) {
        return {
          type: it.type,
          url: it.url,
          name: it.name != null ? String(it.name) : '',
          duration_sec: it.duration_sec === undefined ? null : it.duration_sec
        };
      }),
      top_default_interval_sec: getDefaultSec(sections[0]),
      items: state.bottom.items.map(function (it) {
        return {
          type: it.type,
          url: it.url,
          name: it.name != null ? String(it.name) : '',
          duration_sec: it.duration_sec === undefined ? null : it.duration_sec
        };
      }),
      default_interval_sec: getDefaultSec(sections[1])
    };
  }

  function save(snapshot, successMsg) {
    return fetch(contentApiUrl(), {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payloadFromState())
    })
      .then(function (r) {
        if (!r.ok) {
          return r.json().then(function (j) {
            throw new Error((j && j.detail) ? (typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail)) : '저장 실패');
          });
        }
        return r.json();
      })
      .then(function () {
        showToast(successMsg || '저장했습니다.');
        return load();
      })
      .catch(function (err) {
        if (snapshot) restoreState(snapshot);
        showToast(err.message || '저장에 실패했습니다.');
      });
  }

  function updateAddPanelDurationVisibility(section) {
    var typeEl = el(section, 'add-type');
    var lab = document.querySelector('.dc-add-duration-label[data-section="' + section.key + '"]');
    var inp = el(section, 'add-duration');
    if (!typeEl || !inp) return;
    var hide = typeEl.value === 'video';
    if (lab) lab.hidden = hide;
    inp.hidden = hide;
  }

  function resetAddPanel(section) {
    var nameEl = el(section, 'add-name');
    var realEl = el(section, 'add-url-real');
    var urlEl = el(section, 'add-url');
    var typeEl = el(section, 'add-type');
    var durEl = el(section, 'add-duration');
    var fileEl = el(section, 'add-file');
    if (nameEl) nameEl.value = '';
    if (realEl) realEl.value = '';
    if (urlEl) urlEl.value = '';
    if (typeEl) typeEl.value = 'image';
    if (durEl) durEl.value = '';
    if (fileEl) fileEl.value = '';
    updateAddPanelDurationVisibility(section);
  }

  function readAddPanel(section) {
    var typeEl = el(section, 'add-type');
    var urlEl = el(section, 'add-url');
    var realEl = el(section, 'add-url-real');
    var nameEl = el(section, 'add-name');
    var durEl = el(section, 'add-duration');
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

  function renderSummary(section) {
    var tbody = el(section, 'summary-body');
    var emptyEl = el(section, 'summary-empty');
    var wrap = el(section, 'summary-wrap');
    var tableWrap = wrap ? wrap.querySelector('.dc-summary-table-wrap') : null;
    var items = state[section.key].items;
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
    items.forEach(function (it, i) {
      var tr = document.createElement('tr');
      var td1 = document.createElement('td');
      td1.className = 'col-order';
      td1.textContent = String(i + 1);
      var td2 = document.createElement('td');
      td2.className = 'col-type';
      td2.textContent = it.type === 'video' ? '동영상' : '이미지';
      var td3 = document.createElement('td');
      td3.textContent = formatDisplayTime(section, it);
      var td4 = document.createElement('td');
      td4.className = 'col-name';
      td4.textContent = contentDisplayName(it);
      var td5 = document.createElement('td');
      td5.className = 'col-move';
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
      btnDn.disabled = i >= items.length - 1;
      btnDn.textContent = '↓';
      td5.appendChild(btnUp);
      td5.appendChild(btnDn);
      var td6 = document.createElement('td');
      td6.className = 'col-del';
      var delBtn = document.createElement('button');
      delBtn.type = 'button';
      delBtn.className = 'btn btn-del dc-summary-del';
      delBtn.setAttribute('data-index', String(i));
      delBtn.setAttribute('title', '이 항목 삭제');
      delBtn.setAttribute('aria-label', '삭제');
      delBtn.textContent = '삭제';
      td6.appendChild(delBtn);
      tr.appendChild(td1);
      tr.appendChild(td2);
      tr.appendChild(td3);
      tr.appendChild(td4);
      tr.appendChild(td5);
      tr.appendChild(td6);
      tbody.appendChild(tr);
    });
  }

  function renderAll() {
    sections.forEach(renderSummary);
  }

  function load() {
    return fetch(contentApiUrl(), { credentials: 'same-origin' })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        state.top.items = cloneItems(Array.isArray(data.top_items) ? data.top_items : []);
        state.bottom.items = cloneItems(Array.isArray(data.items) ? data.items : []);
        el(sections[0], 'default-interval').value = String(Math.max(3, Math.min(600, parseInt(data.top_default_interval_sec, 10) || 8)));
        el(sections[1], 'default-interval').value = String(Math.max(3, Math.min(600, parseInt(data.default_interval_sec, 10) || 8)));
        resetAddPanel(sections[0]);
        resetAddPanel(sections[1]);
        renderAll();
      })
      .catch(function () {
        state.top.items = [];
        state.bottom.items = [];
        renderAll();
        showToast('목록을 불러오지 못했습니다.');
      });
  }

  function commitAddPanelFromUrl(section) {
    var it = readAddPanel(section);
    if (!String(it.url || '').trim()) {
      showToast('URL을 입력하거나 파일을 선택하세요.');
      return;
    }
    var snapshot = snapshotState();
    state[section.key].items.push(it);
    resetAddPanel(section);
    renderAll();
    save(snapshot, section.label + '를 저장했습니다.');
  }

  function bindSection(section) {
    var typeEl = el(section, 'add-type');
    if (typeEl) {
      typeEl.addEventListener('change', function () {
        updateAddPanelDurationVisibility(section);
      });
    }

    var urlEl = el(section, 'add-url');
    var realEl = el(section, 'add-url-real');
    var nameEl = el(section, 'add-name');
    if (urlEl) {
      urlEl.addEventListener('keydown', function (e) {
        if (e.key === 'Enter') {
          e.preventDefault();
          commitAddPanelFromUrl(section);
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

    var fileEl = el(section, 'add-file');
    if (fileEl) {
      fileEl.addEventListener('change', function () {
        var f = fileEl.files && fileEl.files[0];
        fileEl.value = '';
        if (!f) return;
        showToast(section.label + ' 업로드 중…');
        uploadDisplayFile(f)
          .then(function (data) {
            var u = data && data.url != null ? String(data.url).trim() : '';
            if (!u) {
              showToast('업로드 응답에 URL이 없습니다. 서버 로그에서 R2 오류를 확인하세요.');
              return;
            }
            var typeSel = el(section, 'add-type');
            if (typeSel) typeSel.value = guessTypeFromFile(f);
            updateAddPanelDurationVisibility(section);
            var picked = displayNameFromUpload(data, f, u);
            var durEl = el(section, 'add-duration');
            var durRaw = durEl && durEl.value ? durEl.value.trim() : '';
            var dur = durRaw === '' ? null : parseInt(durRaw, 10);
            if (dur !== null && (isNaN(dur) || dur < 3 || dur > 600)) dur = null;
            var snapshot = snapshotState();
            state[section.key].items.push({
              id: '',
              type: typeSel && typeSel.value === 'video' ? 'video' : 'image',
              url: u,
              name: picked || '',
              duration_sec: typeSel && typeSel.value === 'video' ? null : dur
            });
            resetAddPanel(section);
            renderAll();
            return save(snapshot, section.label + '를 저장했습니다.');
          })
          .catch(function (err) {
            showToast(err.message || '업로드에 실패했습니다.');
          });
      });
    }

    var summaryWrap = el(section, 'summary-wrap');
    if (summaryWrap) {
      summaryWrap.addEventListener('click', function (e) {
        var snapshot;
        var del = e.target.closest('.dc-summary-del');
        if (del) {
          e.preventDefault();
          var ix = parseInt(del.getAttribute('data-index'), 10);
          if (isNaN(ix)) return;
          snapshot = snapshotState();
          state[section.key].items.splice(ix, 1);
          renderAll();
          save(snapshot, section.label + '를 저장했습니다.');
          return;
        }
        var up = e.target.closest('.dc-summary-move-up');
        if (up && !up.disabled) {
          e.preventDefault();
          var iu = parseInt(up.getAttribute('data-index'), 10);
          if (isNaN(iu) || iu <= 0) return;
          snapshot = snapshotState();
          var temp = state[section.key].items[iu - 1];
          state[section.key].items[iu - 1] = state[section.key].items[iu];
          state[section.key].items[iu] = temp;
          renderAll();
          save(snapshot, section.label + ' 순서를 저장했습니다.');
          return;
        }
        var dn = e.target.closest('.dc-summary-move-down');
        if (dn && !dn.disabled) {
          e.preventDefault();
          var id = parseInt(dn.getAttribute('data-index'), 10);
          if (isNaN(id) || id >= state[section.key].items.length - 1) return;
          snapshot = snapshotState();
          var temp2 = state[section.key].items[id + 1];
          state[section.key].items[id + 1] = state[section.key].items[id];
          state[section.key].items[id] = temp2;
          renderAll();
          save(snapshot, section.label + ' 순서를 저장했습니다.');
        }
      });
    }

    var clearBtn = el(section, 'summary-clear');
    if (clearBtn) {
      clearBtn.addEventListener('click', function () {
        if (!state[section.key].items.length) return;
        if (!confirm(section.label + '를 모두 삭제할까요?')) return;
        var snapshot = snapshotState();
        state[section.key].items = [];
        renderAll();
        save(snapshot, section.label + '를 저장했습니다.');
      });
    }

    var defaultEl = el(section, 'default-interval');
    if (defaultEl) {
      defaultEl.addEventListener('focus', function () {
        defaultEl.dataset.prev = defaultEl.value;
      });
      defaultEl.addEventListener('change', function () {
        var snapshot = snapshotState();
        var prev = parseInt(defaultEl.dataset.prev, 10);
        if (!isNaN(prev)) {
          if (section.key === 'top') {
            snapshot.topDefault = Math.max(3, Math.min(600, prev));
          } else {
            snapshot.bottomDefault = Math.max(3, Math.min(600, prev));
          }
        }
        defaultEl.value = String(getDefaultSec(section));
        save(snapshot, section.label + ' 기본 시간을 저장했습니다.');
      });
    }

    updateAddPanelDurationVisibility(section);
  }

  sections.forEach(bindSection);
  load();
})();
