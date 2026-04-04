/**
 * 관리자 · 계정 관리 탭 (GET/POST/PATCH/DELETE /api/auth/accounts)
 */
(function () {
  'use strict';

  var SYSTEM_IDS = { admin: 1, display: 1, tel: 1 };
  var ROLES = ['admin', 'display', 'tel'];

  var tbody = document.getElementById('accounts-table-body');
  var btnAdd = document.getElementById('accounts-btn-add');
  var btnEdit = document.getElementById('accounts-btn-edit');
  var btnDelete = document.getElementById('accounts-btn-delete');
  var btnRevoke = document.getElementById('accounts-btn-revoke');
  var toastEl = document.getElementById('accounts-toast');
  var modal = document.getElementById('accounts-modal');
  var modalBackdrop = document.getElementById('accounts-modal-backdrop');
  var modalTitle = document.getElementById('accounts-modal-title');
  var modalFields = document.getElementById('accounts-modal-fields');
  var modalCancel = document.getElementById('accounts-modal-cancel');
  var modalSave = document.getElementById('accounts-modal-save');

  var rowsCache = [];
  var selectedId = null;
  var modalMode = 'add';

  if (!tbody || !modal) return;

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function parseDetail(j) {
    var d = j && j.detail;
    if (typeof d === 'string') return d;
    if (Array.isArray(d) && d[0] && d[0].msg) return d[0].msg;
    return '요청을 처리하지 못했습니다.';
  }

  function showToast(msg) {
    if (toastEl) toastEl.textContent = msg || '';
  }

  function apiJson(url, options) {
    return fetch(url, options).then(function (r) {
      if (!r.ok) {
        return r.json().then(function (j) {
          throw new Error(parseDetail(j));
        });
      }
      var ct = r.headers.get('content-type') || '';
      if (ct.indexOf('application/json') !== -1) return r.json();
      return {};
    });
  }

  function load() {
    return apiJson('/api/auth/accounts', { credentials: 'same-origin' })
      .then(function (data) {
        rowsCache = data.accounts || [];
        selectedId = null;
        render();
      })
      .catch(function (e) {
        showToast(e.message || String(e));
      });
  }

  function render() {
    tbody.innerHTML = rowsCache
      .map(function (r) {
        var authLabel = r.authenticated ? '예' : '아니오';
        var sel = r.id === selectedId ? ' accounts-row-selected' : '';
        return (
          '<tr class="accounts-row' + sel + '" data-id="' + escapeHtml(r.id) + '" tabindex="0">' +
          '<td>' + r.no + '</td>' +
          '<td>' + escapeHtml(r.name || r.id) + '</td>' +
          '<td>' + authLabel + '</td>' +
          '</tr>'
        );
      })
      .join('');
  }

  function selectRow(id) {
    selectedId = id;
    render();
  }

  tbody.addEventListener('click', function (ev) {
    var tr = ev.target.closest('tr.accounts-row');
    if (!tr) return;
    selectRow(tr.getAttribute('data-id'));
  });

  function closeModal() {
    modal.classList.add('hidden');
    modal.setAttribute('aria-hidden', 'true');
  }

  function openModalAdd() {
    modalMode = 'add';
    modalTitle.textContent = '계정 추가';
    modalFields.innerHTML =
      '<div class="accounts-field">' +
      '<label for="acc-in-id">계정 ID</label>' +
      '<input type="text" id="acc-in-id" autocomplete="off" spellcheck="false" placeholder="영문 시작, 영숫자·_-">' +
      '</div>' +
      '<div class="accounts-field">' +
      '<label for="acc-in-name">이름</label>' +
      '<input type="text" id="acc-in-name" autocomplete="off">' +
      '</div>' +
      '<div class="accounts-field">' +
      '<label for="acc-in-role">역할</label>' +
      '<select id="acc-in-role">' +
      ROLES.map(function (role) {
        return '<option value="' + role + '">' + role + '</option>';
      }).join('') +
      '</select>' +
      '</div>' +
      '<div class="accounts-field">' +
      '<label for="acc-in-pw">비밀번호</label>' +
      '<input type="password" id="acc-in-pw" autocomplete="new-password">' +
      '</div>';
    modal.classList.remove('hidden');
    modal.setAttribute('aria-hidden', 'false');
  }

  function openModalEdit() {
    if (!selectedId) {
      showToast('수정할 계정을 표에서 선택하세요.');
      return;
    }
    var row = rowsCache.filter(function (r) {
      return r.id === selectedId;
    })[0];
    if (!row) return;
    modalMode = 'edit';
    modalTitle.textContent = '계정 수정';
    modalFields.innerHTML =
      '<p class="accounts-edit-id">ID: <strong>' + escapeHtml(row.id) + '</strong></p>' +
      '<div class="accounts-field">' +
      '<label for="acc-in-name">이름</label>' +
      '<input type="text" id="acc-in-name" value="' + escapeHtml(row.name || '') + '" autocomplete="off">' +
      '</div>' +
      '<div class="accounts-field">' +
      '<label for="acc-in-pw">새 비밀번호 (비워두면 유지)</label>' +
      '<input type="password" id="acc-in-pw" autocomplete="new-password" placeholder="변경 시에만 입력">' +
      '</div>';
    modal.classList.remove('hidden');
    modal.setAttribute('aria-hidden', 'false');
  }

  function saveModal() {
    if (modalMode === 'add') {
      var idEl = document.getElementById('acc-in-id');
      var nameEl = document.getElementById('acc-in-name');
      var roleEl = document.getElementById('acc-in-role');
      var pwEl = document.getElementById('acc-in-pw');
      var id = idEl ? idEl.value.trim() : '';
      var name = nameEl ? nameEl.value.trim() : '';
      var role = roleEl ? roleEl.value : 'tel';
      var pw = pwEl ? pwEl.value : '';
      if (!id) {
        showToast('계정 ID를 입력하세요.');
        return;
      }
      if (pw.length < 4) {
        showToast('비밀번호는 4자 이상이어야 합니다.');
        return;
      }
      showToast('');
      apiJson('/api/auth/accounts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify({ id: id, name: name || id, role: role, password: pw }),
      })
        .then(function () {
          closeModal();
          showToast('계정을 추가했습니다.');
          return load();
        })
        .catch(function (e) {
          showToast(e.message || String(e));
        });
      return;
    }
    if (modalMode === 'edit') {
      var nameIn = document.getElementById('acc-in-name');
      var pwIn = document.getElementById('acc-in-pw');
      var newName = nameIn ? nameIn.value.trim() : '';
      var newPw = pwIn ? pwIn.value : '';
      var body = { name: newName };
      if (newPw.length > 0) {
        if (newPw.length < 4) {
          showToast('비밀번호는 4자 이상이어야 합니다.');
          return;
        }
        body.password = newPw;
      }
      showToast('');
      apiJson('/api/auth/accounts/' + encodeURIComponent(selectedId), {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify(body),
      })
        .then(function () {
          closeModal();
          showToast('계정을 수정했습니다.');
          return load();
        })
        .catch(function (e) {
          showToast(e.message || String(e));
        });
    }
  }

  function doDelete() {
    if (!selectedId) {
      showToast('삭제할 계정을 선택하세요.');
      return;
    }
    if (SYSTEM_IDS[selectedId]) {
      showToast('기본 계정(admin, display, tel)은 삭제할 수 없습니다.');
      return;
    }
    if (!window.confirm('선택한 계정을 삭제할까요? 이 작업은 되돌릴 수 없습니다.')) return;
    showToast('');
    apiJson('/api/auth/accounts/' + encodeURIComponent(selectedId), {
      method: 'DELETE',
      credentials: 'same-origin',
    })
      .then(function () {
        showToast('계정을 삭제했습니다.');
        return load();
      })
      .catch(function (e) {
        showToast(e.message || String(e));
      });
  }

  function doRevoke() {
    if (!selectedId) {
      showToast('인증을 취소할 계정을 선택하세요.');
      return;
    }
    if (
      !window.confirm(
        '선택한 계정의 비밀번호(인증)를 제거합니다. 해당 사용자는 로그인 후 비밀번호를 다시 설정해야 합니다. 계속할까요?'
      )
    ) {
      return;
    }
    showToast('');
    apiJson('/api/auth/accounts/' + encodeURIComponent(selectedId) + '/revoke', {
      method: 'POST',
      credentials: 'same-origin',
    })
      .then(function () {
        showToast('인증을 취소했습니다.');
        return load();
      })
      .catch(function (e) {
        showToast(e.message || String(e));
      });
  }

  if (btnAdd) btnAdd.addEventListener('click', openModalAdd);
  if (btnEdit) btnEdit.addEventListener('click', openModalEdit);
  if (btnDelete) btnDelete.addEventListener('click', doDelete);
  if (btnRevoke) btnRevoke.addEventListener('click', doRevoke);
  if (modalCancel) modalCancel.addEventListener('click', closeModal);
  if (modalBackdrop) modalBackdrop.addEventListener('click', closeModal);
  if (modalSave) modalSave.addEventListener('click', saveModal);

  load();
  window.__accountsReload = load;
})();
