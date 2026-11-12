"""Application-owned UI messages. PDF contents, paths and monitor names are never translated."""
LANGUAGES = {'ko': '한국어', 'en': 'English', 'ja': '日本語', 'zh_CN': '简体中文'}
# Source (Korean) | English | Japanese | Simplified Chinese
_ROWS = '''언어|Language|言語|语言
PDF 발표자 도구|PDF Presenter|PDF プレゼンター|PDF 演示工具
오디언스 뷰 (청중 화면)|Audience View|観客用画面|观众屏幕
발표할 PDF를 열어 주세요|Open a PDF to present|発表する PDF を開いてください|请打开要演示的 PDF
PDF 파일을 열어 주세요.|Open a PDF file.|PDF ファイルを開いてください。|请打开 PDF 文件。
PDF를 열어 주세요.|Open a PDF first.|先に PDF を開いてください。|请先打开 PDF。
PDF 파일 열기|Open PDF|PDF を開く|打开 PDF
PDF 파일 열기 · Ctrl+O|Open PDF · Ctrl+O|PDF を開く · Ctrl+O|打开 PDF · Ctrl+O
PDF 파일 (*.pdf)|PDF files (*.pdf)|PDF ファイル (*.pdf)|PDF 文件 (*.pdf)
현재 화면|Current page|現在のページ|当前页
다음 페이지|Next page|次のページ|下一页
CURRENT|CURRENT|現在|当前
UP NEXT|UP NEXT|次|下一页
페이지|Page|ページ|页码
←  이전|←  Previous|←  前へ|←  上一页
다음  →|Next  →|次へ  →|下一页  →
이전 페이지|Previous page|前のページ|上一页
첫 페이지입니다.|First page.|最初のページです。|已是第一页。
마지막 페이지입니다.|Last page.|最後のページです。|已是最后一页。
남은 페이지  {value}|Pages left: {value}|残りページ数：{value}|剩余页数：{value}
발표 시작|Start presentation|発表開始|开始演示
발표 정지|Stop presentation|発表停止|停止演示
프레젠테이션 시작|Start presentation|発表を開始|开始演示
프레젠테이션 정지|Stop presentation|発表を停止|停止演示
청중 화면을 숨깁니다. 제어 화면에서는 계속 준비할 수 있습니다.|Hide the audience screen and keep preparing in the control window.|観客用画面を非表示にします。操作画面で準備を続けられます。|隐藏观众屏幕，可在控制窗口继续准备。
현재 페이지부터 청중 화면에 표시합니다.|Present the current page to the audience.|現在のページから観客用画面に表示します。|从当前页开始向观众展示。
발표 중|Presenting|発表中|演示中
발표 대기|Ready to present|発表待機中|演示待命
전체 화면|Full screen|全画面|全屏
창 모드|Windowed|ウィンドウ表示|窗口模式
자동|Auto|自動|自动
선택|Manual|手動|手动
모니터|Monitor|モニター|显示器
발표 모니터: {name}|Display: {name}|発表モニター：{name}|演示屏幕：{name}
발표 모니터 선택|Choose presentation display|発表モニターを選択|选择演示屏幕
청중에게 표시할 모니터를 선택합니다.|Choose the display the audience will see.|観客用のモニターを選択します。|选择观众使用的显示器。
다른 모니터: 전체 화면 / 같은 모니터: 창 모드|Other display: full screen / same display: windowed|別のモニター：全画面／同じモニター：ウィンドウ表示|其他显示器：全屏 / 同一显示器：窗口模式
자동 선택 (발표자 화면과 다른 모니터)|Automatic (prefer another display)|自動選択（操作画面と別のモニターを優先）|自动选择（优先使用其他显示器）
영역 크기 조절|Resize panels|領域のサイズを変更|调整区域大小
드래그하여 크기 조절 · 방향키로도 조절할 수 있습니다.|Drag to resize, or use the arrow keys when focused.|ドラッグ、または選択して矢印キーでサイズを変更します。|拖动调整大小，或选中后使用方向键。
현재 화면과 다음 페이지 비율 조절|Adjust current and next page widths|現在と次のページの幅を調整|调整当前页和下一页的宽度
슬라이드와 페이지 조작 영역 높이 조절|Adjust slide and navigation panel heights|スライドと操作領域の高さを調整|调整幻灯片和翻页区域的高度
페이지 번호 입력 후 Enter · Esc 또는 여백 클릭으로 취소|Enter a page number and press Enter. Press Esc or click outside to cancel.|ページ番号を入力して Enter。Esc または余白をクリックしてキャンセル。|输入页码后按 Enter；按 Esc 或点击空白处取消。
이동할 페이지 번호|Go to page number|移動先のページ番号|要跳转到的页码
← ↑ 이전    → ↓ 다음    ·    번호 입력 후 Enter로 이동|← ↑ Previous    → ↓ Next    ·    Page number + Enter|← ↑ 前へ    → ↓ 次へ    ·    ページ番号＋Enter|← ↑ 上一页    → ↓ 下一页    ·    页码 + Enter
개발 & 문의|Contact|開発・お問い合わせ|开发与联系
페이지를 준비 중입니다. 잠시 후 다시 시도해 주세요.|Preparing a page. Please try again shortly.|ページを準備中です。少し待ってから再試行してください。|正在准备页面，请稍后重试。
페이지를 준비하고 있습니다…|Preparing page…|ページを準備中…|正在准备页面…
{page}페이지를 준비하고 있습니다…|Preparing page {page}…|{page} ページを準備中…|正在准备第 {page} 页…
{page}페이지 준비 중|Preparing page {page}|{page} ページを準備中|正在准备第 {page} 页
{page}페이지 준비 중 · {shown}페이지 표시 중|Preparing page {page} · Showing page {shown}|{page} ページを準備中 · {shown} ページを表示中|正在准备第 {page} 页 · 当前显示第 {shown} 页
미리보기를 준비하고 있습니다…|Preparing preview…|プレビューを準備中…|正在准备预览…
미리보기를 표시할 수 없습니다.|Preview unavailable.|プレビューを表示できません。|无法显示预览。
페이지 크기가 올바르지 않습니다.|Invalid page dimensions.|ページサイズが正しくありません。|页面尺寸无效。
PDF 파일이 아닙니다.|This is not a PDF file.|PDF ファイルではありません。|这不是 PDF 文件。
비밀번호가 설정된 보안 PDF는 열 수 없습니다.|Password-protected PDFs cannot be opened.|パスワードで保護された PDF は開けません。|无法打开受密码保护的 PDF。
페이지가 없는 PDF입니다.|The PDF contains no pages.|PDF にページがありません。|此 PDF 没有页面。
파일을 열 수 없습니다: {error}|Could not open the file: {error}|ファイルを開けません：{error}|无法打开文件：{error}
페이지를 표시할 수 없습니다: {error}|Could not display the page: {error}|ページを表示できません：{error}|无法显示页面：{error}
PDF 처리 통신 오류: {error}. 다시 시도해 주세요.|PDF worker communication failed: {error}. Please try again.|PDF 処理の通信エラー：{error}。もう一度お試しください。|PDF 处理通信错误：{error}。请重试。
PDF 처리 프로세스가 종료되었습니다. 다시 시도해 주세요.|The PDF worker stopped. Please try again.|PDF 処理が停止しました。もう一度お試しください。|PDF 处理进程已停止。请重试。
PDF 처리 시간이 60초를 초과했습니다. 다시 시도해 주세요.|PDF processing exceeded 60 seconds. Please try again.|PDF 処理が60秒を超えました。もう一度お試しください。|PDF 处理超过 60 秒。请重试。
페이지 이미지를 만들 수 없습니다.|Could not create the page image.|ページ画像を作成できません。|无法创建页面图像。'''
CATALOG = {key: dict(zip(LANGUAGES, (key, *values))) for key, *values in (line.split('|') for line in _ROWS.splitlines())}

def translate(language, key, **values):
    template = CATALOG.get(key, {}).get(language, key)
    return template.format(**values) if values else template


def language_from_langid(langid):
    # PRIMARYLANGID: regional variants share the low ten language bits.
    if langid & 0x3ff == 0x04:
        return 'zh_CN' if langid in (0x0004, 0x0804, 0x1004) else 'en'
    return {0x12: 'ko', 0x09: 'en', 0x11: 'ja'}.get(langid & 0x3ff, 'en')


def system_language():
    # Query the user's UI language, independently of keyboard and regional formats.
    import ctypes
    try:
        get_language = ctypes.windll.kernel32.GetUserDefaultUILanguage
        get_language.argtypes = []
        get_language.restype = ctypes.c_ushort
        return language_from_langid(get_language())
    except (AttributeError, OSError):
        return 'en'
