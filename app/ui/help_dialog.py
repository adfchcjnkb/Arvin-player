
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QScrollArea, QWidget, QComboBox, QFrame, QSizePolicy, QPushButton
)

from app.utils import resource_path, APP_TITLE, APP_VERSION, APP_AUTHOR
from app.i18n import (
    LANGUAGES, LANGUAGE_ORDER, HELP_SECTIONS, HELP_CONTENT,
    UI_STRINGS, tr,
)


class HelpDialog(QDialog):

    def __init__(self, theme: dict, language: str, font_loader=None, parent=None):
        super().__init__(parent)
        self.theme = theme
        self.language = language if language in LANGUAGES else "en_US"
        self.font_loader = font_loader
        self.setWindowTitle(f"{APP_TITLE} — {self._help_about_text(self.language)}")
        self.resize(880, 560)
        self._build_ui()
        self._apply_theme()
        self._set_language(self.language)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        header = QHBoxLayout()
        self.header_label = QLabel()
        self.header_label.setObjectName("helpHeader")
        header.addWidget(self.header_label)
        header.addStretch()

        lang_label = QLabel("🌐")
        header.addWidget(lang_label)

        self.lang_combo = QComboBox()
        for code in LANGUAGE_ORDER:
            self.lang_combo.addItem(LANGUAGES[code]["native"], code)
        if self.font_loader:
            for i in range(self.lang_combo.count()):
                code = self.lang_combo.itemData(i)
                font = self.font_loader(code)
                if font:
                    self.lang_combo.setItemData(i, font, Qt.ItemDataRole.FontRole)
        self.lang_combo.currentIndexChanged.connect(self._on_language_changed)
        header.addWidget(self.lang_combo)
        root.addLayout(header)

        self.about_label = QLabel(f"{APP_TITLE} v{APP_VERSION} — {APP_AUTHOR}")
        self.about_label.setObjectName("aboutBlock")
        root.addWidget(self.about_label)

        body = QHBoxLayout()
        body.setSpacing(12)

        self.section_list = QListWidget()
        self.section_list.setMinimumWidth(120)
        self.section_list.setMaximumWidth(220)
        self.section_list.currentRowChanged.connect(self._show_section)
        body.addWidget(self.section_list)

        self.scroll = QScrollArea()
        self.scroll.setObjectName("helpScroll")
        self.scroll.setWidgetResizable(True)
        self.content_holder = QWidget()
        self.content_holder.setObjectName("helpContent")
        self.content_layout = QVBoxLayout(self.content_holder)
        self.content_layout.setContentsMargins(20, 10, 20, 20)
        self.content_layout.setSpacing(12)

        self.title_label = QLabel()
        self.title_label.setObjectName("helpTitle")
        self.title_label.setWordWrap(True)
        self.content_layout.addWidget(self.title_label)

        self.body_label = QLabel()
        self.body_label.setObjectName("helpBody")
        self.body_label.setWordWrap(True)
        self.content_layout.addWidget(self.body_label)

        self.content_layout.addStretch()
        self.scroll.setWidget(self.content_holder)
        body.addWidget(self.scroll, 1)

        root.addLayout(body)

        close_row = QHBoxLayout()
        close_row.addStretch()
        self.close_btn = QPushButton()
        self.close_btn.clicked.connect(self.accept)
        close_row.addWidget(self.close_btn)
        root.addLayout(close_row)

    def _apply_theme(self):
        t = self.theme
        self.setStyleSheet(f"""
            QDialog {{ background: {t['bg_primary']}; }}
            #helpHeader {{ color: {t['accent_primary']}; font-size: 16px; font-weight: bold; }}
            QListWidget {{
                background: {t['bg_card']}; color: {t['text_primary']};
                border: 1px solid {t['border']}; border-radius: 6px;
                padding: 4px;
            }}
            QListWidget::item {{ padding: 8px 6px; border-radius: 4px; }}
            QListWidget::item:selected {{ background: {t['accent_primary']}; color: white; }}
            #helpScroll {{ background: {t['bg_card']}; border: 1px solid {t['border']}; border-radius: 6px; }}
            #helpScroll > QWidget > QWidget {{ background: {t['bg_card']}; }}
            #helpContent {{ background: {t['bg_card']}; }}
            #helpTitle {{ color: {t['text_primary']}; font-size: 18px; font-weight: bold; background: transparent; }}
            #helpBody {{ color: {t['text_secondary']}; font-size: 13px; line-height: 150%; background: transparent; }}
            #aboutBlock {{ color: {t['text_secondary']}; font-size: 12px; }}
            QComboBox {{
                background: {t['input_bg']}; color: {t['text_primary']};
                border: 1px solid {t['input_border']}; border-radius: 5px; padding: 3px 8px;
            }}
            QComboBox QAbstractItemView {{
                background: {t['bg_card']}; color: {t['text_primary']};
                border: 1px solid {t['border']};
                selection-background-color: {t['accent_primary']}; selection-color: white;
                outline: none;
            }}
            QPushButton {{
                background: {t['button_bg']}; color: {t['text_primary']};
                border: 1px solid {t['border']}; border-radius: 5px; padding: 6px 18px;
            }}
            QPushButton:hover {{ background: {t['accent_primary']}; color: white; }}
        """)

    def _on_language_changed(self, _idx):
        code = self.lang_combo.currentData()
        if code:
            self._set_language(code)

    def _set_language(self, language: str):
        self.language = language
        meta = LANGUAGES[language]
        is_rtl = meta["rtl"]
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft if is_rtl else Qt.LayoutDirection.LeftToRight)

        self._apply_font(language)

        idx = self.lang_combo.findData(language)
        if idx >= 0 and self.lang_combo.currentIndex() != idx:
            self.lang_combo.blockSignals(True)
            self.lang_combo.setCurrentIndex(idx)
            self.lang_combo.blockSignals(False)

        self.setWindowTitle(f"{APP_TITLE} — {self._help_about_text(language)}")
        self.header_label.setText(f"{APP_TITLE} — {self._help_about_text(language)}")
        self.close_btn.setText(self._close_text(language))

        self.section_list.blockSignals(True)
        self.section_list.clear()
        for sec_id in HELP_SECTIONS:
            item = QListWidgetItem(self._bidi_fix(self._section(language, sec_id)["title"]))
            item.setData(Qt.ItemDataRole.UserRole, sec_id)
            self.section_list.addItem(item)
        self.section_list.blockSignals(False)

        if self.section_list.count():
            self.section_list.setCurrentRow(0)
            self._show_section(0)

    def _apply_font(self, language):
        if not self.font_loader:
            return
        font = self.font_loader(language)
        if not font:
            return
        self._language_font = QFont(font)
        self.setFont(self._language_font)
        for child in self.findChildren(QWidget):
            sized = QFont(self._language_font)
            existing = child.font()
            if existing.pointSize() > 0:
                sized.setPointSize(existing.pointSize())
            sized.setBold(existing.bold())
            child.setFont(sized)
        style = self.style()
        for child in self.findChildren(QWidget):
            style.unpolish(child)
            style.polish(child)
            child.update()
            child.updateGeometry()
        self.updateGeometry()
        self.update()

    @staticmethod
    def _help_about_text(language):
        titles = {
            "en_US": "Help & About", "zh_CN": "帮助与关于", "es_ES": "Ayuda y Acerca de",
            "hi_IN": "सहायता और परिचय", "ar_SA": "المساعدة وحول البرنامج",
            "pt_BR": "Ajuda e Sobre", "fr_FR": "Aide et À propos",
            "ru_RU": "Справка и о программе", "de_DE": "Hilfe & Über",
            "ja_JP": "ヘルプとこのアプリについて", "tr_TR": "Yardım ve Hakkında",
            "ko_KR": "도움말 및 정보", "it_IT": "Guida e Informazioni",
            "id_ID": "Bantuan & Tentang", "fa_IR": "راهنما و درباره برنامه",
        }
        return titles.get(language, "Help & About")

    @staticmethod
    def _close_text(language):
        closes = {
            "en_US": "Close", "zh_CN": "关闭", "es_ES": "Cerrar", "hi_IN": "बंद करें",
            "ar_SA": "إغلاق", "pt_BR": "Fechar", "fr_FR": "Fermer", "ru_RU": "Закрыть",
            "de_DE": "Schließen", "ja_JP": "閉じる", "tr_TR": "Kapat", "ko_KR": "닫기",
            "it_IT": "Chiudi", "id_ID": "Tutup", "fa_IR": "بستن",
        }
        return closes.get(language, "Close")

    def _bidi_fix(self, text: str) -> str:
        if LANGUAGES.get(self.language, {}).get("rtl") and text:
            return "\u200f" + text
        return text

    def _show_section(self, row: int):
        if row < 0:
            return
        item = self.section_list.item(row)
        if not item:
            return
        sec_id = item.data(Qt.ItemDataRole.UserRole)
        content = self._section(self.language, sec_id)
        self.title_label.setText(self._bidi_fix(content["title"]))
        self.body_label.setText(self._bidi_fix(content["body"]))

    @staticmethod
    def _section(language, sec_id):
        lang_map = HELP_CONTENT.get(language, {})
        if sec_id in lang_map:
            return lang_map[sec_id]
        return HELP_CONTENT["en_US"][sec_id]
