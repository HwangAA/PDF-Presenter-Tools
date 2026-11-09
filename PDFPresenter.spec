from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files
from PyInstaller.utils.hooks.qt import pyqt5_library_info

# Qt 5's compiled-in paths can lose Korean characters on Windows.
# Repair the hook's discovered paths using the real installed package location.
_ = pyqt5_library_info.version
qt_root = pyqt5_library_info.package_location / 'Qt5'
old_prefix = pyqt5_library_info.location['PrefixPath']
if qt_root.is_dir() and not Path(old_prefix).is_dir():
    for key, value in pyqt5_library_info.location.items():
        if value.startswith(old_prefix):
            pyqt5_library_info.location[key] = str(qt_root) + value[len(old_prefix):]
    pyqt5_library_info.qt_inside_package = True
    pyqt5_library_info.qt_lib_dir = qt_root / 'bin'

root = Path(SPECPATH)
fonts = [root / 'assets/fonts' / name for name in
         ('PRETENDARD-REGULAR.OTF', 'PRETENDARD-SEMIBOLD.OTF')]
if not all(font.is_file() for font in fonts) or not (root / 'assets/fonts/OFL.txt').is_file():
    raise RuntimeError('Bundled fonts and OFL license are required.')

a = Analysis(
    [str(root / 'pdf_presenter_fixed.py')],
    pathex=[str(root)],
    binaries=[],
    datas=[(str(font), 'assets/fonts') for font in fonts] +
          [(str(root / 'assets/fonts/OFL.txt'), 'assets/fonts'),
           (str(root / 'assets' / 'app-icon.png'), 'assets')] + collect_data_files('qt_material'),
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name='PDFPresenter', debug=False, bootloader_ignore_signals=False,
    strip=False, upx=False, console=False,
    icon=str(root / 'assets' / 'app-icon.ico'),
)
