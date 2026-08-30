# NetScope

Fiddler 스타일의 HTTP/HTTPS 네트워크 트래픽 인스펙터 (UI 프로토타입)

## 요구사항

- Python 3.14+
- PySide6

## 설치

```bash
pip install PySide6
```

## 실행

```bash
cd NetScope
python main.py
```

## 사용법

1. **Start** 버튼 클릭 → 트래픽 캡처 시작
2. 세션 목록에서 항목 클릭 → 하단에 Request / Response 상세 표시
3. **Headers / Body / JSON / Raw** 탭으로 전환하며 내용 확인
4. 상단 검색창에 텍스트 입력 → host, path, method, status 기준 실시간 필터
5. **Stop** 버튼 → 캡처 중지
6. **Clear** 버튼 → 전체 세션 초기화

## 프로젝트 구조

```
NetScope/
├── main.py                       # 엔트리포인트
└── netscope/
    ├── models/
    │   ├── session.py            # SessionEntry 데이터 클래스
    │   └── session_table_model.py# QAbstractTableModel 구현
    ├── proxy/
    │   └── engine.py             # ProxyEngine 인터페이스 + StubProxyEngine
    └── ui/
        ├── main_window.py        # 메인 윈도우
        ├── toolbar.py            # 툴바 (Start/Stop/Search/Clear)
        ├── session_table.py      # 세션 테이블 + 필터 프록시
        └── detail_panel.py       # Request/Response 상세 패널
```

## 실제 프록시 엔진 연결

현재는 `StubProxyEngine`이 더미 트래픽을 생성합니다.
실제 프록시(mitmproxy 등)를 붙이려면 `ProxyEngine`을 상속해 구현 후 `MainWindow._engine`을 교체하면 됩니다.

```python
# netscope/proxy/engine.py
class MyProxyEngine(ProxyEngine):
    def start(self, port: int = 8888): ...
    def stop(self): ...
    def is_running(self) -> bool: ...
```
