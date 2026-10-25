# Third-party licenses

직접 Python 의존성 버전은 `requirements.txt`에 고정했습니다. 라이선스 표기는 설치된 배포 메타데이터의 License-Expression 또는 License 필드에서 확인했습니다.

| 구성 요소 | 버전 | 라이선스 | 용도 |
|---|---:|---|---|
| Streamlit | 1.66.1 | Apache-2.0 | 로컬 웹 인터페이스 |
| Pillow | 13.0.0 | MIT-CMU | 이미지 입력·처리 |
| pytest | 9.1.1 | MIT | 테스트 실행 전용 |
| Playwright (선택 E2E) | 1.64.1 | Apache-2.0 | 브라우저 자동화 |
| SUIT 글꼴 | — | SIL Open Font License 1.1 | UI 글꼴 (`static/fonts/LICENSE.txt`) |
| Tesseract OCR | 시스템 설치본 | Apache-2.0 | 로컬 OCR 엔진 |
| tessdata_best (kor, eng) | `e12c65a915945e4c28e237a9b52bc4a8f39a0cec` | Apache-2.0 | 정밀 한국어·영어 OCR 모델 ([출처](https://github.com/tesseract-ocr/tessdata_best/tree/e12c65a915945e4c28e237a9b52bc4a8f39a0cec)) |
| Poppler (`pdftotext`, `pdftoppm`) | 시스템 설치본 | GPL-2.0-or-later | PDF 텍스트 추출·페이지 렌더링 |

Streamlit 전이 의존성은 각 패키지 배포 메타데이터의 라이선스를 따릅니다. 별도 Python PDF 바인딩(pypdfium2 등)은 이 릴리스의 requirements에 포함되지 않습니다.
