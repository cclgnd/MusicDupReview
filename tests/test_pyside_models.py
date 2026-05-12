import unittest

try:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication
    from pyside_app.models.file_explorer import FileExplorerModel
    from pyside_app.models.duplicate_tables import DuplicateFilesModel, DuplicateGroupsModel
    from pyside_app.widgets.file_preview import FilePreviewWidget
except ModuleNotFoundError:
    Qt = None
    QApplication = None
    DuplicateFilesModel = None
    DuplicateGroupsModel = None
    FileExplorerModel = None
    FilePreviewWidget = None


@unittest.skipIf(DuplicateGroupsModel is None, "PySide6 is not installed")
class PySideModelTests(unittest.TestCase):
    def test_group_model_exposes_group_id_and_columns(self):
        model = DuplicateGroupsModel()
        model.set_groups([[12, "audio_md5", 3, "10.00 MB", "5.00 MB", r"C:\music\a.mp3"]])

        self.assertEqual(model.rowCount(), 1)
        self.assertEqual(model.columnCount(), 6)
        self.assertEqual(model.group_id_at(0), 12)
        self.assertEqual(model.data(model.index(0, 1), Qt.DisplayRole), "audio_md5")

    def test_file_model_formats_state_and_keeps_source_row(self):
        row = {
            "id": 7,
            "decision": "delete",
            "nombre": "a.mp3",
            "extension": ".mp3",
            "tamano": 2048,
            "carpeta": r"C:\music",
            "ruta": r"C:\music\a.mp3",
        }
        model = DuplicateFilesModel()
        model.set_files([row])

        self.assertEqual(model.data(model.index(0, 0), Qt.DisplayRole), "Trash")
        self.assertEqual(model.data(model.index(0, 3), Qt.DisplayRole), "2.00 KB")
        self.assertEqual(model.file_rows_at([0]), [row])

    def test_file_explorer_model_formats_hash_link_rows(self):
        model = FileExplorerModel()
        model.set_files([{
            "nombre": "b.flac",
            "extension": ".flac",
            "tamano": 1024,
            "carpeta": r"C:\music",
            "decision": "master",
            "hash_link": "same as previous",
        }])

        self.assertEqual(model.data(model.index(0, 0), Qt.DisplayRole), "b.flac")
        self.assertEqual(model.data(model.index(0, 2), Qt.DisplayRole), "1.00 KB")
        self.assertEqual(model.data(model.index(0, 4), Qt.DisplayRole), "Keep")
        self.assertEqual(model.data(model.index(0, 5), Qt.DisplayRole), "same as previous")

    def test_file_explorer_model_returns_source_rows(self):
        row = {"nombre": "b.flac", "ruta": r"C:\music\b.flac"}
        model = FileExplorerModel()
        model.set_files([row])

        self.assertEqual(model.file_rows_at([0, 3]), [row])

    def test_file_preview_shows_selected_file_details(self):
        app = QApplication.instance() or QApplication([])
        preview = FilePreviewWidget()

        preview.set_file({
            "nombre": "song.mp3",
            "decision": "master",
            "tamano": 2048,
            "carpeta": r"C:\music",
            "ruta": r"C:\music\song.mp3",
            "md5": "filehash",
            "audio_md5": "audiohash",
        })

        self.assertEqual(preview.name.text(), "song.mp3")
        self.assertEqual(preview.state.text(), "Keep")
        self.assertEqual(preview.size.text(), "2.00 KB")
        self.assertEqual(preview.md5.text(), "filehash")
        self.assertEqual(preview.audio_md5.text(), "audiohash")
        app.processEvents()


if __name__ == "__main__":
    unittest.main()
