from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                             QLineEdit, QPushButton, QCheckBox, QFormLayout)

class SettingsDialog(QDialog):
    def __init__(self, settings_manager, parent=None):
        super().__init__(parent)
        self.sm = settings_manager
        self.setWindowTitle("QuillAI Settings")
        self.setFixedWidth(450)
        self.setStyleSheet("background-color: #252526; color: #CCCCCC;")

        layout = QVBoxLayout(self)
        form = QFormLayout()

        # Input Fields
        self.local_url = QLineEdit(self.sm.get("local_llm_url"))
        self.cloud_url = QLineEdit(self.sm.get("cloud_llm_url"))
        self.api_key = QLineEdit(self.sm.get("cloud_api_key"))
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.model_name = QLineEdit(self.sm.get("active_model"))

        # Checkbox for Toggle
        self.use_cloud = QCheckBox("Use Cloud for Chat (OpenAI style)")
        self.use_cloud.setChecked(self.sm.get("use_cloud_for_chat"))

        # Add to form
        form.addRow("Local LLM URL:", self.local_url)
        form.addRow("Cloud API URL:", self.cloud_url)
        form.addRow("Cloud API Key:", self.api_key)
        form.addRow("Model Name:", self.model_name)
        form.addRow(self.use_cloud)

        layout.addLayout(form)

        # Buttons
        btns = QHBoxLayout()
        save_btn = QPushButton("Save Settings")
        save_btn.clicked.connect(self.save_and_close)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)

        btns.addWidget(save_btn)
        btns.addWidget(cancel_btn)
        layout.addLayout(btns)

    def save_and_close(self):
        self.sm.set("local_llm_url", self.local_url.text())
        self.sm.set("cloud_llm_url", self.cloud_url.text())
        self.sm.set("cloud_api_key", self.api_key.text())
        self.sm.set("active_model", self.model_name.text())
        self.sm.set("use_cloud_for_chat", self.use_cloud.isChecked())
        self.accept()
