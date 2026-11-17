import sys


def main():
    from app.adapters.stdio import configure_stdio

    worker = "--youtube-worker" in sys.argv
    configure_stdio(worker=worker)
    if worker:
        from app.adapters.youtube_worker import main as worker_main

        return worker_main(sys.argv[2:])

    from PySide6.QtWidgets import QApplication

    from app.ui.window import MainWindow

    application = QApplication(sys.argv)
    application.setApplicationName("MDOW")
    application.setOrganizationName("MDOW")
    window = MainWindow()
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
