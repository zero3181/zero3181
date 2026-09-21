// ⚠️ 실제 오픈 전, 아래 URL을 각 이벤트의 실제 딥링크/랜딩 URL로 교체하세요.
// (앱스토어/원스토어 다운로드 링크, 슈퍼SOL 이벤트 페이지 딥링크 등)
const LINKS = {
  appInstall: '#',       // 슈퍼SOL 앱 설치 (원링크 등)
  superSolSignup: '#',   // 슈퍼SOL 신규가입 이벤트 페이지 (네이버페이 1만P)
  solLinkBonus: '#',     // SOL LINK 보유 고객 대상 확정 포인트/쿠폰 (3천원~100만원)
  randomPoint: '#',      // 랜덤 포인트 뽑기 이벤트 페이지
  oliveYoung: '#',       // 올리브영 SOL통장 X SOL LINK 이벤트 페이지
  soLinkSignup: '#',     // 신한 SOL LINK 계좌개설
  teslaEvent: '#',       // SOL LINK 개설 이벤트 (테슬라 추첨 + 투자쿠폰)
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
