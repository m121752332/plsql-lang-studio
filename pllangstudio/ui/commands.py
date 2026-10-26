"""可復原的編輯步驟（見 ADR-0010：整批算一個步驟）。"""

from PySide6.QtGui import QUndoCommand


class EditCommand(QUndoCommand):
    def __init__(self, model, edits: list[tuple[int, str, str]], label: str):
        super().__init__(f"{label}（{len(edits)} 個字串）")
        self.model = model
        self.edits = edits  # (列, 修改前, 修改後)

    def redo(self):
        self.model.apply_texts([(i, new) for i, _old, new in self.edits])

    def undo(self):
        self.model.apply_texts([(i, old) for i, old, _new in reversed(self.edits)])
