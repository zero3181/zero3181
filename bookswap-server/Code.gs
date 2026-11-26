/**
 * 블라인드 북 스왑 서버 (Google Apps Script)
 *
 * 구글 시트의 [확장 프로그램 > Apps Script]에 이 파일 내용을 통째로 붙여넣고
 * [배포 > 새 배포 > 웹 앱]으로 배포합니다. (실행: 나 / 액세스 권한: 모든 사용자)
 *
 * - 추천 내용은 이 시트에만 저장되고, 참여자 화면에는 완료 여부만 전달됩니다.
 * - 모든 사람이 추천을 마치는 순간 서버가 자동으로 배정합니다. 자기 책은 배정되지 않습니다.
 * - 책 검색: 스크립트 속성에 KAKAO_REST_KEY가 있으면 카카오 책 검색, 없으면 Google Books를 씁니다.
 */

// 참여자 명단. 추천이 시작된 뒤에는 순서를 바꾸지 마세요 (자리 번호가 순서에 묶여 있습니다).
const ROSTER = [
  '강성진', '김가영', '김나정', '김윤수', '김채린', '박현영', '이루리',
  '장효민', '전하민', '정재하', '정종우', '진영규', '최보배', '하준성'
];

const SPREADSHEET_TITLE = '블라인드 북 스왑';
const PICKS = '추천';
const DRAW = '배정';
const TEST_PICKS = '테스트 추천';
const TEST_DRAW = '테스트 배정';
const PICK_HEADER = ['자리', '이름', '제목', '저자', '추천 이유', '수정 토큰', '저장 시각'];
const DRAW_HEADER = ['자리', '받는 사람', '추천한 사람', '제목', '저자', '추천 이유', '배정 시각'];

// '테스트 배정 미리보기'에 쓰는 더미 추천 (명단 순서대로 한 권씩)
const DUMMY_BOOKS = [
  ['채식주의자', '한강'], ['아몬드', '손원평'], ['불편한 편의점', '김호연'], ['달러구트 꿈 백화점', '이미예'],
  ['어린 왕자', '앙투안 드 생텍쥐페리'], ['사피엔스', '유발 하라리'], ['미움받을 용기', '기시미 이치로'],
  ['데미안', '헤르만 헤세'], ['1984', '조지 오웰'], ['82년생 김지영', '조남주'], ['파친코', '이민진'],
  ['원씽', '게리 켈러'], ['소년이 온다', '한강'], ['죽고 싶지만 떡볶이는 먹고 싶어', '백세희']
];

/* ---------------- web app ---------------- */

function doGet(e) {
  return route_((e && e.parameter) || {});
}

function doPost(e) {
  let p = {};
  try { p = JSON.parse(e.postData.contents); } catch (err) { p = {}; }
  return route_(p);
}

function route_(p) {
  let result;
  try {
    switch (p.action) {
      case 'status': result = status_(); break;
      case 'submit': result = submit_(p); break;
      case 'mine': result = mine_(p.slot, p.token); break;
      case 'assignment': result = assignment_(p.slot); break;
      case 'search': result = search_(p.q); break;
      default: result = { error: 'unknown_action' };
    }
  } catch (err) {
    result = { error: 'server_error', message: String((err && err.message) || err) };
  }
  return ContentService.createTextOutput(JSON.stringify(result)).setMimeType(ContentService.MimeType.JSON);
}

/* ---------------- helpers ---------------- */

function slotIds_() {
  return ROSTER.map(function (_, i) { return 'p' + ('0' + (i + 1)).slice(-2); });
}

function slotIndex_(slot) {
  const i = slotIds_().indexOf(String(slot));
  if (i < 0) throw new Error('잘못된 자리입니다.');
  return i;
}

function sheet_(name, header) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sh = ss.getSheetByName(name);
  if (!sh) {
    sh = ss.insertSheet(name);
    sh.appendRow(header);
    sh.setFrozenRows(1);
  } else {
    const cur = sh.getRange(1, 1, 1, header.length).getValues()[0];
    if (cur.join('|') !== header.join('|')) {
      sh.getRange(1, 1, 1, Math.max(header.length, sh.getLastColumn() || 1)).clearContent();
      sh.getRange(1, 1, 1, header.length).setValues([header]);
    }
  }
  return sh;
}

function readPicks_() {
  const sh = sheet_(PICKS, PICK_HEADER);
  const values = sh.getDataRange().getValues();
  const bySlot = {};
  for (let r = 1; r < values.length; r++) {
    const v = values[r];
    if (!v[0]) continue;
    bySlot[v[0]] = { row: r + 1, slot: v[0], title: String(v[2]), author: String(v[3]), note: String(v[4]), token: String(v[5]) };
  }
  return { sh: sh, bySlot: bySlot };
}

function readDraw_() {
  const sh = sheet_(DRAW, DRAW_HEADER);
  const values = sh.getDataRange().getValues();
  const bySlot = {};
  for (let r = 1; r < values.length; r++) {
    const v = values[r];
    if (!v[0]) continue;
    bySlot[v[0]] = { title: String(v[3]), author: String(v[4]), note: String(v[5]) };
  }
  return { sh: sh, bySlot: bySlot, drawn: Object.keys(bySlot).length > 0 };
}

function clip_(s, n) {
  return String(s == null ? '' : s).replace(/[\u0000-\u001f]/g, ' ').trim().slice(0, n);
}

// 시트 수식 주입 방지: = + - @ 로 시작하는 값은 앞에 작은따옴표를 붙입니다.
function safeCell_(s) {
  return /^[=+\-@]/.test(s) ? "'" + s : s;
}

/* ---------------- actions ---------------- */

function status_() {
  const picks = readPicks_().bySlot;
  const draw = readDraw_();
  return {
    names: ROSTER,
    done: slotIds_().map(function (id) { return !!picks[id]; }),
    drawn: draw.drawn
  };
}

function submit_(p) {
  const slot = String(p.slot || '');
  const idx = slotIndex_(slot);
  const title = clip_(p.title, 120);
  const author = clip_(p.author, 80);
  const note = clip_(p.note, 300);
  if (!title) return { error: 'title_required' };

  const lock = LockService.getScriptLock();
  lock.waitLock(20000);
  try {
    if (readDraw_().drawn) return { error: 'already_drawn' };
    const picks = readPicks_();
    const existing = picks.bySlot[slot];
    if (existing && existing.token !== String(p.token || '')) return { error: 'taken' };

    const token = existing ? existing.token : Utilities.getUuid();
    const row = [slot, ROSTER[idx], safeCell_(title), safeCell_(author), safeCell_(note), token, new Date()];
    if (existing) picks.sh.getRange(existing.row, 1, 1, row.length).setValues([row]);
    else picks.sh.appendRow(row);
    SpreadsheetApp.flush();

    let drawn = false;
    const after = readPicks_().bySlot;
    if (slotIds_().every(function (id) { return !!after[id]; })) {
      draw_(after, DRAW);
      drawn = true;
    }
    return { ok: true, token: token, drawn: drawn };
  } finally {
    lock.releaseLock();
  }
}

function mine_(slot, token) {
  const pick = readPicks_().bySlot[String(slot || '')];
  if (!pick || pick.token !== String(token || '')) return { error: 'not_found' };
  return { title: pick.title, author: pick.author, note: pick.note };
}

function assignment_(slot) {
  const draw = readDraw_();
  if (!draw.drawn) return { drawn: false };
  const a = draw.bySlot[String(slot || '')];
  if (!a) return { drawn: true, error: 'not_found' };
  return { drawn: true, title: a.title, author: a.author, note: a.note };
}

/* ---------------- draw ---------------- */

// 섞은 뒤 원형으로 돌려 받기: 각자 다음 사람이 추천한 책을 받으므로 자기 책은 절대 받지 않습니다.
function draw_(picks, sheetName) {
  const ids = slotIds_();
  const order = ids.slice();
  for (let i = order.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    const t = order[i]; order[i] = order[j]; order[j] = t;
  }
  const now = new Date();
  const rows = order.map(function (receiver, i) {
    const giverSlot = order[(i + 1) % order.length];
    const giver = picks[giverSlot];
    return [receiver, ROSTER[slotIndex_(receiver)], ROSTER[slotIndex_(giverSlot)], safeCell_(giver.title), safeCell_(giver.author), safeCell_(giver.note || ''), now];
  });
  rows.sort(function (a, b) { return a[0] < b[0] ? -1 : 1; });
  const sh = sheet_(sheetName, DRAW_HEADER);
  if (sh.getLastRow() > 1) sh.getRange(2, 1, sh.getLastRow() - 1, DRAW_HEADER.length).clearContent();
  sh.getRange(2, 1, rows.length, DRAW_HEADER.length).setValues(rows);
  SpreadsheetApp.flush();
}

/* ---------------- book search ---------------- */

function search_(q) {
  q = clip_(q, 80);
  if (q.length < 2) return { items: [] };
  const cache = CacheService.getScriptCache();
  const key = 'q:' + Utilities.base64EncodeWebSafe(q).slice(0, 200);
  const hit = cache.get(key);
  if (hit) return JSON.parse(hit);

  const kakaoKey = PropertiesService.getScriptProperties().getProperty('KAKAO_REST_KEY');
  let items = [];
  let source;
  if (kakaoKey) {
    source = 'kakao';
    const res = UrlFetchApp.fetch('https://dapi.kakao.com/v3/search/book?size=8&query=' + encodeURIComponent(q), {
      headers: { Authorization: 'KakaoAK ' + kakaoKey }, muteHttpExceptions: true
    });
    if (res.getResponseCode() === 200) {
      items = (JSON.parse(res.getContentText()).documents || []).map(function (d) {
        return { title: d.title || '', author: (d.authors || []).join(', '), publisher: d.publisher || '', thumbnail: d.thumbnail || '' };
      });
    }
  } else {
    source = 'google';
    const res = UrlFetchApp.fetch('https://www.googleapis.com/books/v1/volumes?maxResults=8&printType=books&q=' + encodeURIComponent(q), { muteHttpExceptions: true });
    if (res.getResponseCode() === 200) {
      items = (JSON.parse(res.getContentText()).items || []).map(function (it) {
        const v = it.volumeInfo || {};
        const th = (v.imageLinks && (v.imageLinks.smallThumbnail || v.imageLinks.thumbnail)) || '';
        return { title: v.title || '', author: (v.authors || []).join(', '), publisher: v.publisher || '', thumbnail: th.replace(/^http:/, 'https:') };
      });
    }
  }
  const out = { items: items, source: source };
  cache.put(key, JSON.stringify(out), 21600);
  return out;
}

/* ---------------- organizer menu (시트 상단 '북 스왑' 메뉴) ---------------- */

function onOpen() {
  try { ensureTitle_(); } catch (e) {}
  SpreadsheetApp.getUi().createMenu('북 스왑')
    .addItem('진행 현황 보기', 'menuStatus')
    .addItem('배정 다시 하기', 'menuRedraw')
    .addSeparator()
    .addItem('테스트 배정 미리보기 (더미 데이터)', 'menuTestDraw')
    .addItem('테스트 탭 지우기', 'menuClearTest')
    .addSeparator()
    .addItem('전체 초기화', 'menuReset')
    .addToUi();
}

function ensureTitle_() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  if (ss.getName() !== SPREADSHEET_TITLE) ss.rename(SPREADSHEET_TITLE);
}

// 실제 '추천'/'배정' 탭과 참여자 화면에는 영향을 주지 않습니다.
function menuTestDraw() {
  ensureTitle_();
  const ids = slotIds_();
  const picks = {};
  const pickRows = ids.map(function (id, i) {
    const b = DUMMY_BOOKS[i % DUMMY_BOOKS.length];
    const reason = i % 3 === 2 ? '' : '(테스트) ' + ROSTER[i] + '의 추천 이유';
    picks[id] = { title: b[0], author: b[1], note: reason };
    return [id, ROSTER[i], b[0], b[1], reason, '(테스트)', new Date()];
  });
  const sh = sheet_(TEST_PICKS, PICK_HEADER);
  if (sh.getLastRow() > 1) sh.getRange(2, 1, sh.getLastRow() - 1, PICK_HEADER.length).clearContent();
  sh.getRange(2, 1, pickRows.length, PICK_HEADER.length).setValues(pickRows);
  draw_(picks, TEST_DRAW);
  SpreadsheetApp.getActiveSpreadsheet().setActiveSheet(sheet_(TEST_DRAW, DRAW_HEADER));
  SpreadsheetApp.getUi().alert('더미 추천 14건으로 테스트 배정을 만들었습니다.\n\n' +
    "'테스트 배정' 탭에서 받는 사람과 추천한 사람이 늘 다른지 확인해 보세요. 다시 누를 때마다 새로 섞입니다.\n" +
    '실제 추천과 참여자 화면에는 영향이 없습니다.');
}

function menuClearTest() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  [TEST_PICKS, TEST_DRAW].forEach(function (n) { const sh = ss.getSheetByName(n); if (sh) ss.deleteSheet(sh); });
  SpreadsheetApp.getUi().alert('테스트 탭을 지웠습니다.');
}

function menuStatus() {
  ensureTitle_();
  const s = status_();
  const done = s.done.filter(Boolean).length;
  const waiting = s.names.filter(function (_, i) { return !s.done[i]; });
  SpreadsheetApp.getUi().alert(
    done + ' / ' + s.names.length + '명 완료' + (s.drawn ? ' (배정 완료)' : '') +
    (waiting.length ? '\n\n아직 안 한 사람: ' + waiting.join(', ') : '')
  );
}

function menuRedraw() {
  const ui = SpreadsheetApp.getUi();
  const picks = readPicks_().bySlot;
  if (!slotIds_().every(function (id) { return !!picks[id]; })) { ui.alert('아직 모든 사람이 추천하지 않았습니다.'); return; }
  if (ui.alert('기존 배정을 지우고 새로 배정할까요?', ui.ButtonSet.YES_NO) !== ui.Button.YES) return;
  draw_(picks, DRAW);
  ui.alert('새로 배정했습니다.');
}

function menuReset() {
  const ui = SpreadsheetApp.getUi();
  if (ui.alert('모든 추천과 배정을 지웁니다. 되돌릴 수 없습니다. 계속할까요?', ui.ButtonSet.YES_NO) !== ui.Button.YES) return;
  [sheet_(PICKS, PICK_HEADER), sheet_(DRAW, DRAW_HEADER)].forEach(function (sh) {
    if (sh.getLastRow() > 1) sh.getRange(2, 1, sh.getLastRow() - 1, sh.getLastColumn()).clearContent();
  });
  ui.alert('초기화했습니다.');
}
