STYLE = """
QWidget { color: #eee9e3; font-family: 'Segoe UI'; font-size: 14px; }
QMainWindow, QDialog { background: #111112; }
QFrame#card { background: #1a1919; border: 1px solid #443328; border-radius: 4px; }
QLabel { background: transparent; }
QLabel#brand { font-family: 'Bahnschrift'; font-size: 34px; font-weight: 700; color: #ff7800; }
QLabel#heading { font-family: 'Bahnschrift'; font-size: 21px; font-weight: 600; color: #f2e8dd; }
QLabel#muted { color: #a69c93; font-size: 13px; }
QLabel#cropSize { color: #ff7800; font-family: 'Consolas'; font-size: 13px; }
QLineEdit, QPlainTextEdit { background: #111112; border: 1px solid #403933;
 border-radius: 2px; padding: 10px; selection-background-color: #804323; }
QLineEdit:hover, QPlainTextEdit:hover { border-color: #68503c; }
QLineEdit:focus, QPlainTextEdit:focus { border: 1px solid #ff7800; }
QLineEdit:disabled, QPlainTextEdit:disabled { background: #151414; color: #74685e; border-color: #322b26; }
QInputDialog QComboBox, QInputDialog QComboBox QAbstractItemView {
 color: #ffffff; background-color: #303030; border: 1px solid #565656;
 selection-color: #ffffff; selection-background-color: #505050; }
QInputDialog QComboBox QAbstractItemView::item:selected {
 color: #ffffff; background-color: #505050; }
QPushButton { background: #26211d; border: 1px solid #65503d; border-radius: 2px;
 padding: 10px 15px; color: #e4d6c9; outline: none; }
QPushButton:hover { background: #36271d; border-color: #ff7800; color: #ff941f; }
QPushButton:pressed { background: #4c2e19; }
QPushButton:focus { border-color: #ff7800; }
QPushButton:disabled { color: #756453; background: #211d19; border-color: #3d3026; }
QPushButton#primary { background: #ff7800;
 color: #1b1008; border: 1px solid #ff7800; font-weight: 700; }
QPushButton#primary:hover { background: #ff8c1a; border-color: #ff8c1a; }
QPushButton#primary:pressed { background: #df6200; border-color: #df6200; }
QPushButton#primary:disabled { background: #4f301c; color: #a67c57; border-color: #6a4023; }
QPushButton#terms { color: #c38e64; background: #1d1916; padding: 6px 11px; font-size: 12px; }
QPushButton#terms:hover { color: #ff941f; border-color: #ff7800; }
QProgressBar { background: #30241c; border: none; border-radius: 0; }
QProgressBar::chunk { background: #ff7800; }
QToolTip { background: #30231b; color: #ffdfbf; border: 1px solid #986239; padding: 4px; }
QScrollArea { background: transparent; border: none; }
QScrollBar:vertical { background: #171412; width: 8px; margin: 0; }
QScrollBar::handle:vertical { background: #745035; min-height: 30px; border-radius: 2px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QSlider::groove:horizontal { height: 4px; background: #493225; }
QSlider::sub-page:horizontal { background: #ff7800; }
QSlider::handle:horizontal { background: #ff7800; border: 1px solid #ff941f; width: 12px;
 margin: -6px 0; border-radius: 1px; }
"""
