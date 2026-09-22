const LINKS = {
  // 슈퍼SOL 설치 딥링크
  appInstall: 'https://SNRyhPIaqEWCErBZXy2iWA.adtouch.adbrix.io/api/v1/click/y9XvBoqAIEqatgehUbiJhg?deeplink_custom_path=supersol%3A%2F%2FCO0605H0011F01%3Fgroup%3DS001%26hwno%3D22102213',
  // 슈퍼SOL 신규가입 이벤트 페이지 (네이버페이 1만P)
  superSolSignup: 'https://nssol.shinhan.com/link.html?pr_id=VU0001R0001F01&pid=GO0601H0001F04&evtType=01&evtMstNo=2608140704&jehyuCode=PLF1',
  // 올리브영 SOL통장 X SOL LINK 연결 이벤트
  oliveYoung: 'https://nssol.shinhan.com/link.html?pr_id=SP1301H0012F01&evntSeq=10910',
  // SOL LINK 보유고객 전체 확정 포인트(3천원~100만원)
  solLinkBonus: 'https://nssol.shinhan.com/link.html?pr_id=VU0001R0001F01&pid=GO0601H0001F04&jehyuCode=PLF1&evtMstNo=2606150701&evtType=01',
  // 테슬라 추첨 + 투자쿠폰 이벤트
  teslaEvent: 'https://nssol.shinhan.com/link.html?pr_id=VU0001R0001F01&pid=GO0601H0001F04&jehyuCode=PLF1&evtMstNo=2606150701&evtType=01',
};

document.querySelectorAll('[data-link]').forEach((el) => {
  const key = el.getAttribute('data-link');
  const url = LINKS[key];
  if (!url) el.classList.add('link-missing');
  el.setAttribute('href', url || '#');
});

// D-day countdown to the event end date (2026.09.30 KST)
const ddayEl = document.getElementById('dday');
if (ddayEl) {
  const target = new Date('2026-09-30T23:59:59+09:00');
  const now = new Date();
  const diffDays = Math.ceil((target - now) / 86400000);
  ddayEl.textContent = diffDays > 0 ? `D-${diffDays}` : '이벤트 종료';
}
