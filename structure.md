## ✅ 전체 폴더 및 파일 구조

```
fastchat/
├── __init__.py                        # 패키지 버전 관리
├── conversation.py                   # Prompt 템플릿 관리 및 메시지 포맷 정의
├── serve/
│   ├── controller.py                 # 모델 작업자 관리 (Controller 서비스)
│   ├── model_worker.py              # 실제 모델 추론 수행 (Model Worker 서비스)
│   ├── gradio_web_server.py         # Gradio UI 웹 서버 (사용자 인터페이스)
│   ├── openai_api_server.py         # OpenAI 호환 REST API 서버
│   └── vision/                      # 이미지 입력 등 멀티모달 확장 기능
├── model/                            # 모델 초기화 및 변환기 정의
├── cli/                              # CLI 명령어 (예: 채팅, 채점, 번역 등)
├── utils/                            # 공통 유틸 함수
├── log/                              # 로그 파일 디렉토리
└── tests/                            # 테스트용 스크립트
```

---

## 🔁 전체 서비스 간 연결 구조 (서비스 흐름)

```
┌──────────────────────────┐
│      사용자 브라우저       │
└────────────▲─────────────┘
             │ (HTTP)
             ▼
┌──────────────────────────┐
│ Gradio Web Server        │ <──── or ────> OpenAI API Server
│ (serve/gradio_web_server.py) │
└────────────▲─────────────┘
             │ (RPC: HTTP/WebSocket)
             ▼
┌──────────────────────────┐
│ Controller               │ (serve/controller.py)
│ 모델 작업자 상태 추적     │
└────────────▲─────────────┘
             │ (RPC)
             ▼
┌──────────────────────────┐
│ Model Worker             │ (serve/model_worker.py)
│ 모델 로딩 및 응답 생성    │
└──────────────────────────┘
```

---

## 🧠 주요 컴포넌트의 역할

| 컴포넌트                   | 역할                     | 상태(state) 저장 여부               |
| ---------------------- | ---------------------- | ----------------------------- |
| `controller.py`        | 모델 워커 등록 및 라우팅         | ✔️ 모델 등록 상태 유지 (in-memory)    |
| `model_worker.py`      | LLM 모델 로딩 및 추론 응답      | ✔️ 모델 로컬 메모리에 상주              |
| `conversation.py`      | 메시지 포맷 구성, 템플릿 관리      | ✔️ 대화 상태 (`Conversation` 클래스) |
| `gradio_web_server.py` | Gradio 기반 사용자 인터페이스 제공 | ❌ 상태는 서버가 아닌 클라이언트에 있음        |
| `openai_api_server.py` | OpenAI API 호환 REST 서버  | ❌ Stateless                   |
| `vision/`              | 이미지 입력 처리 (옵션)         | ✔️ 이미지 상태를 메모리/디스크에 보관 가능     |

---

## 💾 상태(State) 관리 구조

| 위치                      | 내용                | 휘발성 여부    |
| ----------------------- | ----------------- | --------- |
| `Conversation.messages` | 대화 이력 (in-memory) | 휘발성       |
| `controller` 내부 dict    | 등록된 모델 및 워커 상태    | 휘발성       |
| `model_worker`          | 로딩된 모델 객체         | 휘발성       |
| `/log/*.log`            | 런타임 로그            | 영속적 (디스크) |

---

## 📍운영 단계별 예시 흐름

1. **사용자**가 Gradio UI에 질문 입력
2. Gradio Web Server가 **Controller**에 모델 요청 중계
3. Controller는 가용 **Model Worker**를 탐색
4. Model Worker는 **conversation.py**의 템플릿으로 메시지를 구성해 모델에 입력
5. 추론 결과가 사용자에게 반환됨

---

## 🛠️ 확장 포인트

| 목적           | 위치                                      | 설명                            |
| ------------ | --------------------------------------- | ----------------------------- |
| 새로운 템플릿 추가   | `conversation.py`                       | `register_conv_template()` 사용 |
| 커스텀 모델 연결    | `model_worker.py`                       | `--model-path` 인자로 변경 가능      |
| API 게이트웨이 연동 | `openai_api_server.py`                  | FastAPI 기반으로 쉽게 확장 가능         |
| 배포           | `docker-compose`, `systemd`, `fly.io` 등 | 서버별로 설정                       |