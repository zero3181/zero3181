// ⚠️ 실제 오픈 전, 아래 URL을 각 이벤트의 실제 딥링크/랜딩 URL로 교체하세요.
// (앱스토어/원스토어 다운로드 링크, 슈퍼SOL 이벤트 페이지 딥링크 등)
const LINKS = {
  // 슈퍼SOL 가입 딥링크 (adbrix)
  appInstall: 'https://SNRyhPIaqEWCErBZXy2iWA.adtouch.adbrix.io/api/v1/click/y9XvBoqAIEqatgehUbiJhg?deeplink_custom_path=supersol%3A%2F%2FCO0605H0011F01%3Fgroup%3DS001%26hwno%3D22102213',
  // 슈퍼SOL 신규가입 이벤트 페이지 (네이버페이 1만P)
  superSolSignup: 'https://nssol.shinhan.com/link.html?pr_id=VU0001R0001F01&pid=GO0601H0001F04&evtType=01&evtMstNo=2608140704&jehyuCode=PLF1',
  // 은행·증권 신규계좌 개설 이벤트 (테슬라 추첨 + SOL LINK 보유고객 전체 확정 포인트 3천원~100만원)
  solLinkBonus: 'https://nssol.shinhan.com/link.html?pr_id=VU0001R0001F01&pid=GO0601H0001F04&jehyuCode=PLF1&evtMstNo=2606150701&evtType=01',
  // TODO: 랜덤 포인트 뽑기(마이신한포인트 최대 10만P) 이벤트 링크 - 아직 미수령, 확인 후 채워주세요
  randomPoint: '#',
  // 올리브영 SOL통장 X SOL LINK 연결 이벤트
  oliveYoung: 'https://nssol.shinhan.com/link.html?pr_id=SP1301H0012F01&evntSeq=10910',
  // 신한 SOL LINK 계좌개설(가입) 링크
  soLinkSignup: 'https://nssol.shinhan.com/link.html?pr_id=PR1002S0011F01&prdCode=110007801&hwno=22102213',
  // 은행·증권 신규계좌 개설 이벤트 (테슬라 추첨 + 투자쿠폰) - solLinkBonus와 동일 이벤트 페이지
  teslaEvent: 'https://nssol.shinhan.com/link.html?pr_id=VU0001R0001F01&pid=GO0601H0001F04&jehyuCode=PLF1&evtMstNo=2606150701&evtType=01',
};

document.querySelectorAll('[data-link]').forEach((el) => {
  const key = el.getAttribute('data-link');
  const url = LINKS[key];
  if (!url || url === '#') {
    el.classList.add('link-missing');
  }
  el.setAttribute('href', url || '#');
});

document.documentElement.style.scrollBehavior = 'smooth';
