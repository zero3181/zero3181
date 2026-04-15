import { Article, BiasType } from '../types';

const CORS_PROXY = 'https://api.allorigins.win/raw?url=';

const DOMAIN_BIAS: Record<string, { bias: BiasType; level: 'moderate' | 'extreme'; name: string }> = {
  'hani.co.kr':      { bias: 'LEFT',  level: 'moderate', name: '한겨레' },
  'khan.co.kr':      { bias: 'LEFT',  level: 'moderate', name: '경향신문' },
  'ohmynews.com':    { bias: 'LEFT',  level: 'extreme',  name: '오마이뉴스' },
  'jtbc.co.kr':      { bias: 'LEFT',  level: 'moderate', name: 'JTBC' },
  'imbc.com':        { bias: 'LEFT',  level: 'moderate', name: 'MBC' },
  'ytn.co.kr':       { bias: 'LEFT',  level: 'moderate', name: 'YTN' },
  'newstapa.org':    { bias: 'LEFT',  level: 'extreme',  name: '뉴스타파' },
  'seoul.co.kr':     { bias: 'LEFT',  level: 'moderate', name: '서울신문' },
  'chosun.com':      { bias: 'RIGHT', level: 'moderate', name: '조선일보' },
  'joongang.co.kr':  { bias: 'RIGHT', level: 'moderate', name: '중앙일보' },
  'donga.com':       { bias: 'RIGHT', level: 'moderate', name: '동아일보' },
  'tvchosun.com':    { bias: 'RIGHT', level: 'extreme',  name: 'TV조선' },
  'ichannela.com':   { bias: 'RIGHT', level: 'extreme',  name: '채널A' },
  'munhwa.com':      { bias: 'RIGHT', level: 'moderate', name: '문화일보' },
  'segye.com':       { bias: 'RIGHT', level: 'moderate', name: '세계일보' },
  'kmib.co.kr':      { bias: 'RIGHT', level: 'moderate', name: '국민일보' },
};

const LEFT_DOMAINS  = Object.entries(DOMAIN_BIAS).filter(([, v]) => v.bias === 'LEFT').map(([d]) => d);
const RIGHT_DOMAINS = Object.entries(DOMAIN_BIAS).filter(([, v]) => v.bias === 'RIGHT').map(([d]) => d);

function gnewsUrl(keyword: string, domains: string[]): string {
  const siteClause = domains.map((d) => `site:${d}`).join(' OR ');
  const q = encodeURIComponent(`${keyword} (${siteClause})`);
  const rss = `https://news.google.com/rss/search?q=${q}&hl=ko&gl=KR&ceid=KR:ko`;
  return `${CORS_PROXY}${encodeURIComponent(rss)}`;
}

function domainOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return '';
  }
}

function mediaInfo(sourceText: string, sourceUrl: string) {
  const domain = domainOf(sourceUrl);
  if (DOMAIN_BIAS[domain]) return DOMAIN_BIAS[domain];
  // fallback: search by partial domain in name
  for (const [d, info] of Object.entries(DOMAIN_BIAS)) {
    if (sourceText.includes(info.name) || domain.includes(d.split('.')[0])) return info;
  }
  return null;
}

function parseRSS(xml: string, defaultBias: BiasType, keyword: string): Article[] {
  const doc = new DOMParser().parseFromString(xml, 'application/xml');
  const items = Array.from(doc.querySelectorAll('item'));

  return items
    .map((item, i) => {
      const rawTitle  = item.querySelector('title')?.textContent ?? '';
      const link      = item.querySelector('link')?.textContent?.trim() ?? '#';
      const pubDate   = item.querySelector('pubDate')?.textContent ?? '';
      const srcEl     = item.querySelector('source');
      const srcText   = srcEl?.textContent ?? '';
      const srcUrl    = srcEl?.getAttribute('url') ?? '';

      // Google News appends " - Media Name" to titles
      const title = rawTitle.replace(/\s*-\s*[^-]+$/, '').trim() || rawTitle;

      const info = mediaInfo(srcText, srcUrl);

      return {
        id: `gnews-${defaultBias}-${i}-${Date.now()}`,
        mediaId: 0,
        mediaName: info?.name ?? srcText,
        title,
        url: link,
        publishedAt: pubDate ? new Date(pubDate).toISOString() : new Date().toISOString(),
        topic: keyword,
        bias: info?.bias ?? defaultBias,
        biasLevel: info?.level ?? ('moderate' as const),
      } satisfies Article;
    })
    .filter((a) => a.title.length > 0);
}

export async function fetchGoogleNews(
  keyword: string,
  bias: BiasType,
): Promise<Article[]> {
  const domains = bias === 'LEFT' ? LEFT_DOMAINS : RIGHT_DOMAINS;
  const url = gnewsUrl(keyword, domains);

  const res = await fetch(url);
  if (!res.ok) throw new Error(`네트워크 오류 (${res.status})`);

  const xml = await res.text();
  if (!xml.includes('<rss') && !xml.includes('<feed')) {
    throw new Error('RSS 파싱 실패 — Google 응답 형식 오류');
  }

  return parseRSS(xml, bias, keyword);
}
