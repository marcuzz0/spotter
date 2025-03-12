###############################################################################
# IMPORT NECESSARI
###############################################################################
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QLineEdit, QFileDialog, QCheckBox, QListWidget, QListWidgetItem,
    QComboBox, QMessageBox, QTabWidget, QWidget, QProgressDialog, QSizePolicy
)
from qgis.PyQt.QtGui import QColor, QFont, QPixmap
from qgis.PyQt.QtCore import QVariant, Qt, pyqtSignal
from qgis.gui import QgsMapToolEmitPoint
from qgis.core import (
    QgsProject, QgsVectorLayer, QgsFeature, QgsFields, QgsField,
    QgsDefaultValue, QgsCoordinateTransform, QgsCoordinateReferenceSystem,
    QgsWkbTypes, QgsGeometry, QgsPointXY, QgsMessageLog, Qgis,
    QgsSnappingConfig, QgsTolerance, QgsVectorLayerSimpleLabeling,
    QgsPalLayerSettings, QgsTextFormat, QgsTextBufferSettings, QgsMarkerSymbol,
    QgsSingleSymbolRenderer
)
import csv
import os
import traceback
import logging

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

###############################################################################
# DIALOG PRINCIPALE CON 4 TAB:
#   1) Importa CSV
#   2) Esporta CSV
#   3) Importa DXF
#   4) Info
###############################################################################
class CombinedCsvDialog(QDialog):
    def __init__(self, iface):
        super().__init__()
        self.iface = iface  # Interfaccia di QGIS (di solito disponibile come variabile globale "iface")
        self.setWindowTitle("spotter")
        self.setFixedSize(600, 600)

        # Variabili per gestione CSV
        self.import_fields = []
        self.name_field = None
        self.x_field = None
        self.y_field = None

        # Variabili per gestione DXF
        self.dxf_path = None
        self.dxf_layer = None
        self.map_tool = None

        # Setup interfaccia
        self.initUI()
        self.connect_tab_signal()

        # Per mostrare eventuali progress bar di import/export
        self.progress_import = None
        self.progress_export = None

    def initUI(self):
        main_layout = QVBoxLayout()

        # TABS
        self.tabs = QTabWidget()

        # 1) TAB Import CSV
        self.import_tab = QWidget()
        self.init_import_tab()
        self.tabs.addTab(self.import_tab, "Importa CSV")

        # 2) TAB Export CSV
        self.export_tab = QWidget()
        self.init_export_tab()
        self.tabs.addTab(self.export_tab, "Esporta CSV")

        # 3) TAB Import DXF
        self.dxf_tab = QWidget()
        self.init_dxf_tab()
        self.tabs.addTab(self.dxf_tab, "Importa DXF")

        # 4) TAB Info
        self.info_tab = QWidget()
        self.init_info_tab()
        self.tabs.addTab(self.info_tab, "Info")

        main_layout.addWidget(self.tabs)
        self.setLayout(main_layout)

    def connect_tab_signal(self):
        """Collega eventuali segnali quando cambiamo tab."""
        self.tabs.currentChanged.connect(self.on_tab_changed)

    ############################################################################
    #                               TAB 1: IMPORTA CSV
    ############################################################################
    def init_import_tab(self):
        layout = QVBoxLayout()

        # Layout per la selezione del file CSV
        file_layout = QHBoxLayout()
        self.import_file_line_edit = QLineEdit()
        self.import_file_button = QPushButton("Scegli")
        self.import_file_button.clicked.connect(self.import_select_file)
        self.import_file_button.setFixedWidth(80)

        file_layout.addWidget(QLabel("File CSV:"))
        file_layout.addWidget(self.import_file_line_edit)
        file_layout.addWidget(self.import_file_button)
        layout.addSpacing(10)
        layout.addLayout(file_layout)
        layout.addSpacing(10)

        # Layout per il nome del layer
        layer_name_layout = QHBoxLayout()
        self.layer_name_line_edit = QLineEdit()
        self.layer_name_line_edit.setPlaceholderText("Inserisci nome per il layer temporaneo")
        layer_name_layout.addWidget(QLabel("Nome Layer:"))
        layer_name_layout.addWidget(self.layer_name_line_edit)
        layout.addLayout(layer_name_layout)
        layout.addSpacing(10)

        # Checkbox per l'intestazione del CSV
        self.import_header_checkbox = QCheckBox("Il file CSV ha l'intestazione (header)")
        self.import_header_checkbox.setChecked(True)
        self.import_header_checkbox.stateChanged.connect(self.import_load_fields)
        layout.addWidget(self.import_header_checkbox)
        layout.addSpacing(8)

        # Lista dei campi da includere
        layout.addWidget(QLabel("Seleziona i campi da includere: (sono obbligatori i campi Nome, Latitudine e Longitudine)"))
        self.import_fields_list_widget = QListWidget()
        self.import_fields_list_widget.setSelectionMode(QListWidget.MultiSelection)
        self.import_fields_list_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self.import_fields_list_widget)
        layout.addSpacing(10)

        # Selezione dei campi di coordinate e nome
        coord_layout = QHBoxLayout()
        self.import_name_field_combo = QComboBox()
        self.import_x_field_combo = QComboBox()
        self.import_y_field_combo = QComboBox()
        coord_layout.addWidget(QLabel("Campo nome:"))
        coord_layout.addWidget(self.import_name_field_combo)
        coord_layout.addWidget(QLabel("Campo lat(y):"))
        coord_layout.addWidget(self.import_y_field_combo)
        coord_layout.addWidget(QLabel("Campo lon(x):"))
        coord_layout.addWidget(self.import_x_field_combo)
        layout.addLayout(coord_layout)
        layout.addSpacing(10)

        # Pulsanti di import
        import_buttons_layout = QHBoxLayout()
        self.import_execute_button = QPushButton("Esegui")
        self.import_execute_button.clicked.connect(self.import_csv)
        self.import_execute_button.setEnabled(False)
        self.import_cancel_button = QPushButton("Annulla")
        self.import_cancel_button.clicked.connect(self.close_dialog)
        import_buttons_layout.addStretch()
        import_buttons_layout.addWidget(self.import_execute_button)
        import_buttons_layout.addWidget(self.import_cancel_button)
        layout.addLayout(import_buttons_layout)
        layout.addSpacing(10)

        # Istruzioni
        edit_instructions = QLabel(
            "<br>"
            "<b>Istruzioni per l'editing:</b><br>"
            "1. Dopo l'importazione, il layer temporaneo sarà aggiunto al progetto<br>"
            "2. Seleziona il layer nella legenda di QGIS<br>"
            "3. Utilizza lo strumento 'Aggiungi Punti' per aggiungere nuovi punti<br>"
            "4. Una volta terminato, clicca su 'Salva modifiche' per salvare le modifiche"
        )
        edit_instructions.setWordWrap(True)
        edit_instructions.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        layout.addWidget(edit_instructions)

        self.import_tab.setLayout(layout)

    def import_select_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Seleziona il file CSV", "", "CSV files (*.csv)")
        if file_path:
            self.import_file_line_edit.setText(file_path)
            self.import_load_fields()

    def import_load_fields(self):
        self.import_fields_list_widget.clear()
        self.import_x_field_combo.clear()
        self.import_y_field_combo.clear()
        self.import_name_field_combo.clear()

        file_path = self.import_file_line_edit.text()
        if not file_path:
            return

        header = self.import_header_checkbox.isChecked()
        try:
            with open(file_path, 'r', encoding='cp1252') as csvfile:
                reader = csv.reader(csvfile)
                first_line = next(reader)
                if header:
                    fields = first_line
                else:
                    num_fields = len(first_line)
                    fields = [f"field_{i+1}" for i in range(num_fields)]
                self.import_fields = fields

                csvfile.seek(0)
                if not header:
                    next(reader, None)

                for field in fields:
                    item = QListWidgetItem(field)
                    item.setSelected(True)
                    self.import_fields_list_widget.addItem(item)
                    self.import_name_field_combo.addItem(field)
                    self.import_x_field_combo.addItem(field)
                    self.import_y_field_combo.addItem(field)

                self.import_header_checkbox.stateChanged.disconnect(self.import_load_fields)

                if not header:
                    if len(fields) >= 1:
                        self.import_name_field_combo.setCurrentIndex(0)
                    if len(fields) >= 3:
                        self.import_y_field_combo.setCurrentIndex(1)
                        self.import_x_field_combo.setCurrentIndex(2)
                    for i in range(len(fields)):
                        item = self.import_fields_list_widget.item(i)
                        if item:
                            item.setSelected(True)
                else:
                    self.import_name_field_combo.setEnabled(True)

                self.import_header_checkbox.stateChanged.connect(self.import_load_fields)
                self.import_execute_button.setEnabled(True)

                logging.info("Campi importati correttamente.")
        except Exception as e:
            QMessageBox.critical(self, "Errore", f"Errore nel leggere il file CSV: {e}")
            self.import_execute_button.setEnabled(False)
            logging.error(f"Errore nel leggere il file CSV: {e}")

    def import_csv(self):
        file_path = self.import_file_line_edit.text()
        if not file_path:
            QMessageBox.warning(self, "Errore", "Nessun file selezionato.")
            return

        layer_name = self.layer_name_line_edit.text().strip()
        if not layer_name:
            QMessageBox.warning(self, "Errore", "Inserisci un nome per il layer temporaneo.")
            return

        existing_layers = QgsProject.instance().mapLayersByName(layer_name)
        if existing_layers:
            QMessageBox.warning(self, "Errore", f"Un layer con il nome '{layer_name}' esiste già. Scegli un altro nome.")
            return

        header = self.import_header_checkbox.isChecked()
        selected_items = self.import_fields_list_widget.selectedItems()
        selected_fields = [item.text() for item in selected_items]

        if len(selected_fields) < 3:
            QMessageBox.warning(self, "Errore", "Devi selezionare almeno tre campi, inclusi Nome, Latitudine e Longitudine.")
            return

        self.name_field = self.import_name_field_combo.currentText()
        self.x_field = self.import_x_field_combo.currentText()
        self.y_field = self.import_y_field_combo.currentText()

        mandatory_fields = [self.name_field, self.x_field, self.y_field]
        missing_fields = [field for field in mandatory_fields if field not in selected_fields]
        if missing_fields:
            QMessageBox.warning(self, "Errore", f"Devi selezionare i campi: {', '.join(missing_fields)}.")
            return

        # Costruzione URI per il CSV
        uri = f"file:///{file_path}?type=csv&detectTypes=yes&xField={self.x_field}&yField={self.y_field}&crs=EPSG:4326&encoding=cp1252"
        if not header:
            uri += "&useHeader=no"
            field_names = ','.join(selected_fields)
            uri += f"&fieldNames={field_names}"

        csv_layer = QgsVectorLayer(uri, layer_name, "delimitedtext")
        if not csv_layer.isValid():
            QMessageBox.warning(self, "Errore", "Layer non valido. Controlla il file CSV e i parametri.")
            logging.error("Layer CSV non valido.")
            return

        # Creazione layer in memoria come Point
        mem_layer = QgsVectorLayer("Point?crs=EPSG:4326", layer_name, "memory")
        mem_provider = mem_layer.dataProvider()

        # Costruzione dei campi
        fields = QgsFields()
        for field_name in selected_fields:
            field_index = csv_layer.fields().indexFromName(field_name)
            if field_index == -1:
                QMessageBox.warning(self, "Errore", f"Il campo '{field_name}' non esiste nel layer CSV.")
                logging.warning(f"Campo mancante: {field_name}")
                return
            field = csv_layer.fields().field(field_index)
            if not header and field_name.startswith('field_'):
                new_field = QgsField(field_name, QVariant.String)
            else:
                new_field = QgsField(field.name(), field.type(), field.typeName())
            fields.append(new_field)
        mem_provider.addAttributes(fields)
        mem_layer.updateFields()

        total_features = csv_layer.featureCount()
        if total_features == 0:
            QMessageBox.warning(self, "Errore", "Il layer CSV non contiene alcuna feature.")
            logging.warning("Layer CSV vuoto.")
            return

        # Barra di progresso e controllo delle feature con coordinate non valide
        self.progress_import = QProgressDialog("Importazione delle feature...", "Annulla", 0, total_features, self)
        self.progress_import.setWindowModality(Qt.WindowModal)
        self.progress_import.setMinimumDuration(0)
        self.progress_import.show()

        processed_features = 0
        invalid_features = 0  # Contatore per feature con coordinate non valide
        try:
            for feat in csv_layer.getFeatures():
                if self.progress_import.wasCanceled():
                    QMessageBox.information(self, "Interrotto", "L'importazione è stata interrotta dall'utente.")
                    logging.info("Importazione interrotta dall'utente.")
                    self.progress_import.close()
                    return
                # Estrai e verifica i valori di latitudine e longitudine
                lat_val = feat.attribute(self.y_field)
                lon_val = feat.attribute(self.x_field)
                try:
                    lat = float(lat_val)
                    lon = float(lon_val)
                except Exception:
                    invalid_features += 1
                    continue  # Salta la feature se i valori non sono numerici

                if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
                    invalid_features += 1
                    continue  # Salta la feature se le coordinate non sono nel range

                new_feat = QgsFeature()
                new_feat.setGeometry(feat.geometry())
                attr_values = [feat.attribute(field_name) for field_name in selected_fields]
                new_feat.setAttributes(attr_values)
                mem_provider.addFeature(new_feat)
                processed_features += 1
                self.progress_import.setValue(processed_features)
        except Exception as e:
            QMessageBox.critical(self, "Errore", f"Errore durante l'importazione delle feature: {e}")
            logging.error(f"Errore durante l'importazione delle feature: {e}")
            self.progress_import.close()
            return

        self.progress_import.setValue(total_features)
        self.progress_import.close()

        # Se sono state trovate feature con coordinate non valide, annulla l'importazione (il layer non viene creato)
        if invalid_features > 0:
            QMessageBox.warning(self, "Attenzione", f"Sono state trovate {invalid_features} feature con coordinate non valide. Importazione annullata.")
            return

        mem_layer.updateExtents()

        # Imposta default value per X e Y se presenti
        if self.x_field and self.y_field:
            x_idx = mem_layer.fields().indexFromName(self.x_field)
            y_idx = mem_layer.fields().indexFromName(self.y_field)
            if x_idx != -1:
                mem_layer.setDefaultValueDefinition(x_idx, QgsDefaultValue('round($x, 8)'))
            if y_idx != -1:
                mem_layer.setDefaultValueDefinition(y_idx, QgsDefaultValue('round($y, 8)'))

        QgsProject.instance().addMapLayer(mem_layer)

        # Salviamo alcune informazioni personalizzate
        mem_layer.setCustomProperty('import_name_field', self.name_field)
        mem_layer.setCustomProperty('import_x_field', self.x_field)
        mem_layer.setCustomProperty('import_y_field', self.y_field)
        mem_layer.setCustomProperty('has_header', header)

        self.iface.setActiveLayer(mem_layer)

        # Etichettatura automatica se il campo nome esiste
        if self.name_field in mem_layer.fields().names():
            label_settings = QgsPalLayerSettings()
            label_settings.fieldName = self.name_field
            label_settings.enabled = True

            text_format = QgsTextFormat()
            text_format.setFont(QFont("Noto Sans", 12))
            text_format.setSize(12)

            buffer_settings = QgsTextBufferSettings()
            buffer_settings.setEnabled(True)
            buffer_settings.setSize(2)
            buffer_settings.setColor(QColor(255, 255, 255))
            text_format.setBuffer(buffer_settings)

            label_settings.setFormat(text_format)
            labeling = QgsVectorLayerSimpleLabeling(label_settings)
            mem_layer.setLabelsEnabled(True)
            mem_layer.setLabeling(labeling)
        else:
            QMessageBox.warning(self, "Errore", f"Il campo '{self.name_field}' non esiste nel layer.")
            logging.warning(f"Campo nome '{self.name_field}' mancante nel layer.")

        # Stile base punto rosso
        symbol = QgsMarkerSymbol.createSimple({'name': 'circle', 'color': '255,0,0', 'size': '2.5'})
        mem_layer.setRenderer(QgsSingleSymbolRenderer(symbol))

        mem_layer.startEditing()
        mem_layer.triggerRepaint()

        QMessageBox.information(self, "Successo", f"Layer temporaneo '{layer_name}' creato ed editabile con successo!")
        logging.info(f"Layer temporaneo '{layer_name}' creato con successo.")

        # Aggiorno la lista dei layer per l'export
        self.populate_export_layers()

    ############################################################################
    #                               TAB 2: ESPORTA CSV
    ############################################################################
    def init_export_tab(self):
        layout = QVBoxLayout()

        # Selezione del layer da esportare
        layer_selection_layout = QVBoxLayout()
        layer_label = QLabel("Seleziona il layer vettoriale:")
        self.export_layer_list_widget = QListWidget()
        self.populate_export_layers()
        self.export_layer_list_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.export_layer_list_widget.setFixedHeight(100)

        layer_selection_layout.addWidget(layer_label)
        layer_selection_layout.addWidget(self.export_layer_list_widget)
        layout.addLayout(layer_selection_layout)
        layout.addSpacing(10)

        # Checkbox header
        self.export_header_checkbox = QCheckBox("Esporta intestazione (header)")
        self.export_header_checkbox.setChecked(True)
        layout.addWidget(self.export_header_checkbox)
        layout.addSpacing(8)
        
        # Seleziona campi da esportare
        field_selection_layout = QVBoxLayout()
        fields_label = QLabel("Seleziona i campi da esportare:")
        self.export_fields_list_widget = QListWidget()
        self.export_fields_list_widget.setSelectionMode(QListWidget.MultiSelection)
        self.export_fields_list_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.export_fields_list_widget.setFixedHeight(110)

        field_selection_layout.addWidget(fields_label)
        field_selection_layout.addWidget(self.export_fields_list_widget)
        layout.addLayout(field_selection_layout)
        layout.addSpacing(10)

        # Selezione CRS
        crs_selection_layout = QHBoxLayout()
        crs_label = QLabel("Seleziona CRS di uscita per il CSV:")
        self.export_crs_combo = QComboBox()
        crs_list = [
            ("EPSG:4326 - WGS 84", "EPSG:4326"),
            ("EPSG:3857 - WGS 84 / Pseudo-Mercator", "EPSG:3857"),
            ("EPSG:3003 - Monte Mario / Italy zone 1", "EPSG:3003"),
            ("EPSG:3004 - Monte Mario / Italy zone 2", "EPSG:3004"),
            ("EPSG:6707 - RDN2008 / UTM zone 32N (N-E)", "EPSG:6707"),
            ("EPSG:6708 - RDN2008 / UTM zone 33N (N-E)", "EPSG:6708")
        ]
        for crs_name, crs_code in crs_list:
            self.export_crs_combo.addItem(crs_name, crs_code)
        crs_selection_layout.addWidget(crs_label)
        crs_selection_layout.addWidget(self.export_crs_combo)
        self.export_crs_combo.setFixedWidth(300)
        layout.addLayout(crs_selection_layout)
        layout.addSpacing(10)

        # Pulsanti di export
        export_buttons_layout = QHBoxLayout()
        self.export_execute_button = QPushButton("Esegui")
        self.export_execute_button.clicked.connect(self.export_to_csv)
        self.export_cancel_button = QPushButton("Annulla")
        self.export_cancel_button.clicked.connect(self.close_dialog)
        self.export_execute_button.setFixedWidth(80)
        self.export_cancel_button.setFixedWidth(80)

        export_buttons_layout.addStretch()
        export_buttons_layout.addWidget(self.export_execute_button)
        export_buttons_layout.addWidget(self.export_cancel_button)
        layout.addLayout(export_buttons_layout)
        layout.addSpacing(10)

        # Istruzioni
        export_instructions = QLabel(
            "<br>"
            "<b>Istruzioni per l'esportazione del file CSV:</b><br>"
            "1. Seleziona il layer da esportare<br>"
            "2. Seleziona se esportare o no l'intestazione<br>"
            "3. Seleziona i campi da includere nel CSV<br>"
            "4. Scegli il CRS di uscita e clicca su 'Esegui' per esportare il file CSV"
        )
        export_instructions.setWordWrap(True)
        export_instructions.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        layout.addWidget(export_instructions)

        self.export_tab.setLayout(layout)
        self.export_layer_list_widget.currentItemChanged.connect(self.export_load_fields)

    def populate_export_layers(self):
        """Popola la lista dei layer per la sezione 'Esporta CSV'."""
        if not hasattr(self, 'export_layer_list_widget'):
            return

        self.export_layer_list_widget.clear()
        layers = QgsProject.instance().mapLayers().values()
        for layer in layers:
            if isinstance(layer, QgsVectorLayer):
                item = QListWidgetItem(layer.name())
                item.setData(Qt.UserRole, layer.id())
                self.export_layer_list_widget.addItem(item)

    def export_load_fields(self):
        self.export_fields_list_widget.clear()
        current_item = self.export_layer_list_widget.currentItem()
        if not current_item:
            return
        layer_id = current_item.data(Qt.UserRole)
        layer = QgsProject.instance().mapLayer(layer_id)
        if not layer or not layer.isValid():
            QMessageBox.warning(self, "Errore", f"Il layer '{current_item.text()}' non esiste più.")
            self.export_layer_list_widget.takeItem(self.export_layer_list_widget.row(current_item))
            return

        for field in layer.fields():
            item = QListWidgetItem(field.name())
            item.setSelected(True)
            self.export_fields_list_widget.addItem(item)

    def export_to_csv(self):
        current_item = self.export_layer_list_widget.currentItem()
        if not current_item:
            QMessageBox.warning(self, "Errore", "Seleziona un layer vettoriale.")
            return

        layer_id = current_item.data(Qt.UserRole)
        layer = QgsProject.instance().mapLayer(layer_id)
        if not layer or not layer.isValid():
            QMessageBox.warning(self, "Errore", f"Il layer '{current_item.text()}' non esiste più.")
            return

        x_field = layer.customProperty('import_x_field')
        y_field = layer.customProperty('import_y_field')
        name_field = layer.customProperty('import_name_field')

        selected_items = self.export_fields_list_widget.selectedItems()
        selected_fields = [item.text() for item in selected_items]
        if not selected_fields:
            QMessageBox.warning(self, "Errore", "Devi selezionare almeno un campo.")
            return

        export_headers = self.export_header_checkbox.isChecked()
        crs_code = self.export_crs_combo.currentData()
        if not crs_code:
            QMessageBox.warning(self, "Errore", "Seleziona un CRS di uscita.")
            return
        target_crs = QgsCoordinateReferenceSystem(crs_code)
        if not target_crs.isValid():
            QMessageBox.warning(self, "Errore", f"CRS '{crs_code}' non valido.")
            return

        file_path, _ = QFileDialog.getSaveFileName(self, "Esporta in CSV", "", "CSV files (*.csv)")
        if not file_path:
            return
        if not file_path.lower().endswith('.csv'):
            file_path += '.csv'

        transform = QgsCoordinateTransform(layer.crs(), target_crs, QgsProject.instance())
        is_epsg_4326 = (crs_code == "EPSG:4326")

        def format_number(value, decimals):
            try:
                val = float(value)
                return f"{val:.{decimals}f}"
            except:
                return str(value)

        def format_value(field_name, field_value):
            if field_value is None:
                return ""
            if name_field and field_name == name_field:
                return str(field_value)

            is_x_coord = (x_field is not None and field_name == x_field)
            is_y_coord = (y_field is not None and field_name == y_field)

            if is_x_coord or is_y_coord:
                # Coordinate
                if is_epsg_4326:
                    return format_number(field_value, 8)
                else:
                    return format_number(field_value, 3)
            else:
                # Campo generico
                return format_number(field_value, 3)

        # Header: se esporta l'header e il CRS non è EPSG:4326, sostituisce i nomi dei campi x e y con "est" e "nord"
        if export_headers:
            header_fields = [f for f in selected_fields]
            if not is_epsg_4326:
                header_fields = [("est" if f == x_field else "nord" if f == y_field else f) for f in header_fields]
        else:
            header_fields = None

        try:
            with open(file_path, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile, delimiter=',', quotechar='|', quoting=csv.QUOTE_NONE, escapechar='\\')
                if export_headers and header_fields:
                    writer.writerow(header_fields)

                for feat in layer.getFeatures():
                    geom = feat.geometry()
                    feat_x_val = None
                    feat_y_val = None
                    if geom and not geom.isEmpty():
                        geom.transform(transform)
                        if geom.type() == QgsWkbTypes.PointGeometry:
                            p = geom.asPoint()
                            feat_x_val = p.x()
                            feat_y_val = p.y()

                    row = []
                    for f in selected_fields:
                        val = feat[f]
                        if f == x_field and feat_x_val is not None:
                            val = feat_x_val
                        if f == y_field and feat_y_val is not None:
                            val = feat_y_val

                        formatted_val = format_value(f, val)
                        row.append(formatted_val)

                    writer.writerow(row)

            QMessageBox.information(self, "Successo", "Esportazione CSV completata con successo.")
            logging.info(f"Esportazione CSV completata: {file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Errore", f"Errore durante l'esportazione: {e}")
            logging.error(f"Errore durante l'esportazione: {e}")

    ############################################################################
    #                          TAB 3: IMPORTA DXF
    ############################################################################
    def init_dxf_tab(self):
        layout = QVBoxLayout()

        # Selezione file DXF
        file_layout = QHBoxLayout()
        self.dxf_file_line_edit = QLineEdit()
        self.select_dxf_button = QPushButton("Seleziona File DXF")
        self.select_dxf_button.clicked.connect(self.select_dxf)

        file_layout.addWidget(QLabel("File DXF:"))
        file_layout.addWidget(self.dxf_file_line_edit)
        file_layout.addWidget(self.select_dxf_button)
        layout.addLayout(file_layout)

        layout.addSpacing(1)

        # Label di stato
        self.dxf_status_label = QLabel("Nessun file selezionato")
        layout.addWidget(self.dxf_status_label)
        layout.addSpacing(1)

        # Pulsante di posizionamento
        self.place_dxf_button = QPushButton("Posiziona DXF sulla Mappa")
        self.place_dxf_button.setEnabled(False)
        self.place_dxf_button.clicked.connect(self.start_placing_dxf)
        layout.addWidget(self.place_dxf_button)
        layout.addSpacing(270)

        # Istruzioni
        info_label = QLabel(
            "<b>Istruzioni per l'importazione del file DXF:</b><br>"
            "1. Seleziona il file DXF (solo linee o poligoni)<br>"
            "2. Se tutte le geometrie sono valide, si abilita il pulsante<br>"
            "3. Clicca su 'Posiziona DXF sulla Mappa' e poi clicca sul canvas QGIS<br>"
            "4. Verrà creato un layer in memoria con il file DXF"
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        self.dxf_tab.setLayout(layout)

    def select_dxf(self):
        path, _ = QFileDialog.getOpenFileName(self, "Seleziona il file DXF", "", "DXF Files (*.dxf)")
        if not path:
            self.dxf_file_line_edit.setText("")
            self.dxf_status_label.setText("Nessun file selezionato.")
            self.place_dxf_button.setEnabled(False)
            self.dxf_layer = None
            return

        self.dxf_path = path
        self.dxf_file_line_edit.setText(path)
        self.dxf_status_label.setText(f"File selezionato: {os.path.basename(path)}")

        # Carica layer DXF in modo temporaneo (senza aggiungerlo al progetto)
        temp_dxf_layer = QgsVectorLayer(path, "DXF_Temp", "ogr")
        if not temp_dxf_layer.isValid():
            QMessageBox.critical(self, "Errore", "Errore durante l'importazione del DXF.")
            self.place_dxf_button.setEnabled(False)
            self.dxf_layer = None
            return

        # Verifica linee/poligoni
        total_features = 0
        invalid_geometries = 0
        for feat in temp_dxf_layer.getFeatures():
            total_features += 1
            geom = feat.geometry()
            if not geom:
                invalid_geometries += 1
                continue
            topo = QgsWkbTypes.geometryType(geom.wkbType())
            if topo not in [QgsWkbTypes.LineGeometry, QgsWkbTypes.PolygonGeometry]:
                invalid_geometries += 1

        if invalid_geometries > 0:
            QMessageBox.warning(
                self,
                "Geometrie Non Supportate",
                f"Il file DXF contiene {invalid_geometries} geometrie non valide su un totale di {total_features}.\n"
                "Solo linee e poligoni sono supportati"
            )
            self.place_dxf_button.setEnabled(False)
            self.dxf_layer = None
        else:
            self.dxf_layer = temp_dxf_layer
            self.place_dxf_button.setEnabled(True)

    def start_placing_dxf(self):
        if not self.dxf_layer:
            QMessageBox.warning(self, "Avviso", "Nessun layer DXF valido disponibile")
            return

        # Imposta CRS del progetto al layer
        crs_project = QgsProject.instance().crs()
        self.dxf_layer.setCrs(crs_project)

        # Abilita snapping (facoltativo)
        snapping_config = QgsSnappingConfig()
        snapping_config.setEnabled(True)
        snapping_config.setType(QgsSnappingConfig.Vertex)
        snapping_config.setTolerance(10)
        snapping_config.setUnits(QgsTolerance.Pixels)
        QgsProject.instance().setSnappingConfig(snapping_config)

        # Crea map tool personalizzato per il clic
        self.map_tool = DXFMapTool(self.iface.mapCanvas(), self.dxf_layer)
        self.map_tool.pointClicked.connect(self.place_dxf_on_map)
        self.iface.mapCanvas().setMapTool(self.map_tool)

        QMessageBox.information(self, "Istruzioni", "Clicca sulla mappa nel punto in cui vuoi posizionare il DXF.")

    def place_dxf_on_map(self, qgs_point_xy):
        if not self.dxf_layer:
            QMessageBox.warning(self, "Errore", "Nessun layer DXF disponibile.")
            return

        extent = self.dxf_layer.extent()
        origin_x = extent.xMinimum()
        origin_y = extent.yMinimum()

        dx = qgs_point_xy.x() - origin_x
        dy = qgs_point_xy.y() - origin_y
        print(f"Traslazione: dx={dx}, dy={dy}")

        # Prima feature per determinare se line o polygon
        first_feat = next(self.dxf_layer.getFeatures(), None)
        if not first_feat:
            QMessageBox.critical(self, "Errore", "DXF vuoto, nessuna geometria")
            return

        topo = QgsWkbTypes.geometryType(first_feat.geometry().wkbType())
        if topo == QgsWkbTypes.LineGeometry:
            geometry_string = "LineString"
        elif topo == QgsWkbTypes.PolygonGeometry:
            geometry_string = "Polygon"
        else:
            QMessageBox.critical(self, "Errore", "Tipo di geometria non supportato")
            return

        crs_auth_id = self.dxf_layer.crs().authid()
        memory_layer = QgsVectorLayer(f"{geometry_string}?crs={crs_auth_id}", "DXF_Posizionato", "memory")
        provider = memory_layer.dataProvider()

        # Copia campi
        fields = self.dxf_layer.fields()
        provider.addAttributes(fields.toList())
        memory_layer.updateFields()

        # Trasla feature
        for feat in self.dxf_layer.getFeatures():
            geom = feat.geometry()
            if not geom:
                continue
            geom.translate(dx, dy)
            new_feat = QgsFeature()
            new_feat.setFields(fields)
            new_feat.setAttributes(feat.attributes())
            new_feat.setGeometry(geom)
            provider.addFeature(new_feat)
        
        memory_layer.updateExtents()
        QgsProject.instance().addMapLayer(memory_layer)

        # Stile rosso semplice
        renderer_symbol = memory_layer.renderer().symbol()
        renderer_symbol.setColor(QColor(255, 0, 0))
        memory_layer.triggerRepaint()

        QMessageBox.information(self, "Completato", "DXF posizionato correttamente sulla mappa")

        # Riporta eventuali tool di digitalizzazione
        self.iface.actionAddFeature().trigger()
        self.iface.mapCanvas().refresh()

        # Scollega e disabilita map tool
        self.iface.mapCanvas().unsetMapTool(self.map_tool)
        self.map_tool = None

    ############################################################################
    #                               TAB 4: INFO
    ############################################################################
    def init_info_tab(self):
        layout = QVBoxLayout()

        # Informazioni sul plugin
        info_label = QLabel(
            "<p><b>Versione:</b> 1.0.0 del 28 febbraio 2025</p>"
            "<p><b>Autore:</b> <a href='mailto:severinmarco@gmail.com'>marcuzz0</a></p>"
            "<p><b>Codice:</b> <a href='https://github.com/marcuzz0/spotter'>Github repository</a></p>"
            "<p><b>Supporta:</b> puoi fare una donazione per supportare il progetto da  <a href='https://ko-fi.com/marcuzz0'>qui</a></p>"
            "<p><b>Licenza:</b> spotter viene distribuito sotto licenza <a href='https://github.com/marcuzz0/spotter/blob/main/LICENSE'>GPL-3.0 license</a></p>"
            "<p><b>Descrizione:</b> Il plugin spotter è uno strumento per QGIS progettato per semplificare il flusso di lavoro relativo all'importazione ed esportazione di dati geografici, focalizzandosi in particolare su file CSV e DXF</p>"
        )
        info_label.setOpenExternalLinks(True)
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        # Aggiungere il logo del plugin (se presente)
        icon_path = os.path.join(os.path.dirname(__file__), "icon.png")
        if os.path.exists(icon_path):
            logo_label = QLabel()
            logo_label.setPixmap(QPixmap(icon_path).scaled(200, 200, Qt.KeepAspectRatio))
            logo_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(logo_label)

        self.info_tab.setLayout(layout)

    ############################################################################
    #        METODI GENERICI / GESTIONE TAB / CHIUSURA
    ############################################################################
    def on_tab_changed(self, index):
        tab_name = self.tabs.tabText(index)
        if tab_name == "Esporta CSV":
            self.populate_export_layers()

    def close_dialog(self):
        reply = QMessageBox.question(
            self, 'Conferma', 'Vuoi chiudere la finestra?',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.close()


###############################################################################
# MAP TOOL PER IL CLIC SULLA MAPPA (PER IL DXF)
###############################################################################
class DXFMapTool(QgsMapToolEmitPoint):
    pointClicked = pyqtSignal(QgsPointXY)

    def __init__(self, canvas, layer):
        super().__init__(canvas)
        self.canvas = canvas
        self.layer = layer

    def canvasReleaseEvent(self, event):
        pt = self.toMapCoordinates(event.pos())
        self.pointClicked.emit(QgsPointXY(pt))
        # Se desideri disabilitare subito il map tool, puoi farlo qui:
        # self.canvas.unsetMapTool(self)


###############################################################################
# FUNZIONE DI AVVIO DELLA FINESTRA DI DIALOGO
###############################################################################
dialog_ref = None

def run_dialog():
    global dialog_ref
    # 'iface' deve essere disponibile (in QGIS lo è di default)
    dialog_ref = CombinedCsvDialog(iface)
    dialog_ref.show()

