# Third-party licenses

DOCULENS와 함께 제공되는 구성 요소의 버전·라이선스·출처입니다. 포함된 구성 요소의 저작권 및 라이선스 고지를 유지합니다.

| 구성 요소 | 버전 | 라이선스 | 배포 내용·고지 |
|---|---:|---|---|
| DOCULENS Python 런타임: Streamlit 및 전이 의존성 | requirements.txt 고정 버전 | Apache-2.0, BSD, MIT 등 각 배포 메타데이터에 기재된 라이선스 | PyInstaller onedir의 `_internal`에 포함 |
| Pillow | 13.0.0 | MIT-CMU | Python 이미지 처리 |
| Python / PyInstaller 부트로더 | 빌드 환경 버전 | PSF-2.0 / PyInstaller 예외 포함 GPL-2.0-or-later | Python 런타임·부트로더가 `_internal`에 포함. PyInstaller 라이선스: https://github.com/pyinstaller/pyinstaller/blob/develop/COPYING.txt |
| Tesseract OCR (UB Mannheim Windows 빌드) | 5.4.0.20240606 | Apache-2.0 | `tools/tesseract`의 실행 파일·필요 DLL. 라이선스 전문은 이 폴더의 `tools/tesseract/LICENSE`에 포함. 출처: https://github.com/UB-Mannheim/tesseract/releases/tag/v5.4.0.20240606 |
| tessdata_best 한국어·영어 모델 | commit `e12c65a915945e4c28e237a9b52bc4a8f39a0cec` | Apache-2.0 | `tools/tessdata/kor.traineddata`, `eng.traineddata`; 설치 스크립트의 고정 SHA-256과 일치. 출처: https://github.com/tesseract-ocr/tessdata_best/tree/e12c65a915945e4c28e237a9b52bc4a8f39a0cec |
| Poppler Windows | 26.09.0-0 | GPL-2.0-or-later | `pdfinfo.exe`, `pdftotext.exe`, `pdftoppm.exe`, 런타임 DLL 및 PDF 문자 맵. Poppler 고지 전문은 `tools/poppler/share/poppler/COPYING` 및 `COPYING.gpl2`에 포함. 출처: https://github.com/oschwartz10612/poppler-windows/releases/tag/v26.09.0-0 |
| Poppler 재배포 빌드 스크립트 | 26.09.0-0 | MIT | Windows 재배포 저장소의 고지: https://github.com/oschwartz10612/poppler-windows/blob/master/LICENSE |
| SUIT 글꼴 | — | SIL Open Font License 1.1 | `static/fonts/LICENSE.txt` |

Poppler는 GPL 구성 요소입니다. 해당 바이너리의 대응 소스는 Poppler Windows 패키지 출처와 conda-forge 빌드 레시피에서 확인할 수 있습니다: https://github.com/oschwartz10612/poppler-windows/tree/v26.09.0-0 및 https://github.com/conda-forge/poppler-feedstock/tree/main. Poppler의 `COPYING.gpl2` 및 `COPYING`을 함께 제공합니다.

직접 Python 의존성은 `requirements.txt`에 고정했습니다. 시험 실행에만 쓰이는 pytest와 Playwright는 최종 실행 파일에 포함하지 않습니다. DOCULENS 소스 자체의 조건은 저장소 루트 `LICENSE`(MIT + Commons Clause)를 따릅니다.
