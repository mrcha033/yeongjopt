# YeongjoPT Backend

YeongjoPT는 FastChat 기반의 AI 대화 시스템으로, OpenAI API 호환 서버와 Gradio 웹 인터페이스를 모두 지원합니다.

## 🚀 Features

- **OpenAI API 호환**: OpenAI ChatCompletion API와 호환되는 REST API 제공
- **Gradio 웹 인터페이스**: 브라우저 기반 채팅 인터페이스
- **분산 아키텍처**: Controller-Worker 구조로 확장성 제공
- **다양한 모델 지원**: Hugging Face 모델들을 쉽게 로드하여 사용 가능
- **보안**: API 키 인증 지원 (선택사항)

## 📋 Requirements

- Python 3.8+
- CUDA 지원 GPU (권장)
- 8GB+ RAM (모델 크기에 따라 조정)

## 🛠 Installation

1. **의존성 설치**:
```bash
pip install -r requirements.txt
```

2. **환경 설정** (선택사항):
```bash
# config.py에서 설정 수정 또는 환경 변수 사용
export MODEL_PATH="your/model/path"
export API_KEY="your-api-key"  # 선택사항
```

## 🎯 Usage

### OpenAI API 호환 서버

```bash
# Linux/Mac
./run_api.sh [model_path]

# Windows
bash run_api.sh [model_path]
```

기본적으로 다음 엔드포인트를 제공합니다:
- `http://localhost:8000/v1/chat/completions` - ChatCompletion API
- `http://localhost:8000/v1/models` - 사용 가능한 모델 목록
- `http://localhost:8000/health` - 헬스 체크

### Gradio 웹 인터페이스

```bash
# Linux/Mac  
./run.sh [model_path]

# Windows
bash run.sh [model_path]
```

브라우저에서 `http://localhost:7860`으로 접속

## 🔧 Configuration

`config.py`에서 다음 설정들을 수정할 수 있습니다:

```python
class Settings:
    HOST: str = "0.0.0.0"
    CONTROLLER_PORT: int = 21001
    MODEL_WORKER_PORT: int = 21002
    API_PORT: int = 8000
    GRADIO_PORT: int = 7860
    
    DEFAULT_MODEL_PATH: str = "mistralai/Mistral-7B-Instruct-v0.1"
    MODEL_NAME: str = "yeongjopt-mistral-7b"
    
    API_KEY: Optional[str] = None  # API 키 설정 (선택사항)
    WORKER_CONCURRENCY: int = 5
```

## 🌐 API Usage Examples

### Python (OpenAI 클라이언트)

```python
import openai

# API 서버 설정
openai.api_base = "http://localhost:8000/v1"
openai.api_key = "your-api-key"  # API 키를 설정한 경우

# 채팅 완성
response = openai.ChatCompletion.create(
    model="yeongjopt-mistral-7b",
    messages=[
        {"role": "user", "content": "안녕하세요!"}
    ],
    temperature=0.7,
    max_tokens=512
)

print(response.choices[0].message.content)
```

### cURL

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your-api-key" \
  -d '{
    "model": "yeongjopt-mistral-7b",
    "messages": [
      {"role": "user", "content": "Hello!"}
    ],
    "temperature": 0.7,
    "max_tokens": 512
  }'
```

### JavaScript/Node.js

```javascript
const response = await fetch('http://localhost:8000/v1/chat/completions', {
    method: 'POST',
    headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer your-api-key'
    },
    body: JSON.stringify({
        model: 'yeongjopt-mistral-7b',
        messages: [
            { role: 'user', content: 'Hello!' }
        ],
        temperature: 0.7,
        max_tokens: 512
    })
});

const data = await response.json();
console.log(data.choices[0].message.content);
```

## 🐳 Docker Support (추후 구현 예정)

```dockerfile
# Dockerfile
FROM python:3.9-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
EXPOSE 8000

CMD ["bash", "run_api.sh"]
```

## 🏗 Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Client        │────│  API Server     │────│   Controller    │
│                 │    │  (Port 8000)    │    │  (Port 21001)   │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                                       │
                                               ┌─────────────────┐
                                               │  Model Worker   │
                                               │  (Port 21002)   │
                                               └─────────────────┘
```

## 🔒 Security

- API 키 인증 지원 (config.py에서 `API_KEY` 설정)
- CORS 설정 포함
- HTTPS는 리버스 프록시(nginx 등)에서 처리 권장

## 📊 Monitoring

로그 파일들은 `./logs/` 디렉토리에 저장됩니다:
- `controller.log` - 컨트롤러 로그
- `worker.log` - 모델 워커 로그  
- `api_server.log` - API 서버 로그
- `gradio.log` - Gradio 서버 로그

## 🚨 Troubleshooting

### 일반적인 문제들

1. **모델 로딩 실패**:
   - GPU 메모리 부족: 더 작은 모델 사용 또는 `--load-8bit` 옵션 추가
   - 모델 경로 확인: 유효한 Hugging Face 모델 경로인지 확인

2. **포트 충돌**:
   - `config.py`에서 포트 번호 변경
   - 또는 환경 변수로 포트 설정

3. **API 인증 오류**:
   - API 키가 올바른지 확인
   - `Authorization: Bearer <api-key>` 헤더 확인

## 🤝 Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- [FastChat](https://github.com/lm-sys/FastChat) - 기반 프레임워크
- [Hugging Face](https://huggingface.co/) - 모델 허브
- [FastAPI](https://fastapi.tiangolo.com/) - API 프레임워크 