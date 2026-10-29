# 시놀로지 NAS에 AI 토론방 설치하기

NAS에서 24시간 돌아가는 웹페이지를 만듭니다. 폰이나 노트북 브라우저에서 비밀번호를 넣고
주제를 입력한 뒤 **시작**을 누르면 Gemini와 Claude가 토론하고, 진행 상황이 실시간으로 보입니다.
지난 토론 기록도 그 페이지에 남습니다. 맥은 처음 설치할 때만 필요합니다.

## 0. 확인할 것

- **Container Manager 지원 여부:** DSM **패키지 센터**에서 `Container Manager`를 검색하세요.
  - 보이면 설치합니다. 설치하면 `docker` 공유 폴더가 생깁니다.
  - 안 보이면 이 NAS 모델은 지원하지 않는 모델이라 이 방법을 쓸 수 없습니다.
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
5. 아이디는 아무거나, 비밀번호는 `RUNNER_PASSWORD`에 넣은 값을 입력합니다.

NAS를 다시 켜도 자동으로 다시 실행됩니다.

## 집 밖에서 쓰려면

- 공유기 **포트포워딩으로 8790을 인터넷에 열지 마세요.** 이 페이지는 HTTPS가 아니라서
  비밀번호가 암호화되지 않은 채 오가고, 누군가 들어오면 내 API 사용량을 쓸 수 있습니다.
- 대신 **Tailscale**을 쓰세요(무료).
  - NAS: 패키지 센터에서 Tailscale을 설치합니다.
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
