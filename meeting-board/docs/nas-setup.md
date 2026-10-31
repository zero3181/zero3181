# 시놀로지 NAS에 AI 토론방 설치하기

NAS에서 24시간 돌아가는 웹페이지를 만듭니다. 폰이나 노트북 브라우저에서 비밀번호를 넣고
주제를 입력한 뒤 **시작**을 누르면 Gemini와 Claude가 토론하고, 진행 상황이 실시간으로 보입니다.
지난 토론 기록도 그 페이지에 남습니다. 맥은 처음 설치할 때만 필요합니다.

## 0. 확인할 것

- **Container Manager 지원 여부:** DSM **패키지 센터**에서 `Container Manager`를 검색하세요.
  - 보이면 설치합니다. 설치하면 `docker` 공유 폴더가 생깁니다.
  - 안 보이면 DSM 버전을 확인하세요(**제어판 → 정보 센터**).
  - DSM 7.1 이하에서는 패키지 이름이 `Docker`이고 프로젝트 기능이 없습니다.
    `Docker` 패키지를 설치한 뒤 아래 **DSM 7.1 이하** 절차를 따르세요. DS218+ / DSM 7.1.1에서 이 절차로 동작을 확인했습니다.
- **Gemini API 키:** https://aistudio.google.com 에서 발급합니다.
- **Claude 구독 토큰:** 맥 터미널에서 아래 명령을 한 번 실행합니다. 브라우저 로그인 후 터미널에
  긴 토큰이 출력되면 복사해 둡니다. 이 토큰은 비밀번호처럼 다루세요.
  ```bash
  claude setup-token
  ```

## 1. 파일 받기 (맥에서)

1. 아래 주소를 브라우저로 열면 ZIP 파일이 받아집니다.
   https://github.com/zero3181/zero3181/archive/refs/heads/claude/friendly-dirac-ujg7v8.zip
2. 압축을 풀고 그 안의 `meeting-board` 폴더를 찾습니다.

## 2. 설정 파일 만들기 (맥에서)

터미널에서 `meeting-board` 폴더로 이동한 뒤 아래 명령을 실행합니다
(`cd ` 뒤에 Finder에서 폴더를 끌어다 놓으면 경로가 입력됩니다).

```bash
cp settings.env.example settings.env && open -e settings.env
```

텍스트 편집기가 열리면 `=` 뒤에 값을 채우고 저장합니다.

| 항목 | 넣을 값 |
|---|---|
| `RUNNER_PASSWORD` | 토론방 웹페이지 비밀번호 (직접 정하기) |
| `GEMINI_API_KEY` | Gemini API 키 |
| `CLAUDE_CODE_OAUTH_TOKEN` | `claude setup-token`으로 받은 토큰 |

나머지 항목은 비워 두어도 됩니다.

## 3. NAS에 올리기

1. DSM **File Station**에서 `docker` 폴더 안에 `ai-debate` 폴더를 만듭니다.
2. 맥의 `meeting-board` 폴더 **안에 있는 파일과 폴더 전부**를 `docker/ai-debate`에 끌어다 놓습니다.
   `docker-compose.yml`, `Dockerfile`, `settings.env`가 `docker/ai-debate` 바로 아래에 있어야 합니다.

## 4. 실행하기

1. **Container Manager** → **프로젝트** → **생성**을 누릅니다.
2. 아래처럼 입력합니다. DSM 버전에 따라 메뉴 이름이 조금 다를 수 있습니다.
   - 프로젝트 이름: `ai-debate`
   - 경로: `docker/ai-debate`
   - 소스: 기존 `docker-compose.yml` 사용
3. 다음 → 완료를 누릅니다. 처음에는 이미지를 만드느라 몇 분 걸립니다.
4. 프로젝트 상태가 **실행 중**이 되면, 같은 집 네트워크의 브라우저에서 접속합니다.
   `http://NAS주소:8790` (예: `http://192.168.0.10:8790`)
5. 비밀번호 칸에 `RUNNER_PASSWORD` 값을 입력합니다. 한 번 들어가면 그 기기에서는 30일 동안 다시 묻지 않고,
   브라우저의 비밀번호 저장도 쓸 수 있습니다. `RUNNER_PASSWORD`를 바꾸면 모든 기기가 로그아웃됩니다.

NAS를 다시 켜도 자동으로 다시 실행됩니다.

## DSM 7.1 이하 (Container Manager 없음)

1~3단계는 같습니다. 4단계 대신 SSH로 실행합니다.

1. **SSH 켜기:** **제어판 → 터미널 및 SNMP → SSH 서비스 활성화**를 체크합니다.
2. **NAS 접속:** 맥 터미널에서 접속합니다.
   ```bash
   ssh 관리자계정@NAS주소
   ```
3. **이미지 만들기와 실행:**
   ```bash
   cd /volume1/docker/ai-debate
   ```
   ```bash
   sudo docker build -t ai-debate .
   ```
   ```bash
   sudo docker run -d --name ai-debate --restart unless-stopped -p 8790:8790 --env-file settings.env -v ai-debate-data:/data ai-debate
   ```
4. **설정을 바꾼 뒤:** 아래 두 명령으로 컨테이너를 지우고 3번의 `docker run`을 다시 실행합니다.
   토론 기록은 지워지지 않습니다. 새 버전 파일을 올렸다면 `docker build`부터 다시 합니다.
   ```bash
   sudo docker stop ai-debate
   ```
   ```bash
   sudo docker rm ai-debate
   ```

## 접속이 안 되면

- **컨테이너 상태:** `sudo docker ps -a --filter name=ai-debate`에서 STATUS가 `Up`인지 봅니다.
- **실행 기록:** `sudo docker logs --tail 30 ai-debate`에 `AI 토론방: http://0.0.0.0:8790`이 보이면 프로그램은 정상입니다.
- **주소:** DSM에 들어가는 주소에서 포트만 `8790`으로 바꾸고 `http://`로 접속합니다.
  QuickConnect 주소로는 안 됩니다. NAS 내부 IP는 **제어판 → 정보 센터 → 네트워크**에 있습니다.
- **방화벽:** **제어판 → 보안 → 방화벽**이 켜져 있으면 TCP 8790 허용 규칙을 "거부" 규칙보다 위에 추가합니다.

## 새 버전으로 업데이트하기 (DSM 7.1 / SSH)

1. 1단계의 ZIP을 다시 받아 압축을 풉니다.
2. `meeting-board` 안의 파일 전부를 `docker/ai-debate`에 올려 덮어씁니다.
   ZIP에는 `settings.env`가 없으므로 내 설정은 그대로 남습니다.
3. SSH에서 이미지를 다시 만들고 컨테이너를 새로 띄웁니다.
   ```bash
   cd /volume1/docker/ai-debate
   ```
   ```bash
   sudo docker build -t ai-debate .
   ```
   ```bash
   sudo docker stop ai-debate
   ```
   ```bash
   sudo docker rm ai-debate
   ```
   ```bash
   sudo docker run -d --name ai-debate --restart unless-stopped -p 8790:8790 --env-file settings.env -v ai-debate-data:/data ai-debate
   ```

## ChatGPT · Grok 추가

| AI | 키 발급 | settings.env에 넣을 줄 |
|---|---|---|
| ChatGPT | [platform.openai.com](https://platform.openai.com) (ChatGPT Plus 구독과 별도, 쓴 만큼 과금) | `OPENAI_API_KEY=`, `OPENAI_MODEL=` |
| Grok | [console.x.ai](https://console.x.ai) | `XAI_API_KEY=`, `GROK_MODEL=` |

1. **키 넣기:** 받은 키를 `settings.env`의 해당 줄에 넣습니다.
2. **이미지 만들기:** 위 업데이트 3단계의 `docker build`까지 실행합니다.
3. **모델 목록 보기:** 키는 `settings.env`에서 읽으므로 명령어 기록에 남지 않습니다.
   ```bash
   sudo docker run --rm --env-file settings.env ai-debate python tools/list_models.py chatgpt
   ```
   ```bash
   sudo docker run --rm --env-file settings.env ai-debate python tools/list_models.py grok
   ```
4. **모델 고르기:** 나온 목록 중 하나를 `OPENAI_MODEL=` / `GROK_MODEL=` 뒤에 넣습니다.
5. **다시 띄우기:** 컨테이너를 지우고 다시 실행합니다(위 업데이트 3단계의 `stop` / `rm` / `run`).
   토론방에 선택지가 나타납니다.

## 집 밖에서 쓰려면

두 가지 방법이 있습니다.

| 방법 | 장점 | 단점 |
|---|---|---|
| **A. HTTPS 주소로 공개** | 앱 없이 아무 브라우저에서 `https://내이름.synology.me:8443` 접속 | 인터넷에 열리므로 누구나 비밀번호를 시도할 수 있음. 공유기 설정 필요 |
| **B. Tailscale** | 인터넷에 아무것도 열지 않아 가장 안전 | 폰·노트북에 Tailscale 앱을 켜야 함 |

어느 경우든 공유기에서 **8790 포트를 직접 열지 마세요.** 8790은 HTTPS가 아니라서 비밀번호가 그대로 오갑니다.

### A. HTTPS 주소로 공개 (시놀로지 리버스 프록시)

토론방에는 비밀번호를 여러 번 틀리면 잠기는 장치가 있습니다.
- 같은 곳에서 10분 안에 5번 틀리면 그곳만 15분 차단
- 전체적으로 1시간에 30번 틀리면 15분 동안 모든 로그인 거부

그래도 비밀번호가 짧으면 위험하니 **먼저 `RUNNER_PASSWORD`를 16자 이상의 긴 문장으로 바꾸세요**
(예: 단어 4~5개를 이어 붙인 것). 바꾼 뒤 컨테이너를 다시 띄웁니다(`stop` → `rm` → `run`).

DSM 7.1 기준이고, 메뉴 이름은 버전에 따라 조금 다를 수 있습니다.

1. **주소 만들기 (DDNS):** **제어판 → 외부 액세스 → DDNS → 추가**
   - 서비스 공급자: `Synology`
   - 호스트 이름: 원하는 이름 (예: `mydebate` → `mydebate.synology.me`)
   - "Let's Encrypt에서 인증서를 받아 기본 인증서로 설정" 체크 → 확인
2. **리버스 프록시 만들기:** **제어판 → 로그인 포털 → 고급 → 리버스 프록시 → 생성**
   - 설명: `ai-debate`
   - 소스: 프로토콜 `HTTPS`, 호스트 이름 `mydebate.synology.me`, 포트 `8443`
   - 대상: 프로토콜 `HTTP`, 호스트 이름 `127.0.0.1`, 포트 `8790`
     (DSM 7.1은 `localhost`를 받지 않습니다. `127.0.0.1`도 거부되면 NAS의 내부 IP를 넣으세요)
   - **사용자 지정 머리글** 탭 → 생성 → 이름 `X-Real-IP`, 값 `$remote_addr`
     (접속자 주소를 넘겨서, 다른 사람이 비밀번호를 틀려도 내 접속은 잠기지 않게 합니다)
   - 저장
3. **인증서 연결 확인:** **제어판 → 보안 → 인증서 → 설정**에서 `ai-debate`(또는 `mydebate.synology.me:8443`)
   항목이 1번에서 받은 인증서로 되어 있는지 봅니다.
4. **공유기 포트포워딩:** 공유기 관리 화면에서 **외부 8443 → NAS 내부 IP의 8443 (TCP)** 규칙을 추가합니다.
   메뉴 위치는 공유기마다 다릅니다(보통 "포트포워딩" 또는 "NAT").
5. **DSM 방화벽:** 방화벽을 켜 두었다면 TCP `8443` 허용 규칙을 추가합니다.
6. **접속:** 휴대폰 데이터(와이파이 끄고)로 `https://mydebate.synology.me:8443`에 접속해 봅니다.

**LG U+ 공유기에서 확인한 것 (DS218+ 사용자 사례)**
- **진짜 공유기 찾기:** `192.168.219.1` 연결도에서 인터넷에 바로 붙은 기기가 진짜 공유기입니다.
  "브릿지"로 표시된 와이파이 공유기에서는 DHCP 고정 할당과 포트포워딩이 막혀 있습니다.
  NAS 고정 IP와 포트포워딩은 진짜 공유기에서 합니다.
- **IPv6 회선이면 IPv4 Only로 전환:** 공유기 상태 화면의 IP주소가 `2406:...` 같은 IPv6뿐이면,
  포트포워드 메뉴가 "IPv6로 사용 불가"라며 막힙니다.
  - **유선네트워크설정 → WAN 설정**을 **IPv4 Only**로 바꾸면 공인 IPv4를 받고 포트포워딩이 됩니다.
  - 바꾸기 전에 원래 설정을 캡처해 두세요. 바꾼 뒤 인터넷이 안 되면 그 설정으로 되돌리면 됩니다.
  - 전환 후 DSM DDNS에서 **업데이트**를 눌러 새 주소를 반영합니다.

**잘 안 될 때**
- 집 안에서는 되는데 밖에서 안 되면 4번 포트포워딩을 다시 확인하세요.
- 인터넷 회사에 따라 공유기 바깥 주소가 공인 IP가 아닌 경우(통신사 공유 IP)가 있습니다.
  이때는 포트포워딩이 동작하지 않으니 B(Tailscale)를 쓰세요.
- 인증서 경고가 나오면 3번을 확인하세요.

### B. Tailscale

- NAS: 패키지 센터에서 Tailscale을 설치하고 로그인합니다.
- 폰/노트북: Tailscale 앱을 설치하고 같은 계정으로 로그인합니다.
- 접속: `http://NAS의-Tailscale-주소:8790`

## 비용과 한도

- **Gemini 무료 티어:** 모델별 하루 20회입니다. 토론 한 번에 15회를 쓰니 하루 1번 정도 가능합니다.
  더 돌리려면 `settings.env`의 `GEMINI_MODEL`을 다른 모델로 바꾸거나 유료 요금제를 쓰세요.
- **Claude:** 내 Claude 구독 사용량에서 차감됩니다.

## 문제가 생기면

- **화면 확인:** 토론이 실패하면 페이지에 원인이 표시됩니다.
  - `401` / `Failed to authenticate`: 키나 토큰이 틀렸습니다.
  - `429`: 사용 한도를 다 썼습니다.
- **로그 확인:** Container Manager → **컨테이너** → `ai-debate` → **로그**
- **설정 변경:** `settings.env`를 바꾼 뒤 프로젝트를 **중지** → **시작**하세요.
- **새 버전으로 바꾸기:** 1~3단계를 다시 하고(`settings.env`는 그대로 두기)
  프로젝트에서 **중지** → **빌드** → **시작**하세요.

## SSH를 쓸 줄 안다면

4단계 대신 `docker/ai-debate` 폴더에서 아래 명령으로 실행해도 됩니다.

```bash
sudo docker compose up -d --build
```
