# PDF-Presenter-Tools
When presenting a PDF, you can use monitor extension to present on another monitor.
You can also see the number of pages remaining during the presentation.

## PDF 발표자 도구 2.4

Windows에서 PDF를 발표할 때 쓰는 도구입니다. 제어 창에는 현재 페이지와 다음 페이지를, 발표를 시작하면 청중 모니터에는 현재 페이지만 표시합니다. PDF를 열어도 발표가 자동으로 시작되지 않습니다.

## 소스에서 실행하기

검증 환경: Windows x64, CPython 3.14.3. PowerShell에서 이 폴더로 이동해 실행하세요.

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\python.exe pdf_presenter_fixed.py
```

PDF를 열고 상단에서 발표 모니터를 선택한 뒤 **발표 시작**을 누릅니다. ←·↑·Page Up은 이전 페이지, →·↓·Page Down은 다음 페이지입니다. 페이지 번호를 입력하고 Enter를 눌러 이동하거나, 분할선을 드래그해 미리보기와 조작 영역 크기를 조절할 수 있습니다.

## 테스트 및 개인용 EXE 빌드

```powershell
.\.venv\Scripts\python.exe test_pdf_presenter.py
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm PDFPresenter.spec
```

결과는 `dist/PDFPresenter.exe`입니다. 폰트 두 개와 프로그램 아이콘이 포함됩니다. 이 소스 배포에는 빌드된 EXE와 외부 라이브러리 코드는 포함하지 않습니다. 의존성은 설치할 때 별도로 내려받습니다. EXE를 다시 배포하는 경우에는 함께 묶이는 외부 구성 요소의 조건도 따르세요.

## 라이선스

이 저장소의 자체 프로그램 코드, 빌드 설정, 문서 및 자체 앱 아이콘은 GNU Affero General Public License version 3 only(AGPL-3.0-only)로 제공합니다. 원문은 [LICENSE](LICENSE)에 있습니다. 타사 구성 요소에 대한 권리는 각 권리자에게 있으며, Pretendard 폰트에는 별도 OFL이 적용됩니다. [타사 라이선스 안내](THIRD_PARTY_NOTICES.md)를 확인하세요.
