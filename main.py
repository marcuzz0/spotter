###############################################################################
# IMPORT NECESSARI
###############################################################################
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QLineEdit, QFileDialog, QCheckBox, QListWidget, QListWidgetItem,
    QComboBox, QMessageBox, QTabWidget, QWidget, QProgressDialog, QSizePolicy,
    QColorDialog, QInputDialog
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
    QgsSingleSymbolRenderer, QgsRuleBasedLabeling
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
        self.setFixedSize(600, 700)
        
        # Configura le flag della finestra
        self.setWindowFlags(
            Qt.Window |                 # Finestra normale
            Qt.WindowTitleHint |        # Mostra la barra del titolo
            Qt.WindowSystemMenuHint |   # Menu di sistema
            Qt.WindowMinimizeButtonHint | # Pulsante minimizza
            Qt.WindowCloseButtonHint |  # Pulsante chiudi
            Qt.WindowMaximizeButtonHint  # Pulsante massimizza
        )
        
        # Assicura che la finestra non sia modale (non blocca altre finestre)
        self.setWindowModality(Qt.NonModal)

        # Variabili per gestione CSV
        self.import_fields = []
        self.name_field = None
        self.x_field = None
        self.y_field = None
        # import_dms_format now comes from combo box

        # Variabili per gestione DXF
        self.dxf_path = None
        self.dxf_layer = None
        self.map_tool = None
        
        # Variabile per gestione etichette
        self.labels_enabled = True  # Abilitato di default
        
        # Variabile per il colore dei punti
        self.point_color = QColor(255, 0, 0)  # Rosso di default
        self.line_color = QColor(20, 181, 255)  # #14b5ff di default
        self.polygon_color = QColor(0, 255, 0)  # #00ff00 di default
        
        # Colori per i testi
        self.name_text_color = QColor(0, 0, 0)  # Nero di default
        self.elevation_text_color = QColor(255, 0, 255)  # Magenta di default (#ff00ff)
        
        # Colori di default per nuovi layer (non modificati dal rilevamento)
        self.default_name_text_color = QColor(0, 0, 0)  # Nero
        self.default_elevation_text_color = QColor(255, 0, 255)  # Magenta (#ff00ff)
        
        # Variabili per gestione quote
        self.elevation_map_tool = None
        self.selected_elevation_field = None
        self.label_type = "name"  # Tipo di etichetta da mostrare: name, elevation
        
        # Dizionario per tenere traccia delle connessioni ai layer
        self.layer_connections = {}

        # Setup interfaccia
        self.initUI()
        self.connect_tab_signal()
        
        # Abilita snap di default all'avvio
        self.enable_snap_on_startup()
        
        # Recupera il campo quota dai layer esistenti all'avvio
        self.initialize_elevation_field()
        
        # Rileva colori e impostazioni dai layer esistenti
        self.detect_existing_settings()
        
        # Connetti al segnale di cambio layer attivo
        self.iface.layerTreeView().currentLayerChanged.connect(self.on_active_layer_changed)
        
        # Connetti al segnale di rimozione layer per aggiornare automaticamente la lista export
        QgsProject.instance().layersRemoved.connect(self.on_layers_removed)

        # Per mostrare eventuali progress bar di import/export
        self.progress_import = None
        self.progress_export = None
        
        # Abilita drag and drop
        self.setAcceptDrops(True)
        logging.info("Drag and drop abilitato per la finestra principale")

    def initUI(self):
        main_layout = QVBoxLayout()

        # TABS
        self.tabs = QTabWidget()
        self.tabs.setAcceptDrops(False)  # Disabilita per il tab widget per non interferire

        # 1) TAB Import CSV
        self.import_tab = QWidget()
        self.init_import_tab()
        self.tabs.addTab(self.import_tab, "Importa CSV")

        # 2) TAB Export CSV
        self.export_tab = QWidget()
        self.init_export_tab()
        self.export_tab_index = self.tabs.addTab(self.export_tab, "Esporta CSV")
        self.tabs.setTabEnabled(self.export_tab_index, True)  # Abilitato di default

        # 3) TAB Gestione (spostato dopo Export)
        self.dxf_tab = QWidget()
        self.init_dxf_tab()
        self.dxf_tab_index = self.tabs.addTab(self.dxf_tab, "Gestione")
        self.tabs.setTabEnabled(self.dxf_tab_index, True)  # Abilitato di default
        
        # 4) TAB About
        self.info_tab = QWidget()
        self.init_info_tab()
        self.tabs.addTab(self.info_tab, "About")

        main_layout.addWidget(self.tabs)
        self.setLayout(main_layout)
        
        # Imposta la tab Importa CSV come attiva di default
        self.tabs.setCurrentIndex(0)  # Index 0 = Importa CSV
        
        # Inizializza i numeri progressivi al primo numero disponibile
        self.initialize_progressive_numbers()

    def initialize_progressive_numbers(self):
        """Inizializza i campi numerici con il primo numero progressivo disponibile"""
        max_num = self.find_max_point_number()
        next_num = str(max_num + 1)
        self.start_vertex_number.setText(next_num)
        self.rename_start_number.setText(next_num)
        logging.info(f"Numeri progressivi inizializzati a: {next_num}")
    
    def detect_existing_settings(self):
        """Rileva colori e impostazioni dai layer esistenti nel progetto"""
        logging.info("Rilevamento impostazioni esistenti nel progetto...")
        
        # Rileva colori dei simboli dai layer esistenti
        for layer in QgsProject.instance().mapLayers().values():
            if layer.type() == QgsVectorLayer.VectorLayer:
                renderer = layer.renderer()
                if renderer and hasattr(renderer, 'symbol') and renderer.symbol():
                    symbol = renderer.symbol()
                    geometry_type = layer.geometryType()
                    
                    # Rileva colori in base al tipo di geometria
                    if geometry_type == QgsWkbTypes.PointGeometry and layer.customProperty('import_source') == 'csv':
                        # Layer punti CSV
                        self.point_color = symbol.color()
                        logging.info(f"Colore punti rilevato da {layer.name()}: {self.point_color.name()}")
                    elif geometry_type == QgsWkbTypes.LineGeometry and layer.customProperty('is_dxf_layer'):
                        # Layer linee DXF
                        self.line_color = symbol.color()
                        logging.info(f"Colore linee rilevato da {layer.name()}: {self.line_color.name()}")
                    elif geometry_type == QgsWkbTypes.PolygonGeometry and layer.customProperty('is_dxf_layer'):
                        # Layer poligoni DXF
                        if symbol.symbolLayer(0):
                            self.polygon_color = symbol.symbolLayer(0).strokeColor()
                            logging.info(f"Colore poligoni rilevato da {layer.name()}: {self.polygon_color.name()}")
        
        # Rileva colori e tipo etichette
        self.detect_label_settings()
        
        # Aggiorna i pulsanti dei colori
        self.update_color_button()
        self.update_line_color_button()
        self.update_polygon_color_button()
        self.update_name_text_color_button()
        self.update_elevation_text_color_button()
    
    def detect_label_settings(self):
        """Rileva le impostazioni delle etichette dai layer esistenti"""
        # Prima controlla il layer attivo
        active_layer = self.iface.activeLayer()
        if (active_layer and 
            active_layer.type() == QgsVectorLayer.VectorLayer and 
            active_layer.customProperty('import_source') == 'csv' and
            active_layer.labelsEnabled() and active_layer.labeling()):
            
            self.process_layer_labels(active_layer)
        
        # Se non abbiamo trovato tutto dal layer attivo, cerca in tutti i layer
        if (self.name_text_color == self.default_name_text_color or 
            self.elevation_text_color == self.default_elevation_text_color):
            for layer in QgsProject.instance().mapLayers().values():
                if (layer.type() == QgsVectorLayer.VectorLayer and 
                    layer.customProperty('import_source') == 'csv' and
                    layer.labelsEnabled() and layer.labeling()):
                    self.process_layer_labels(layer)
                    # Se abbiamo trovato entrambi i colori, possiamo fermarci
                    if (self.name_text_color != self.default_name_text_color and 
                        self.elevation_text_color != self.default_elevation_text_color):
                        break
    
    def process_layer_labels(self, layer):
        """Processa le etichette di un singolo layer per estrarre colori e tipo"""
        labeling = layer.labeling()
        if hasattr(labeling, 'settings'):
            settings = labeling.settings()
            field_name = settings.fieldName
            text_format = settings.format()
            
            # Rileva il tipo di etichetta
            elevation_field = layer.customProperty('import_elevation_field')
            name_field = layer.customProperty('import_name_field')
            
            if elevation_field and field_name == elevation_field:
                self.label_type = "elevation"
                self.elevation_text_color = text_format.color()
                logging.info(f"Rilevato tipo etichetta: quota, colore: {self.elevation_text_color.name()}")
            elif name_field and field_name == name_field:
                self.label_type = "name"
                self.name_text_color = text_format.color()
                logging.info(f"Rilevato tipo etichetta: nome, colore: {self.name_text_color.name()}")
            elif 'concat(' in field_name and '<span style' in field_name:
                self.label_type = "both"
                # Estrai i colori dall'HTML
                import re
                color_matches = re.findall(r'color:\s*([^;"}]+)', field_name)
                if len(color_matches) >= 2:
                    elevation_color = QColor(color_matches[0])
                    name_color = QColor(color_matches[1])
                    if elevation_color.isValid():
                        self.elevation_text_color = elevation_color
                    if name_color.isValid():
                        self.name_text_color = name_color
                logging.info(f"Rilevato tipo etichetta: both, colori: quota={self.elevation_text_color.name()}, nome={self.name_text_color.name()}")
            
            # Rileva se le etichette sono abilitate
            self.labels_enabled = layer.labelsEnabled()
            
            # Aggiorna il combo box del tipo etichetta
            if hasattr(self, 'label_type_combo'):
                index = self.label_type_combo.findData(self.label_type)
                if index >= 0:
                    self.label_type_combo.setCurrentIndex(index)
            
            # Aggiorna il checkbox delle etichette
            if hasattr(self, 'labels_checkbox'):
                self.labels_checkbox.setChecked(self.labels_enabled)
    
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

        # Layout per EPSG input allineato a sinistra (prima di tutto)
        epsg_layout = QHBoxLayout()
        epsg_label = QLabel("EPSG input:")
        epsg_label.setFixedWidth(80)  # Stessa larghezza di "Nome Layer:"
        epsg_layout.addWidget(epsg_label)
        
        self.import_crs_combo = QComboBox()
        self.import_crs_combo.addItem("EPSG:4326 - WGS84", "EPSG:4326")
        self.import_crs_combo.addItem("EPSG:6707 - RDN2008 / UTM 32N", "EPSG:6707")
        self.import_crs_combo.addItem("EPSG:6708 - RDN2008 / UTM 33N", "EPSG:6708")
        self.import_crs_combo.addItem("Altro CRS...", "custom")
        self.import_crs_combo.currentIndexChanged.connect(self.on_import_crs_changed)
        self.import_crs_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        epsg_layout.addWidget(self.import_crs_combo)
        
        layout.addLayout(epsg_layout)
        layout.addSpacing(15)
        
        # Layout orizzontale per checkbox header e DMS
        checkbox_layout = QHBoxLayout()
        
        # Checkbox per l'intestazione del CSV
        self.import_header_checkbox = QCheckBox("Il file CSV ha l'intestazione (header)")
        self.import_header_checkbox.setChecked(True)
        self.import_header_checkbox.stateChanged.connect(self.import_load_fields)
        checkbox_layout.addWidget(self.import_header_checkbox)
        
        # Aggiungi spazio elastico per spostare gli elementi DMS a destra
        checkbox_layout.addStretch()
        
        # Checkbox per coordinate sessagesimali
        self.import_dms_checkbox = QCheckBox("Coordinate sessagesimali")
        self.import_dms_checkbox.setChecked(False)  # Disabilitato di default
        checkbox_layout.addWidget(self.import_dms_checkbox)
        
        # ComboBox per formato DMS nella stessa riga
        checkbox_layout.addWidget(QLabel("Formato:"))
        self.import_dms_format_combo = QComboBox()
        self.import_dms_format_combo.addItem("DD° MM' SS.ss\" N", "standard")
        self.import_dms_format_combo.addItem("DD MM SS.ss N", "spaces")
        self.import_dms_format_combo.addItem("DD:MM:SS.ss N", "colons")
        self.import_dms_format_combo.addItem("DDdMMmSS.sss", "letters")
        self.import_dms_format_combo.setEnabled(self.import_dms_checkbox.isChecked())
        self.import_dms_checkbox.stateChanged.connect(
            lambda state: self.import_dms_format_combo.setEnabled(state == Qt.Checked)
        )
        self.import_dms_format_combo.setMinimumWidth(150)  # Imposta larghezza minima
        checkbox_layout.addWidget(self.import_dms_format_combo)
        
        layout.addLayout(checkbox_layout)
        layout.addSpacing(15)  # Reduced spacing

        # Lista dei campi da includere
        layout.addWidget(QLabel("Seleziona i campi da includere: (sono obbligatori i campi del nome e delle geometrie)"))
        self.import_fields_list_widget = QListWidget()
        self.import_fields_list_widget.setSelectionMode(QListWidget.MultiSelection)
        self.import_fields_list_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.import_fields_list_widget.setFixedHeight(250)
        layout.addWidget(self.import_fields_list_widget)
        layout.addSpacing(10)  # Reduced spacing

        # Selezione dei campi di coordinate e nome
        coord_layout = QHBoxLayout()
        self.import_name_field_combo = QComboBox()
        self.import_name_field_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.import_y_field_combo = QComboBox()
        self.import_y_field_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.import_x_field_combo = QComboBox()
        self.import_x_field_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.import_elevation_field_combo = QComboBox()
        self.import_elevation_field_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        
        coord_layout.addWidget(QLabel("Nome:"))
        coord_layout.addWidget(self.import_name_field_combo)
        self.import_y_label = QLabel("Lat:")  # Default corretto per EPSG:4326
        coord_layout.addWidget(self.import_y_label)
        coord_layout.addWidget(self.import_y_field_combo)
        self.import_x_label = QLabel("Lon:")  # Default corretto per EPSG:4326
        coord_layout.addWidget(self.import_x_label)
        coord_layout.addWidget(self.import_x_field_combo)
        coord_layout.addWidget(QLabel("Hei:"))
        coord_layout.addWidget(self.import_elevation_field_combo)
        layout.addLayout(coord_layout)
        layout.addSpacing(10)
        
        # Layout per il nome del layer
        layer_name_layout = QHBoxLayout()
        layer_name_label = QLabel("Nome Layer:")
        layer_name_label.setFixedWidth(80)  # Stessa larghezza degli altri label
        layer_name_layout.addWidget(layer_name_label)
        self.layer_name_line_edit = QLineEdit()
        self.layer_name_line_edit.setPlaceholderText("Inserisci nome per il layer temporaneo")
        layer_name_line_edit_widget = self.layer_name_line_edit
        layer_name_line_edit_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layer_name_layout.addWidget(layer_name_line_edit_widget)
        layout.addLayout(layer_name_layout)
        layout.addSpacing(10)
        
        # Pulsanti di import
        import_buttons_layout = QHBoxLayout()
        self.import_execute_button = QPushButton("Esegui")
        self.import_execute_button.clicked.connect(self.import_csv)
        self.import_execute_button.setEnabled(False)
        self.import_cancel_button = QPushButton("Annulla")
        self.import_cancel_button.clicked.connect(self.close_dialog)
        
        # Centro i pulsanti
        import_buttons_layout.addStretch()
        import_buttons_layout.addWidget(self.import_execute_button)
        import_buttons_layout.addWidget(self.import_cancel_button)
        import_buttons_layout.addStretch()
        
        layout.addLayout(import_buttons_layout)
        
        # Aggiungi spazio elastico per spingere le istruzioni in fondo
        layout.addStretch()
        
        # Istruzioni in fondo
        layout.addSpacing(10)
        edit_instructions = QLabel(
            "<b>Istruzioni per l'editing:</b><br>"
            "1. Dopo l'importazione, il layer temporaneo sarà aggiunto al progetto<br>"
            "2. Seleziona il layer nella legenda di QGIS<br>"
            "3. Utilizza lo strumento 'Aggiungi Punti' per aggiungere nuovi punti<br>"
            "4. Una volta terminato, clicca su 'Salva modifiche' per salvare le modifiche"
        )
        edit_instructions.setWordWrap(True)
        layout.addWidget(edit_instructions)
        layout.addSpacing(10)

        self.import_tab.setLayout(layout)

    def import_select_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Seleziona il file CSV", "", "CSV files (*.csv)")
        if file_path:
            self.import_file_line_edit.setText(file_path)
            # Aggiorna automaticamente il nome del layer con il nome del file
            base_name = os.path.splitext(os.path.basename(file_path))[0]
            self.layer_name_line_edit.setText(base_name)
            self.import_load_fields()

    def import_load_fields(self):
        logging.info(f"import_load_fields chiamato con percorso: {self.import_file_line_edit.text()}")
        
        # Pulisci le liste
        self.import_fields_list_widget.clear()
        self.import_x_field_combo.clear()
        self.import_y_field_combo.clear()
        self.import_name_field_combo.clear()
        self.import_elevation_field_combo.clear()
        self.import_elevation_field_combo.addItem("-- Nessuno --", None)
        self.import_execute_button.setEnabled(False)

        file_path = self.import_file_line_edit.text().strip()  # Rimuovi spazi extra
        if not file_path:
            logging.warning("Percorso file vuoto")
            return
        
        # Pulisci il percorso da eventuali prefissi file://
        if file_path.startswith('file:///'):
            file_path = file_path[8:]  # Rimuovi 'file:///' (8 caratteri)
        elif file_path.startswith('file://'):
            file_path = file_path[7:]  # Rimuovi 'file://' (7 caratteri)
            
        # Normalizza il percorso
        file_path = os.path.normpath(file_path)
        logging.info(f"Percorso normalizzato: '{file_path}'")
        logging.info(f"File esiste: {os.path.exists(file_path)}")
        logging.info(f"È un file: {os.path.isfile(file_path)}")
            
        # Verifica che il file esista
        if not os.path.exists(file_path) or not os.path.isfile(file_path):
            QMessageBox.warning(self, "Errore", f"File non trovato o non valido: {file_path}")
            logging.error(f"File non trovato o non valido: {file_path}")
            return

        header = self.import_header_checkbox.isChecked()
        
        # Prova diversi encoding comuni
        encodings = ['utf-8', 'cp1252', 'iso-8859-1', 'latin1', 'utf-8-sig']
        used_encoding = None
        
        for encoding in encodings:
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    # Prova a leggere tutto il file per verificare l'encoding
                    f.read()
                    used_encoding = encoding
                    logging.info(f"Encoding trovato: {encoding}")
                    break
            except (UnicodeDecodeError, UnicodeError):
                continue
                
        if not used_encoding:
            # Fallback: prova con errors='ignore'
            used_encoding = 'utf-8'
            logging.warning(f"Impossibile determinare l'encoding, uso utf-8 con errors='ignore'")
            
        try:
            # Apri il file con l'encoding trovato
            with open(file_path, 'r', encoding=used_encoding, errors='replace') as csvfile:
                reader = csv.reader(csvfile)
                first_line = next(reader)
                if header:
                    fields = first_line
                else:
                    num_fields = len(first_line)
                    fields = [f"field_{i+1}" for i in range(num_fields)]
                self.import_fields = fields
                logging.info(f"Campi trovati: {fields}")

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
                    self.import_elevation_field_combo.addItem(field)

                if not header:
                    if len(fields) >= 1:
                        self.import_name_field_combo.setCurrentIndex(0)
                    if len(fields) >= 3:
                        self.import_y_field_combo.setCurrentIndex(1)
                        self.import_x_field_combo.setCurrentIndex(2)
                    if len(fields) >= 4:
                        self.import_elevation_field_combo.setCurrentIndex(4)  # field_4 (0 è "-- Nessuno --")
                    for i in range(len(fields)):
                        item = self.import_fields_list_widget.item(i)
                        if item:
                            item.setSelected(True)
                else:
                    self.import_name_field_combo.setEnabled(True)
                    
                    # Cerca automaticamente i campi comuni
                    # 1. Campo nome
                    name_fields = ['nome', 'name', 'id', 'punto', 'point', 'numero', 'number', 'codice', 'code']
                    for i, field in enumerate(fields):
                        if field.lower() in name_fields:
                            self.import_name_field_combo.setCurrentIndex(i)
                            break
                    
                    # 2. Campi coordinate - dipende dal CRS selezionato
                    selected_crs = self.import_crs_combo.currentData()
                    if selected_crs and selected_crs != "custom":
                        crs = QgsCoordinateReferenceSystem(selected_crs)
                        if crs.isGeographic():
                            # Sistema geografico: cerca lat/lon
                            lat_fields = ['lat', 'latitudine', 'latitude', 'y']
                            lon_fields = ['lon', 'long', 'longitudine', 'longitude', 'x']
                            
                            for i, field in enumerate(fields):
                                if field.lower() in lat_fields:
                                    self.import_y_field_combo.setCurrentIndex(i)
                                    break
                            
                            for i, field in enumerate(fields):
                                if field.lower() in lon_fields:
                                    self.import_x_field_combo.setCurrentIndex(i)
                                    break
                        else:
                            # Sistema piano: cerca est/nord
                            est_fields = ['est', 'east', 'e', 'x', 'verso est']
                            nord_fields = ['nord', 'north', 'n', 'y', 'verso nord']
                            
                            for i, field in enumerate(fields):
                                if field.lower() in est_fields:
                                    self.import_x_field_combo.setCurrentIndex(i)
                                    break
                            
                            for i, field in enumerate(fields):
                                if field.lower() in nord_fields:
                                    self.import_y_field_combo.setCurrentIndex(i)
                                    break
                    
                    # 3. Campo quota
                    elevation_fields = ['hei', 'height', 'quota', 'elevation', 'z', 'alt', 'altitude', 'h']
                    for i, field in enumerate(fields):
                        if field.lower() in elevation_fields:
                            self.import_elevation_field_combo.setCurrentIndex(i + 1)  # +1 perché 0 è "-- Nessuno --"
                            break

                self.import_execute_button.setEnabled(True)

                logging.info("Campi importati correttamente.")
                    
        except Exception as e:
            import traceback
            QMessageBox.critical(self, "Errore", f"Errore nel leggere il file CSV: {e}")
            self.import_execute_button.setEnabled(False)
            logging.error(f"Errore nel leggere il file CSV: {e}")
            logging.error(traceback.format_exc())

    def on_import_crs_changed(self):
        """Gestisce il cambio di selezione del CRS"""
        current_data = self.import_crs_combo.currentData()
        current_text = self.import_crs_combo.currentText()
        
        # Se è stato selezionato un CRS con X per rimuoverlo
        if "✕" in current_text:
            # Disconnetti temporaneamente il segnale per evitare loop
            self.import_crs_combo.currentIndexChanged.disconnect()
            # Rimuovi l'elemento
            current_index = self.import_crs_combo.currentIndex()
            self.import_crs_combo.removeItem(current_index)
            self.import_crs_combo.setCurrentIndex(0)
            # Riconnetti il segnale
            self.import_crs_combo.currentIndexChanged.connect(self.on_import_crs_changed)
            return
        
        if current_data == "custom":
            # Disconnetti temporaneamente il segnale per evitare loop
            self.import_crs_combo.currentIndexChanged.disconnect()
            
            # Mostra il dialogo di selezione CRS di QGIS
            from qgis.gui import QgsProjectionSelectionDialog
            crs_dialog = QgsProjectionSelectionDialog(self)
            if crs_dialog.exec():
                selected_crs = crs_dialog.crs()
                # Aggiungi il CRS personalizzato al combo con X per rimozione
                index = self.import_crs_combo.count() - 1
                
                # Verifica che il CRS sia valido e abbia authid
                if selected_crs.isValid() and selected_crs.authid():
                    # Crea il testo per il combo
                    desc = selected_crs.description() if selected_crs.description() else "CRS Personalizzato"
                    auth_id = selected_crs.authid()
                    
                    # Se non c'è authid, prova a usare la descrizione o un fallback
                    if not auth_id:
                        auth_id = f"USER:{selected_crs.toProj()}" if selected_crs.toProj() else "USER:CUSTOM"
                    
                    # Controlla se questo CRS è già presente nella lista
                    already_exists = False
                    for i in range(self.import_crs_combo.count()):
                        if self.import_crs_combo.itemData(i) == auth_id:
                            already_exists = True
                            self.import_crs_combo.setCurrentIndex(i)
                            break
                    
                    if not already_exists:
                        text = f"{desc} ({auth_id})"
                        # Usa un carattere di riempimento speciale per spingere la X all'estrema destra
                        # Il carattere \u2007 è uno spazio di figura che mantiene la larghezza
                        padding = "\u2007" * 80  # Molti spazi per garantire che arrivi a destra
                        
                        # Inserisci l'elemento con l'authid come data
                        self.import_crs_combo.insertItem(
                            index, 
                            f"{text}{padding}✕", 
                            auth_id
                        )
                        self.import_crs_combo.setCurrentIndex(index)
                else:
                    # Se il CRS non è valido, mostra un avviso
                    QMessageBox.warning(self, "Avviso", "Il CRS selezionato non è valido")
                    self.import_crs_combo.setCurrentIndex(0)
                current_data = selected_crs.authid()
            else:
                # Se l'utente annulla, torna al primo elemento
                self.import_crs_combo.setCurrentIndex(0)
                current_data = "EPSG:4326"
            
            # Riconnetti il segnale
            self.import_crs_combo.currentIndexChanged.connect(self.on_import_crs_changed)
        
        # Aggiorna le etichette in base al tipo di CRS
        if current_data == "EPSG:4326":
            self.import_y_label.setText("Lat:")
            self.import_x_label.setText("Lon:")
            self.import_dms_checkbox.setEnabled(True)
        else:
            self.import_y_label.setText("Y/Nord:")
            self.import_x_label.setText("X/Est:")
            self.import_dms_checkbox.setEnabled(False)
            # Disconnetti temporaneamente per evitare di mostrare il dialog
            # Disable DMS checkbox when not in WGS84
            self.import_dms_checkbox.setChecked(False)

    
    def dms_to_decimal(self, dms_string):
        """Converte coordinate sessagesimali in decimali"""
        import re
        
        dms_str = str(dms_string).strip()
        
        # Pattern più flessibili per diversi formati DMS
        patterns = [
            # Formato: 45°30'15.5"N o 45° 30' 15.5" N
            r"([+-]?\d+)[°\s]+(\d+)['\s]+(\d+(?:\.\d+)?)[\"'\s]*([NSEW]?)",
            # Formato: 45 30 15.5 N
            r"([+-]?\d+)\s+(\d+)\s+(\d+(?:\.\d+)?)\s*([NSEW]?)",
            # Formato: 45:30:15.5N
            r"([+-]?\d+):(\d+):(\d+(?:\.\d+)?)\s*([NSEW]?)",
            # Formato: 45d30m15.5s
            r"([+-]?\d+)d\s*(\d+)m\s*(\d+(?:\.\d+)?)s?\s*([NSEW]?)",
        ]
        
        for pattern in patterns:
            match = re.match(pattern, dms_str, re.IGNORECASE)
            if match:
                degrees = float(match.group(1))
                minutes = float(match.group(2))
                seconds = float(match.group(3))
                direction = match.group(4).upper() if match.group(4) else ''
                
                # Calcola valore decimale
                decimal = abs(degrees) + minutes/60 + seconds/3600
                
                # Applica segno
                if degrees < 0:
                    decimal = -decimal
                elif direction in ['S', 'W']:
                    decimal = -decimal
                    
                return decimal
        
        # Se non matcha nessun pattern DMS, prova come decimale
        try:
            return float(dms_str)
        except:
            raise ValueError(f"Formato coordinate non valido: {dms_string}")
    
    def decimal_to_dms(self, decimal, is_longitude=False, format_type="standard"):
        """Converte coordinate decimali in sessagesimali con formato personalizzabile"""
        import math
        
        abs_decimal = abs(decimal)
        degrees = int(abs_decimal)
        minutes_decimal = (abs_decimal - degrees) * 60
        minutes = int(minutes_decimal)
        seconds = (minutes_decimal - minutes) * 60
        
        # Determina la direzione
        if is_longitude:
            direction = 'E' if decimal >= 0 else 'W'
        else:
            direction = 'N' if decimal >= 0 else 'S'
        
        # Applica il formato richiesto
        if format_type == "compact":
            return f"{degrees}°{minutes}'{seconds:.2f}\"{direction}"
        elif format_type == "spaces":
            return f"{degrees} {minutes} {seconds:.2f} {direction}"
        elif format_type == "colons":
            return f"{degrees}:{minutes:02d}:{seconds:05.2f} {direction}"
        elif format_type == "signed":
            sign = '-' if (decimal < 0) else '+'
            return f"{sign}{degrees}° {minutes}' {seconds:.2f}\""
        else:  # standard
            return f"{degrees}° {minutes}' {seconds:.2f}\" {direction}"

    def import_csv(self):
        file_path = self.import_file_line_edit.text().strip()
        if not file_path:
            QMessageBox.warning(self, "Errore", "Nessun file selezionato.")
            return
            
        # Pulisci il percorso da eventuali prefissi file://
        if file_path.startswith('file:///'):
            file_path = file_path[8:]  # Rimuovi 'file:///' (8 caratteri)
        elif file_path.startswith('file://'):
            file_path = file_path[7:]  # Rimuovi 'file://' (7 caratteri)
        
        # Normalizza il percorso
        file_path = os.path.normpath(file_path)

        layer_name = self.layer_name_line_edit.text().strip()
        if not layer_name:
            # Ask the user if they want to proceed without a name
            reply = QMessageBox.question(self, "Nome layer mancante", 
                                       "Non hai inserito un nome per il layer.\nVuoi utilizzare il nome del file come nome del layer?",
                                       QMessageBox.Yes | QMessageBox.No,
                                       QMessageBox.Yes)
            if reply == QMessageBox.No:
                self.layer_name_line_edit.setFocus()
                return
            else:
                # Use filename without extension as layer name
                layer_name = os.path.splitext(os.path.basename(file_path))[0]
                # Update the line edit with the generated name
                self.layer_name_line_edit.setText(layer_name)

        existing_layers = QgsProject.instance().mapLayersByName(layer_name)
        if existing_layers:
            reply = QMessageBox.question(self, "Layer esistente", 
                                       f"Un layer con il nome '{layer_name}' esiste già.\nVuoi sovrascriverlo?",
                                       QMessageBox.Yes | QMessageBox.No,
                                       QMessageBox.No)
            if reply == QMessageBox.No:
                return
            else:
                # Rimuovi il layer esistente
                for layer in existing_layers:
                    QgsProject.instance().removeMapLayer(layer)

        header = self.import_header_checkbox.isChecked()
        selected_items = self.import_fields_list_widget.selectedItems()
        selected_fields = [item.text() for item in selected_items]

        if len(selected_fields) < 3:
            QMessageBox.warning(self, "Errore", "Devi selezionare almeno tre campi, inclusi Nome, X e Y.")
            return

        self.name_field = self.import_name_field_combo.currentText()
        self.x_field = self.import_x_field_combo.currentText()
        self.y_field = self.import_y_field_combo.currentText()
        
        # Ottieni il campo elevazione selezionato
        elevation_field_text = self.import_elevation_field_combo.currentText()
        if elevation_field_text and elevation_field_text != "-- Nessuno --":
            self.selected_elevation_field = elevation_field_text
        else:
            self.selected_elevation_field = None

        mandatory_fields = [self.name_field, self.x_field, self.y_field]
        missing_fields = [field for field in mandatory_fields if field not in selected_fields]
        if missing_fields:
            QMessageBox.warning(self, "Errore", f"Devi selezionare i campi: {', '.join(missing_fields)}.")
            return

        # Ottieni il CRS selezionato
        selected_crs = self.import_crs_combo.currentData()
        if not selected_crs or selected_crs == "custom":
            selected_crs = "EPSG:4326"  # Default a WGS84
        
        # Costruzione URI per il CSV
        # Normalizza il percorso del file per essere sicuri che sia corretto
        normalized_path = os.path.abspath(file_path).replace('\\', '/')
        uri = f"file:///{normalized_path}?type=csv&detectTypes=yes&xField={self.x_field}&yField={self.y_field}&crs={selected_crs}&encoding=cp1252"
        if not header:
            uri += "&useHeader=no"
            field_names = ','.join(selected_fields)
            uri += f"&fieldNames={field_names}"

        csv_layer = QgsVectorLayer(uri, layer_name, "delimitedtext")
        if not csv_layer.isValid():
            QMessageBox.warning(self, "Errore", "Layer non valido. Controlla il file CSV e i parametri.")
            logging.error("Layer CSV non valido.")
            return

        # Se il CRS è geografico (4326), riproietta in Web Mercator (3857)
        # Altrimenti mantieni il CRS piano originale
        source_crs_obj = QgsCoordinateReferenceSystem(selected_crs)
        if source_crs_obj.isGeographic() or selected_crs == "EPSG:4326":
            target_crs = "EPSG:3857"
            logging.info(f"Riproiezione automatica da {selected_crs} a EPSG:3857 (Web Mercator)")
        else:
            target_crs = selected_crs
            logging.info(f"Mantenimento del CRS piano originale: {selected_crs}")
        
        # Creazione layer in memoria
        mem_layer = QgsVectorLayer(f"Point?crs={target_crs}", layer_name, "memory")
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
        self.progress_import.setWindowModality(Qt.WindowModal)  # Modal solo rispetto alla finestra di Spotter, non all'intera applicazione
        self.progress_import.setMinimumDuration(0)
        self.progress_import.show()

        # Prepara la trasformazione delle coordinate se necessario
        source_crs = QgsCoordinateReferenceSystem(selected_crs)
        dest_crs = QgsCoordinateReferenceSystem(target_crs)
        transform = None
        if source_crs != dest_crs:
            transform = QgsCoordinateTransform(source_crs, dest_crs, QgsProject.instance())
        
        processed_features = 0
        invalid_features = 0  # Contatore per feature con coordinate non valide
        try:
            for feat in csv_layer.getFeatures():
                if self.progress_import.wasCanceled():
                    QMessageBox.information(self, "Interrotto", "L'importazione è stata interrotta dall'utente.")
                    logging.info("Importazione interrotta dall'utente.")
                    self.progress_import.close()
                    return
                # Estrai e verifica i valori delle coordinate
                y_val = feat.attribute(self.y_field)
                x_val = feat.attribute(self.x_field)
                try:
                    # Se è abilitata la conversione DMS e siamo in WGS84
                    if self.import_dms_checkbox.isChecked() and selected_crs == "EPSG:4326":
                        y = self.dms_to_decimal(str(y_val))
                        x = self.dms_to_decimal(str(x_val))
                    else:
                        y = float(y_val)
                        x = float(x_val)
                except Exception:
                    invalid_features += 1
                    continue  # Salta la feature se i valori non sono numerici

                # Crea la geometria
                point = QgsPointXY(x, y)
                
                # Trasforma le coordinate se necessario
                if transform:
                    try:
                        point = transform.transform(point)
                    except Exception as e:
                        logging.warning(f"Errore nella trasformazione delle coordinate: {e}")
                        invalid_features += 1
                        continue
                
                # Verifica le coordinate PRIMA della trasformazione se sono in WGS84
                if selected_crs == "EPSG:4326" and not transform:
                    # Solo se NON c'è trasformazione, verifica i limiti WGS84
                    if not (-90 <= y <= 90) or not (-180 <= x <= 180):
                        invalid_features += 1
                        continue

                new_feat = QgsFeature()
                new_feat.setGeometry(QgsGeometry.fromPointXY(point))
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
            
            # Se abbiamo riproiettato da geografico a Web Mercator, 
            # dobbiamo trasformare le coordinate indietro al CRS originale per i campi
            if (source_crs_obj.isGeographic() or selected_crs == "EPSG:4326") and target_crs == "EPSG:3857":
                # Trasforma da 3857 back to original CRS (4326) per i campi
                if x_idx != -1:
                    mem_layer.setDefaultValueDefinition(x_idx, QgsDefaultValue(
                        f"round(x(transform($geometry, 'EPSG:3857', '{selected_crs}')), 8)"
                    ))
                if y_idx != -1:
                    mem_layer.setDefaultValueDefinition(y_idx, QgsDefaultValue(
                        f"round(y(transform($geometry, 'EPSG:3857', '{selected_crs}')), 8)"
                    ))
            else:
                # Per CRS piani, usa direttamente le coordinate
                if x_idx != -1:
                    mem_layer.setDefaultValueDefinition(x_idx, QgsDefaultValue(
                        "round(x($geometry), 8)"
                    ))
                if y_idx != -1:
                    mem_layer.setDefaultValueDefinition(y_idx, QgsDefaultValue(
                        "round(y($geometry), 8)"
                    ))
        
        # Imposta valore progressivo per il campo nome
        if self.name_field:
            name_idx = mem_layer.fields().indexFromName(self.name_field)
            if name_idx != -1:
                # Trova il numero massimo esistente
                max_num = 0
                for feat in mem_layer.getFeatures():
                    name_val = feat[self.name_field]
                    if name_val:
                        try:
                            # Prova a estrarre un numero dal nome
                            import re
                            name_str = str(name_val)
                            # Se il nome è solo un numero o inizia con un numero seguito da non-cifre
                            if name_str.isdigit():
                                num = int(name_str)
                                max_num = max(max_num, num)
                            else:
                                # Cerca un numero all'inizio della stringa
                                match = re.match(r'^(\d+)(?:\D|$)', name_str)
                                if match:
                                    num = int(match.group(1))
                                    max_num = max(max_num, num)
                        except:
                            pass
                
                # Imposta il valore predefinito come il prossimo numero progressivo
                # Usa aggregate per ottenere il massimo valore numerico esistente + 1
                expression = f"coalesce(array_max(array_foreach(array_agg(regexp_substr(\"{self.name_field}\", '[0-9]+')), to_int(@element))), 0) + 1"
                mem_layer.setDefaultValueDefinition(name_idx, QgsDefaultValue(expression))
        
        # Imposta valore di default 0 per il campo quota se presente
        if self.selected_elevation_field:
            elevation_idx = mem_layer.fields().indexFromName(self.selected_elevation_field)
            if elevation_idx != -1:
                mem_layer.setDefaultValueDefinition(elevation_idx, QgsDefaultValue('0'))

        QgsProject.instance().addMapLayer(mem_layer)

        # Salviamo alcune informazioni personalizzate
        mem_layer.setCustomProperty('import_source', 'csv')  # Marca il layer come importato da CSV
        mem_layer.setCustomProperty('import_name_field', self.name_field)
        mem_layer.setCustomProperty('import_x_field', self.x_field)
        mem_layer.setCustomProperty('import_y_field', self.y_field)
        mem_layer.setCustomProperty('has_header', header)
        mem_layer.setCustomProperty('original_crs', selected_crs)  # Memorizza il CRS originale
        if self.selected_elevation_field:
            mem_layer.setCustomProperty('import_elevation_field', self.selected_elevation_field)

        self.iface.setActiveLayer(mem_layer)
        
        # Riordina i layer: punti sopra, linee e poligoni sotto
        self.reorder_layers()

        # Etichettatura automatica se il campo nome esiste e le etichette sono abilitate
        if self.labels_enabled and self.name_field in mem_layer.fields().names():
            label_settings = QgsPalLayerSettings()
            
            # Configura l'espressione per l'etichetta basata sul tipo selezionato
            if self.label_type == "elevation" and self.selected_elevation_field and self.selected_elevation_field in mem_layer.fields().names():
                # Mostra solo la quota
                label_settings.fieldName = self.selected_elevation_field
            elif self.label_type == "both" and self.selected_elevation_field and self.selected_elevation_field in mem_layer.fields().names():
                # Mostra nome e quota in un'unica etichetta
                label_settings.isExpression = True
                # Usa spazi vuoti per creare separazione verticale tra quota e nome
                # Controlla se ci sono layer CSV esistenti per ereditare i colori
                existing_csv_layers = []
                for layer in QgsProject.instance().mapLayers().values():
                    if (layer.type() == QgsVectorLayer.VectorLayer and 
                        layer.customProperty('import_source') == 'csv'):
                        existing_csv_layers.append(layer)
                
                # Se ci sono layer CSV esistenti, usa i colori correnti invece dei default
                if existing_csv_layers:
                    elevation_color = self.elevation_text_color.name()
                    name_color = self.name_text_color.name()
                else:
                    # Solo se non ci sono layer CSV esistenti usa i colori di default
                    elevation_color = self.default_elevation_text_color.name()
                    name_color = self.default_name_text_color.name()
                    
                label_settings.fieldName = 'concat(\'<span style="color: {};">\', "{}", \'</span>\', \'<br>\', \'&nbsp;\', \'<br>\', \'<span style="color: {};">\', "{}", \'</span>\')'.format(elevation_color, self.selected_elevation_field, name_color, self.name_field)
            else:
                # Mostra solo il nome (default o quando label_type == "name")
                label_settings.fieldName = self.name_field
            
            label_settings.enabled = True
            
            # Non impostiamo placement per evitare errori di compatibilità
            # Le etichette saranno posizionate con le impostazioni di default di QGIS

            text_format = QgsTextFormat()
            text_format.setFont(QFont("Noto Sans", 12))
            text_format.setSize(12)
            
            # Controlla se ci sono layer CSV esistenti per ereditare i colori
            existing_csv_layers = []
            for layer in QgsProject.instance().mapLayers().values():
                if (layer.type() == QgsVectorLayer.VectorLayer and 
                    layer.customProperty('import_source') == 'csv'):
                    existing_csv_layers.append(layer)
            
            # Se ci sono layer CSV esistenti, usa i colori correnti invece dei default
            if existing_csv_layers:
                if self.label_type == "elevation":
                    text_format.setColor(self.elevation_text_color)
                elif self.label_type == "name":
                    text_format.setColor(self.name_text_color)
                elif self.label_type == "both":
                    # Per Nome+Quota usiamo HTML quindi non impostiamo il colore qui
                    text_format.setAllowHtmlFormatting(True)
            else:
                # Solo se non ci sono layer CSV esistenti usa i colori di default
                if self.label_type == "elevation":
                    text_format.setColor(self.default_elevation_text_color)
                elif self.label_type == "name":
                    text_format.setColor(self.default_name_text_color)
                elif self.label_type == "both":
                    # Per Nome+Quota usiamo HTML quindi non impostiamo il colore qui
                    text_format.setAllowHtmlFormatting(True)

            buffer_settings = QgsTextBufferSettings()
            buffer_settings.setEnabled(True)
            buffer_settings.setSize(2)
            buffer_settings.setColor(QColor(255, 255, 255))
            text_format.setBuffer(buffer_settings)

            label_settings.setFormat(text_format)
            
            labeling = QgsVectorLayerSimpleLabeling(label_settings)
            mem_layer.setLabelsEnabled(True)
            mem_layer.setLabeling(labeling)
        elif not self.labels_enabled:
            logging.info("Etichette disabilitate dalle impostazioni")
        elif self.name_field not in mem_layer.fields().names():
            QMessageBox.warning(self, "Errore", f"Il campo '{self.name_field}' non esiste nel layer.")
            logging.warning(f"Campo nome '{self.name_field}' mancante nel layer.")

        # Stile base punto con colore selezionato
        symbol = QgsMarkerSymbol.createSimple({
            'name': 'circle', 
            'color': f'{self.point_color.red()},{self.point_color.green()},{self.point_color.blue()}',
            'size': '2.5'
        })
        mem_layer.setRenderer(QgsSingleSymbolRenderer(symbol))

        # Non avviare automaticamente la modalità di modifica
        # mem_layer.startEditing()
        mem_layer.triggerRepaint()
        
        # Abilita i tab Esporta CSV e Gestione dopo importazione riuscita
        self.tabs.setTabEnabled(self.export_tab_index, True)
        self.tabs.setTabEnabled(self.dxf_tab_index, True)

        # Messaggio di successo con informazione sulla riproiezione
        source_crs_obj = QgsCoordinateReferenceSystem(selected_crs)
        if source_crs_obj.isGeographic() or selected_crs == "EPSG:4326":
            success_msg = f"Layer temporaneo '{layer_name}' creato con successo!\n\nIl layer è stato riproiettato da {selected_crs} a Web Mercator (EPSG:3857)."
        else:
            success_msg = f"Layer temporaneo '{layer_name}' creato con successo!\n\nCRS: {selected_crs}"
        
        QMessageBox.information(self, "Successo", success_msg)
        logging.info(f"Layer temporaneo '{layer_name}' creato con successo. CRS: {target_crs}")
        
        # Chiedi all'utente se vuole impostare una riproiezione OTF per il progetto
        reply = QMessageBox.question(self, "Riproiezione OTF", 
                                   "Vuoi impostare una riproiezione al volo (OTF) per il progetto?",
                                   QMessageBox.Yes | QMessageBox.No,
                                   QMessageBox.Yes)
        
        if reply == QMessageBox.Yes:
            # Mostra dialog per selezione CRS
            from qgis.gui import QgsProjectionSelectionDialog
            crs_dialog = QgsProjectionSelectionDialog(self)
            crs_dialog.setWindowTitle("Seleziona CRS per riproiezione OTF")
            
            # Suggerisci il CRS del layer appena importato
            crs_dialog.setCrs(mem_layer.crs())
            
            if crs_dialog.exec():
                selected_crs = crs_dialog.crs()
                if selected_crs.isValid():
                    # Imposta il CRS del progetto
                    QgsProject.instance().setCrs(selected_crs)
                    
                    # Abilita la riproiezione OTF
                    QgsProject.instance().writeEntry("SpatialRefSys", "ProjectionsEnabled", 1)
                    
                    # Refresh del canvas
                    self.iface.mapCanvas().refresh()
                    
                    QMessageBox.information(self, "Riproiezione OTF", 
                                          f"Riproiezione OTF impostata a: {selected_crs.description()}")
                    logging.info(f"Riproiezione OTF impostata a: {selected_crs.authid()}")

        # Aggiorno la lista dei layer per l'export
        self.populate_export_layers()

    ############################################################################
    #                               TAB 2: ESPORTA CSV
    ############################################################################
    def init_export_tab(self):
        layout = QVBoxLayout()
        
        # Aggiungi spazio iniziale come in Import CSV
        layout.addSpacing(10)

        # Selezione del layer da esportare
        layer_selection_layout = QVBoxLayout()
        layer_label = QLabel("Seleziona il layer:")
        self.export_layer_list_widget = QListWidget()
        self.populate_export_layers()
        self.export_layer_list_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.export_layer_list_widget.setFixedHeight(160)

        layer_selection_layout.addWidget(layer_label)
        layer_selection_layout.addWidget(self.export_layer_list_widget)
        layout.addLayout(layer_selection_layout)
        layout.addSpacing(15)

        # Layout per EPSG output allineato a sinistra (prima di tutto)
        epsg_layout = QHBoxLayout()
        epsg_layout.addWidget(QLabel("EPSG output:"))
        
        self.export_crs_combo = QComboBox()
        self.export_crs_combo.addItem("EPSG:4326 - WGS84", "EPSG:4326")
        self.export_crs_combo.addItem("EPSG:6707 - RDN2008 / UTM 32N", "EPSG:6707")
        self.export_crs_combo.addItem("EPSG:6708 - RDN2008 / UTM 33N", "EPSG:6708")
        self.export_crs_combo.addItem("Altro CRS...", "custom")
        self.export_crs_combo.currentIndexChanged.connect(self.on_export_crs_changed)
        self.export_crs_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        epsg_layout.addWidget(self.export_crs_combo)
        
        layout.addLayout(epsg_layout)
        layout.addSpacing(15)
        
        # Layout orizzontale per checkbox header e DMS (come in importa)
        checkbox_layout = QHBoxLayout()
        
        # Checkbox header
        self.export_header_checkbox = QCheckBox("Esporta intestazione (header)")
        self.export_header_checkbox.setChecked(True)
        checkbox_layout.addWidget(self.export_header_checkbox)
        
        # Aggiungi spazio elastico per spostare gli elementi DMS a destra
        checkbox_layout.addStretch()
        
        # Checkbox per coordinate sessagesimali
        self.export_dms_checkbox = QCheckBox("Coordinate sessagesimali")
        self.export_dms_checkbox.setChecked(False)  # Disabilitato di default
        self.export_crs_combo.currentIndexChanged.connect(self.on_export_crs_format_changed)
        checkbox_layout.addWidget(self.export_dms_checkbox)
        
        # ComboBox per formato DMS nella stessa riga
        checkbox_layout.addWidget(QLabel("Formato:"))
        self.export_dms_format_combo = QComboBox()
        self.export_dms_format_combo.addItem("DD° MM' SS.ss\" N", "standard")
        self.export_dms_format_combo.addItem("DD°MM'SS.ss\"N", "compact")
        self.export_dms_format_combo.addItem("DD MM SS.ss N", "spaces")
        self.export_dms_format_combo.addItem("DD:MM:SS.ss N", "colons")
        self.export_dms_format_combo.addItem("+DD° MM' SS.ss\"", "signed")
        self.export_dms_format_combo.setEnabled(self.export_dms_checkbox.isChecked())
        self.export_dms_checkbox.stateChanged.connect(
            lambda state: self.export_dms_format_combo.setEnabled(state == Qt.Checked)
        )
        self.export_dms_format_combo.setMinimumWidth(150)  # Imposta larghezza minima
        checkbox_layout.addWidget(self.export_dms_format_combo)
        
        layout.addLayout(checkbox_layout)
        layout.addSpacing(15)  # Reduced spacing
        
        # Seleziona campi da esportare
        field_selection_layout = QVBoxLayout()
        fields_label = QLabel("Seleziona i campi da esportare:")
        self.export_fields_list_widget = QListWidget()
        self.export_fields_list_widget.setSelectionMode(QListWidget.MultiSelection)
        self.export_fields_list_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.export_fields_list_widget.setFixedHeight(160)

        field_selection_layout.addWidget(fields_label)
        field_selection_layout.addWidget(self.export_fields_list_widget)
        layout.addLayout(field_selection_layout)
        layout.addSpacing(15)
        
        # Pulsanti di export
        export_buttons_layout = QHBoxLayout()
        self.export_execute_button = QPushButton("Esegui")
        self.export_execute_button.clicked.connect(self.export_to_csv)
        self.export_cancel_button = QPushButton("Annulla")
        self.export_cancel_button.clicked.connect(self.close_dialog)
        
        # Centro i pulsanti
        export_buttons_layout.addStretch()
        export_buttons_layout.addWidget(self.export_execute_button)
        export_buttons_layout.addWidget(self.export_cancel_button)
        export_buttons_layout.addStretch()
        
        layout.addLayout(export_buttons_layout)
        
        # Aggiungi spazio elastico per spingere le istruzioni in fondo
        layout.addStretch()
        
        # Istruzioni in fondo
        layout.addSpacing(15)
        export_instructions = QLabel(
            "<b>Istruzioni per l'esportazione del file CSV:</b><br>"
            "1. Seleziona il layer da esportare<br>"
            "2. Seleziona se esportare o no l'intestazione<br>"
            "3. Seleziona i campi da includere nel CSV<br>"
            "4. Scegli il CRS di uscita e clicca su 'Esegui' per esportare il file CSV"
        )
        export_instructions.setWordWrap(True)
        layout.addWidget(export_instructions)
        layout.addSpacing(10)

        self.export_tab.setLayout(layout)
        self.export_layer_list_widget.currentItemChanged.connect(self.export_load_fields)

    def on_export_crs_changed(self):
        """Gestisce il cambio di selezione del CRS in esportazione"""
        current_text = self.export_crs_combo.currentText()
        
        # Se è stato selezionato un CRS con X per rimuoverlo
        if "✕" in current_text:
            # Disconnetti temporaneamente il segnale per evitare loop
            self.export_crs_combo.currentIndexChanged.disconnect()
            # Rimuovi l'elemento
            current_index = self.export_crs_combo.currentIndex()
            self.export_crs_combo.removeItem(current_index)
            self.export_crs_combo.setCurrentIndex(0)
            # Riconnetti il segnale
            self.export_crs_combo.currentIndexChanged.connect(self.on_export_crs_changed)
            self.on_export_crs_format_changed()  # Aggiorna stato DMS
            return
            
        if self.export_crs_combo.currentData() == "custom":
            # Disconnetti temporaneamente il segnale per evitare loop
            self.export_crs_combo.currentIndexChanged.disconnect()
            
            # Mostra il dialogo di selezione CRS di QGIS
            from qgis.gui import QgsProjectionSelectionDialog
            crs_dialog = QgsProjectionSelectionDialog(self)
            if crs_dialog.exec():
                selected_crs = crs_dialog.crs()
                # Controlla se questo CRS è già presente nella lista
                auth_id = selected_crs.authid()
                already_exists = False
                for i in range(self.export_crs_combo.count()):
                    if self.export_crs_combo.itemData(i) == auth_id:
                        already_exists = True
                        self.export_crs_combo.setCurrentIndex(i)
                        break
                
                if not already_exists:
                    # Aggiungi il CRS personalizzato al combo con X per rimozione
                    index = self.export_crs_combo.count() - 1
                    # Aggiungi spazi per allineare la X a destra
                    text = f"{selected_crs.description()} ({selected_crs.authid()})"
                    # Usa un carattere di riempimento speciale per spingere la X all'estrema destra
                    padding = "\u2007" * 80  # Molti spazi per garantire che arrivi a destra
                    self.export_crs_combo.insertItem(
                        index, 
                        f"{text}{padding}✕", 
                        auth_id
                    )
                    self.export_crs_combo.setCurrentIndex(index)
            else:
                # Se l'utente annulla, torna al primo elemento
                self.export_crs_combo.setCurrentIndex(0)
            
            # Riconnetti il segnale
            self.export_crs_combo.currentIndexChanged.connect(self.on_export_crs_changed)
        
        # Abilita/disabilita DMS checkbox
        self.on_export_crs_format_changed()

    def on_export_crs_format_changed(self):
        """Abilita/disabilita il checkbox DMS in base al CRS selezionato"""
        current_data = self.export_crs_combo.currentData()
        if current_data == "EPSG:4326":
            self.export_dms_checkbox.setEnabled(True)
        else:
            self.export_dms_checkbox.setEnabled(False)
            self.export_dms_checkbox.setChecked(False)

    def populate_export_layers(self):
        """Popola la lista dei layer per la sezione 'Esporta CSV'."""
        if not hasattr(self, 'export_layer_list_widget'):
            return

        self.export_layer_list_widget.clear()
        layers = QgsProject.instance().mapLayers().values()
        for layer in layers:
            if isinstance(layer, QgsVectorLayer):
                # Mostra solo i layer importati tramite CSV (che hanno le custom properties)
                if (layer.customProperty('import_x_field') and 
                    layer.customProperty('import_y_field') and 
                    layer.customProperty('import_name_field')):
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
        if not crs_code or crs_code == "custom":
            crs_code = "EPSG:4326"  # Default a WGS84
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
                    # Se è abilitato DMS e siamo in WGS84, converti in DMS
                    if self.export_dms_checkbox.isChecked():
                        format_type = self.export_dms_format_combo.currentData()
                        return self.decimal_to_dms(float(field_value), is_longitude=is_x_coord, format_type=format_type)
                    else:
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
        
        # Aggiungi spazio iniziale come in Import CSV
        layout.addSpacing(10)
        
        # SEZIONE IMPOSTAZIONI (spostata da Settings)
        # Layout orizzontale per checkbox finestra in primo piano e pulsante default
        top_layout = QHBoxLayout()
        
        # Checkbox per finestra sempre in primo piano
        self.stay_on_top_checkbox = QCheckBox("Finestra sempre in primo piano")
        self.stay_on_top_checkbox.setChecked(False)  # Disabilitato di default
        self.stay_on_top_checkbox.stateChanged.connect(self.on_stay_on_top_changed)
        top_layout.addWidget(self.stay_on_top_checkbox)
        
        # Spazio elastico per separare
        top_layout.addStretch()
        
        # Pulsante per ripristinare i default
        self.reset_defaults_button = QPushButton("Ripristina Default")
        self.reset_defaults_button.setToolTip("Ripristina tutte le impostazioni ai valori di fabbrica")
        self.reset_defaults_button.clicked.connect(self.reset_to_defaults)
        top_layout.addWidget(self.reset_defaults_button)
        
        layout.addLayout(top_layout)
        layout.addSpacing(10)
        
        # Checkbox per lo snap
        self.snap_checkbox = QCheckBox("Abilita snap")
        self.snap_checkbox.setChecked(True)  # Abilitato di default
        self.snap_checkbox.stateChanged.connect(self.on_snap_checkbox_changed)
        layout.addWidget(self.snap_checkbox)
        layout.addSpacing(15)
        
        # Layout per etichette con checkbox e combo
        labels_layout = QHBoxLayout()
        labels_layout.setContentsMargins(0, 0, 0, 0)
        
        # Checkbox per le etichette
        self.labels_checkbox = QCheckBox("Mostra etichette")
        self.labels_checkbox.setChecked(True)  # Abilitato di default
        self.labels_checkbox.stateChanged.connect(self.on_labels_checkbox_changed)
        labels_layout.addWidget(self.labels_checkbox)
        
        # ComboBox per tipo di etichetta
        self.label_type_combo = QComboBox()
        self.label_type_combo.addItem("Nome", "name")
        self.label_type_combo.addItem("Quota", "elevation")
        self.label_type_combo.addItem("Nome + Quota", "both")
        self.label_type_combo.setCurrentIndex(0)  # Nome di default
        self.label_type_combo.currentIndexChanged.connect(self.on_label_type_changed)
        self.label_type_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        labels_layout.addWidget(self.label_type_combo)
        
        layout.addLayout(labels_layout)
        layout.addSpacing(15)
        
        # Layout per tutti i colori in una riga
        colors_layout = QHBoxLayout()
        colors_layout.setContentsMargins(0, 0, 0, 0)
        
        # Label principale
        colors_label = QLabel("Vettori:")
        colors_label.setFixedWidth(50)
        colors_layout.addWidget(colors_label)
        
        # Punti
        colors_layout.addWidget(QLabel("Punti"))
        self.color_button = QPushButton()
        self.color_button.setMinimumWidth(60)
        self.color_button.setFixedHeight(25)
        self.update_color_button()
        self.color_button.clicked.connect(self.choose_point_color)
        colors_layout.addWidget(self.color_button, 1)  # stretch factor 1
        
        colors_layout.addSpacing(10)
        
        # Linee
        colors_layout.addWidget(QLabel("Linee"))
        self.line_color_button = QPushButton()
        self.line_color_button.setMinimumWidth(60)
        self.line_color_button.setFixedHeight(25)
        self.update_line_color_button()
        self.line_color_button.clicked.connect(self.choose_line_color)
        colors_layout.addWidget(self.line_color_button, 1)  # stretch factor 1
        
        colors_layout.addSpacing(10)
        
        # Poligoni
        colors_layout.addWidget(QLabel("Poligoni"))
        self.polygon_color_button = QPushButton()
        self.polygon_color_button.setMinimumWidth(60)
        self.polygon_color_button.setFixedHeight(25)
        self.update_polygon_color_button()
        self.polygon_color_button.clicked.connect(self.choose_polygon_color)
        colors_layout.addWidget(self.polygon_color_button, 1)  # stretch factor 1
        
        layout.addLayout(colors_layout)
        layout.addSpacing(15)
        
        # Layout per i colori dei testi
        text_colors_layout = QHBoxLayout()
        text_colors_layout.setContentsMargins(0, 0, 0, 0)
        
        # Label principale
        text_colors_label = QLabel("Testi:")
        text_colors_label.setFixedWidth(50)
        text_colors_layout.addWidget(text_colors_label)
        
        # Testo Nome
        text_colors_layout.addWidget(QLabel("Nome"))
        self.name_text_color_button = QPushButton()
        self.name_text_color_button.setMinimumWidth(60)
        self.name_text_color_button.setFixedHeight(25)
        self.update_name_text_color_button()
        self.name_text_color_button.clicked.connect(self.choose_name_text_color)
        text_colors_layout.addWidget(self.name_text_color_button, 1)
        
        text_colors_layout.addSpacing(10)
        
        # Testo Quota
        text_colors_layout.addWidget(QLabel("Quota"))
        self.elevation_text_color_button = QPushButton()
        self.elevation_text_color_button.setMinimumWidth(60)
        self.elevation_text_color_button.setFixedHeight(25)
        self.update_elevation_text_color_button()
        self.elevation_text_color_button.clicked.connect(self.choose_elevation_text_color)
        text_colors_layout.addWidget(self.elevation_text_color_button, 1)
        
        # Aggiungi spazio vuoto per allineamento
        text_colors_layout.addStretch()
        
        layout.addLayout(text_colors_layout)
        layout.addSpacing(15)

        # Selezione file DXF
        file_layout = QHBoxLayout()
        self.dxf_file_line_edit = QLineEdit()
        self.select_dxf_button = QPushButton("Scegli")
        self.select_dxf_button.clicked.connect(self.select_dxf)

        file_layout.addWidget(QLabel("File DXF:"))
        file_layout.addWidget(self.dxf_file_line_edit)
        file_layout.addWidget(self.select_dxf_button)
        layout.addLayout(file_layout)
        layout.addSpacing(15)
        
        # Layout orizzontale per posizionamento DXF (per allineamento)
        position_layout = QHBoxLayout()
        position_layout.setSpacing(10)
        
        # Pulsante di posizionamento DXF (metà sinistra - 50%)
        self.place_dxf_button = QPushButton("Posiziona sulla Mappa")
        self.place_dxf_button.setEnabled(False)
        self.place_dxf_button.clicked.connect(self.start_placing_dxf)
        self.place_dxf_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        position_layout.addWidget(self.place_dxf_button, 1)  # stretch factor 1
        
        # Spazio vuoto a destra (metà destra - 50%) per allineamento
        empty_layout = QHBoxLayout()
        empty_layout.setContentsMargins(0, 0, 0, 0)
        position_layout.addLayout(empty_layout, 1)  # stretch factor 1
        
        layout.addLayout(position_layout)
        layout.addSpacing(15)
        rename_layout = QHBoxLayout()
        rename_layout.setSpacing(10)
        
        # Pulsante per rinominare punti (metà sinistra - 50%)
        self.rename_vertices_button = QPushButton("Rinomina Punti")
        self.rename_vertices_button.clicked.connect(self.rename_vertices)
        self.rename_vertices_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        rename_layout.addWidget(self.rename_vertices_button, 1)  # stretch factor 1
        
        # Layout per numero iniziale rinomina (metà destra - 50%)
        rename_numero_layout = QHBoxLayout()
        rename_numero_layout.setContentsMargins(0, 0, 0, 0)
        rename_numero_layout.addStretch()  # Spinge tutto a destra
        rename_numero_label = QLabel("Numero iniziale:")
        rename_numero_layout.addWidget(rename_numero_label)
        self.rename_start_number = QLineEdit()
        self.rename_start_number.setFixedWidth(80)  # Larghezza fissa per il campo
        self.rename_start_number.setAlignment(Qt.AlignRight)  # Align text to the right
        # Non impostare un valore di default, verrà calcolato quando si apre il tab
        rename_numero_layout.addWidget(self.rename_start_number)
        
        # Aggiungi il layout numero con stesso stretch factor
        rename_layout.addLayout(rename_numero_layout, 1)  # stretch factor 1
        
        layout.addLayout(rename_layout)
        layout.addSpacing(15)
        vertices_layout = QHBoxLayout()
        vertices_layout.setSpacing(10)
        
        # Pulsante per estrarre vertici (metà sinistra - 50%)
        self.extract_vertices_button = QPushButton("Estrai Vertici")
        self.extract_vertices_button.clicked.connect(self.extract_vertices_from_geometry)
        self.extract_vertices_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.extract_vertices_button.setEnabled(False)  # Disabilitato di default
        vertices_layout.addWidget(self.extract_vertices_button, 1)  # stretch factor 1
        
        # Layout per numero iniziale (metà destra - 50%)
        numero_layout = QHBoxLayout()
        numero_layout.setContentsMargins(0, 0, 0, 0)
        numero_layout.addStretch()  # Spinge tutto a destra
        numero_label = QLabel("Numero iniziale:")
        numero_layout.addWidget(numero_label)
        self.start_vertex_number = QLineEdit()
        self.start_vertex_number.setFixedWidth(80)  # Larghezza fissa per il campo
        self.start_vertex_number.setAlignment(Qt.AlignRight)  # Align text to the right
        # Non impostare un placeholder, verrà calcolato quando si apre il tab
        numero_layout.addWidget(self.start_vertex_number)
        
        # Aggiungi il layout numero con stesso stretch factor
        vertices_layout.addLayout(numero_layout, 1)  # stretch factor 1
        
        layout.addLayout(vertices_layout)
        layout.addSpacing(15)
        elevation_layout = QHBoxLayout()
        elevation_layout.setSpacing(10)
        
        # Pulsante per impostare quota di riferimento (metà sinistra - 50%)
        self.set_elevation_button = QPushButton("Imposta riferimento")
        self.set_elevation_button.clicked.connect(self.start_elevation_reference)
        self.set_elevation_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.set_elevation_button.setEnabled(False)  # Disabilitato di default
        elevation_layout.addWidget(self.set_elevation_button, 1)  # stretch factor 1
        
        # Layout per quota riferimento (metà destra - 50%)
        elevation_input_layout = QHBoxLayout()
        elevation_input_layout.setContentsMargins(0, 0, 0, 0)
        elevation_input_layout.addStretch()  # Spinge tutto a destra
        elevation_label = QLabel("Quota:")
        elevation_input_layout.addWidget(elevation_label)
        self.reference_elevation = QLineEdit()
        self.reference_elevation.setFixedWidth(80)  # Larghezza fissa per il campo
        self.reference_elevation.setAlignment(Qt.AlignRight)  # Align text to the right
        self.reference_elevation.setPlaceholderText("0.00")
        elevation_input_layout.addWidget(self.reference_elevation)
        
        # Aggiungi il layout quota con stesso stretch factor
        elevation_layout.addLayout(elevation_input_layout, 1)  # stretch factor 1
        
        layout.addLayout(elevation_layout)
        
        # Aggiungi spazio elastico
        layout.addStretch()
        
        # Istruzioni in fondo
        layout.addSpacing(15)
        info_label = QLabel(
            "<b>Istruzioni per l'importazione del file DXF:</b><br>"
            "1. Seleziona il file DXF (solo linee o poligoni)<br>"
            "2. Se tutte le geometrie sono valide, si abilita il pulsante<br>"
            "3. Clicca su 'Posiziona sulla Mappa' e poi clicca sul canvas QGIS<br>"
            "4. Verrà creato un layer in memoria con il file DXF"
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        layout.addSpacing(10)  # Add space at the bottom

        self.dxf_tab.setLayout(layout)

    def select_dxf(self):
        path, _ = QFileDialog.getOpenFileName(self, "Seleziona il file DXF", "", "DXF Files (*.dxf)")
        if not path:
            self.dxf_file_line_edit.setText("")
            self.place_dxf_button.setEnabled(False)
            self.dxf_layer = None
            return

        self.dxf_path = path
        self.dxf_file_line_edit.setText(path)

        # Carica layer DXF in modo temporaneo (senza aggiungerlo al progetto)
        temp_dxf_layer = QgsVectorLayer(path, "DXF_Temp", "ogr")
        
        if not temp_dxf_layer.isValid():
            QMessageBox.critical(self, "Errore", "Errore durante l'importazione del DXF.\nVerifica che il file sia un DXF valido.")
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
            
            # Chiedi se vuole posizionare il DXF sulla mappa
            reply = QMessageBox.question(
                self,
                "DXF Caricato",
                "Il file DXF è stato caricato correttamente.\n\nVuoi posizionarlo sulla mappa?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes
            )
            
            if reply == QMessageBox.Yes:
                self.start_placing_dxf()

    def extract_vertices_from_geometry(self):
        """Estrae i vertici da geometrie selezionate in qualsiasi layer e li aggiunge al layer CSV"""
        # Attiva lo strumento di selezione
        self.iface.actionSelect().trigger()
        
        # Trova tutti i layer di linee o poligoni con feature selezionate
        selected_features_by_layer = {}
        
        for layer in QgsProject.instance().mapLayers().values():
            if (layer.type() == QgsVectorLayer.VectorLayer and 
                layer.geometryType() in [QgsWkbTypes.LineGeometry, QgsWkbTypes.PolygonGeometry]):
                selected_features = layer.selectedFeatures()
                if selected_features:
                    selected_features_by_layer[layer] = selected_features
        
        if not selected_features_by_layer:
            QMessageBox.warning(self, "Avviso", "Seleziona almeno una linea o poligono da cui estrarre i vertici")
            return
            
        # Usa il layer attivo come destinazione se è un layer CSV di punti
        active_layer = self.iface.activeLayer()
        
        if (active_layer and 
            active_layer.type() == QgsVectorLayer.VectorLayer and 
            active_layer.geometryType() == QgsWkbTypes.PointGeometry and
            active_layer.customProperty('import_name_field')):
            target_layer = active_layer
        else:
            # Se il layer attivo non è un CSV di punti, cerca altri layer CSV
            csv_layers = []
            for layer in QgsProject.instance().mapLayers().values():
                if (layer.type() == QgsVectorLayer.VectorLayer and 
                    layer.geometryType() == QgsWkbTypes.PointGeometry and
                    layer.customProperty('import_name_field')):
                    csv_layers.append(layer)
                    
            if not csv_layers:
                QMessageBox.warning(self, "Avviso", "Nessun layer CSV importato trovato. Seleziona un layer CSV di punti come layer attivo o importa prima un file CSV.")
                return
                
            if len(csv_layers) == 1:
                target_layer = csv_layers[0]
            else:
                # Se ci sono più layer CSV, chiedi quale usare
                layer_names = [layer.name() for layer in csv_layers]
                
                layer_name, ok = QInputDialog.getItem(
                    self,
                    'Seleziona Layer CSV',
                    'Il layer attivo non è un layer CSV. In quale layer CSV vuoi aggiungere i vertici estratti?',
                    layer_names,
                    0,
                    False
                )
                
                if not ok:
                    return
                    
                # Trova il layer selezionato
                selected_index = layer_names.index(layer_name)
                target_layer = csv_layers[selected_index]
            
        # Ottieni il campo nome dal layer CSV
        name_field = target_layer.customProperty('import_name_field')
        x_field = target_layer.customProperty('import_x_field')
        y_field = target_layer.customProperty('import_y_field')
        original_crs = target_layer.customProperty('original_crs')  # CRS originale del CSV
        
        if not all([name_field, x_field, y_field]):
            QMessageBox.warning(self, "Errore", "Il layer CSV non ha le informazioni necessarie sui campi")
            return
            
        # Verifica che il layer sia in modalità di editing
        if not target_layer.isEditable():
            target_layer.startEditing()
            
        # Ottieni il numero iniziale dal campo di input
        try:
            start_num = int(self.start_vertex_number.text())
        except ValueError:
            # Se il campo è vuoto o non valido, calcola il prossimo numero disponibile
            max_num = self.find_max_point_number()
            start_num = max_num + 1
            self.start_vertex_number.setText(str(start_num))
        
        logging.info(f"Numero iniziale per estrazione vertici: {start_num}")
            
        # Crea un set per tenere traccia dei vertici già estratti
        # per evitare duplicati in punti condivisi tra poligoni
        extracted_points = set()
        
        # Prima, raccogli tutti i punti esistenti nel layer CSV target
        # per evitare di estrarre vertici già presenti
        for feat in target_layer.getFeatures():
            geom = feat.geometry()
            if geom and not geom.isEmpty():
                point = geom.asPoint()
                point_key = (round(point.x(), 8), round(point.y(), 8))
                extracted_points.add(point_key)
        
        logging.info(f"Trovati {len(extracted_points)} punti già esistenti nel layer CSV")
        
        # Estrai vertici da ogni layer con selezioni
        features_added = 0
        point_num = start_num
        vertices_skipped = 0
        total_vertices_processed = 0
        
        # Variabile per memorizzare la scelta dell'utente sui duplicati
        duplicate_choice = None  # None = chiedi ogni volta, 'yes_all' = sì a tutti, 'no_all' = no a tutti
        
        for source_layer, selected_features in selected_features_by_layer.items():
            # Prepara la trasformazione delle coordinate se necessario
            transform = None
            if source_layer.crs() != target_layer.crs():
                transform = QgsCoordinateTransform(source_layer.crs(), target_layer.crs(), QgsProject.instance())
                
            for feature in selected_features:
                geom = feature.geometry()
                if not geom:
                    continue
                    
                # Ottieni tutti i vertici
                vertices = list(geom.vertices())
                # Per i poligoni chiusi, l'ultimo vertice è uguale al primo
                if geom.type() == QgsWkbTypes.PolygonGeometry and len(vertices) > 1:
                    # Controlla se il primo e l'ultimo vertice sono uguali
                    first_vertex = vertices[0]
                    last_vertex = vertices[-1]
                    if (round(first_vertex.x(), 8) == round(last_vertex.x(), 8) and 
                        round(first_vertex.y(), 8) == round(last_vertex.y(), 8)):
                        # Rimuovi l'ultimo vertice duplicato
                        vertices = vertices[:-1]
                
                for vertex in vertices:
                    total_vertices_processed += 1
                    # Crea il punto
                    point = QgsPointXY(vertex.x(), vertex.y())
                    
                    # Trasforma le coordinate se necessario
                    if transform:
                        try:
                            point = transform.transform(point)
                        except Exception as e:
                            logging.warning(f"Errore nella trasformazione delle coordinate: {e}")
                            continue
                    
                    # Crea una chiave univoca per il punto (arrotondata per evitare problemi di precisione)
                    point_key = (round(point.x(), 8), round(point.y(), 8))
                    
                    # Controlla se questo vertice è già stato estratto
                    if point_key in extracted_points:
                        vertices_skipped += 1
                        continue
                        
                    extracted_points.add(point_key)
                    
                    # Crea la nuova feature
                    new_feat = QgsFeature(target_layer.fields())
                    new_feat.setGeometry(QgsGeometry.fromPointXY(point))
                    
                    # Le coordinate per i campi X e Y devono essere nel CRS originale
                    if original_crs and original_crs != target_layer.crs().authid():
                        # Trasforma dal CRS del layer al CRS originale per i campi
                        transform_to_original = QgsCoordinateTransform(
                            target_layer.crs(), 
                            QgsCoordinateReferenceSystem(original_crs), 
                            QgsProject.instance()
                        )
                        original_point = transform_to_original.transform(point)
                        x_coord = original_point.x()
                        y_coord = original_point.y()
                    else:
                        # Se non c'è riproiezione, usa le coordinate dirette
                        x_coord = point.x()
                        y_coord = point.y()
                    
                    # Controlla se il nome esiste già
                    proposed_name = str(point_num)
                    name_exists = False
                    existing_names = []
                    
                    # Cerca nomi duplicati nel layer
                    for existing_feat in target_layer.getFeatures():
                        if existing_feat[name_field] == proposed_name:
                            name_exists = True
                            existing_names.append(proposed_name)
                            break
                    
                    # Se il nome esiste, gestisci in base alla scelta precedente o chiedi
                    if name_exists:
                        if duplicate_choice == 'yes_all':
                            # L'utente ha scelto di inserire tutti i duplicati
                            pass
                        elif duplicate_choice == 'no_all':
                            # L'utente ha scelto di saltare tutti i duplicati
                            point_num += 1
                            continue
                        else:
                            # Chiedi all'utente con opzioni aggiuntive
                            msg_box = QMessageBox(self)
                            msg_box.setWindowTitle('Nome Duplicato')
                            msg_box.setText(f'Il nome "{proposed_name}" esiste già nel layer.\n\nVuoi inserirlo ugualmente?')
                            
                            yes_button = msg_box.addButton('Sì', QMessageBox.YesRole)
                            no_button = msg_box.addButton('No', QMessageBox.NoRole)
                            yes_all_button = msg_box.addButton('Sì a tutti', QMessageBox.YesRole)
                            no_all_button = msg_box.addButton('No a tutti', QMessageBox.NoRole)
                            
                            msg_box.setDefaultButton(no_button)
                            msg_box.exec_()
                            
                            clicked_button = msg_box.clickedButton()
                            
                            if clicked_button == yes_button:
                                # Inserisci solo questo duplicato
                                pass
                            elif clicked_button == no_button:
                                # Salta solo questo duplicato
                                point_num += 1
                                continue
                            elif clicked_button == yes_all_button:
                                # Inserisci questo e tutti i futuri duplicati
                                duplicate_choice = 'yes_all'
                            elif clicked_button == no_all_button:
                                # Salta questo e tutti i futuri duplicati
                                duplicate_choice = 'no_all'
                                point_num += 1
                                continue
                    
                    # Imposta gli attributi
                    new_feat[name_field] = proposed_name
                    new_feat[x_field] = x_coord
                    new_feat[y_field] = y_coord
                    
                    # Copia altri attributi se esistono nel layer target
                    for field in target_layer.fields():
                        if field.name() not in [name_field, x_field, y_field]:
                            # Imposta valori di default per altri campi
                            if field.type() == QVariant.String:
                                new_feat[field.name()] = ""
                            elif field.type() in [QVariant.Int, QVariant.Double]:
                                new_feat[field.name()] = 0
                                
                    # Aggiungi la feature al layer
                    if target_layer.addFeature(new_feat):
                        features_added += 1
                        point_num += 1
                    
        # Salva le modifiche
        target_layer.commitChanges()
        target_layer.updateExtents()
        target_layer.triggerRepaint()
        
        # Non riavviare automaticamente la modalità di modifica
        # target_layer.startEditing()
        
        # Riordina i layer: punti sopra, linee e poligoni sotto
        self.reorder_layers()
        
        message = f"Aggiunti {features_added} nuovi vertici al layer '{target_layer.name()}'.\n"
        if features_added > 0:
            message += f"Numerazione da {start_num} a {point_num - 1}\n"
        if vertices_skipped > 0:
            message += f"\nVertici totali processati: {total_vertices_processed}\n"
            message += f"Vertici saltati (già presenti): {vertices_skipped}"
            
        # Salva il prossimo numero prima di mostrare il messaggio
        next_number = str(point_num) if features_added > 0 else self.start_vertex_number.text()
        
        QMessageBox.information(self, "Completato", message)
        
        # Aggiorna il contatore DOPO il messaggio per evitare reset
        if features_added > 0:
            # Usa un timer per assicurarsi che l'aggiornamento avvenga dopo tutti gli eventi
            from PyQt5.QtCore import QTimer
            def update_counters():
                self.start_vertex_number.setText(next_number)
                self.rename_start_number.setText(next_number)
            QTimer.singleShot(100, update_counters)
        
        # Attiva automaticamente lo strumento di selezione
        self.iface.actionSelectRectangle().trigger()
    
    def rename_vertices(self):
        """Rinomina tutti i punti selezionati del layer attivo"""
        # Ottieni il numero iniziale
        try:
            start_num = int(self.rename_start_number.text())
        except ValueError:
            QMessageBox.warning(self, "Errore", "Il numero iniziale deve essere un numero intero valido")
            return
            
        # Usa solo il layer attivo
        active_layer = self.iface.activeLayer()
        
        if not active_layer or active_layer.type() != QgsVectorLayer.VectorLayer or active_layer.geometryType() != QgsWkbTypes.PointGeometry:
            QMessageBox.warning(self, "Avviso", "Seleziona un layer di punti come layer attivo")
            return
            
        selected_features = active_layer.selectedFeatures()
        if not selected_features:
            QMessageBox.warning(self, "Avviso", f"Seleziona almeno un punto nel layer '{active_layer.name()}' da rinominare")
            return
            
        selected_features_by_layer = {active_layer: selected_features}
            
        # Conta il totale delle feature da rinominare
        total_features = sum(len(features) for features in selected_features_by_layer.values())
        
        reply = QMessageBox.question(
            self, 
            'Conferma rinomina', 
            f'Vuoi rinominare {total_features} punti selezionati?\n'
            f'La numerazione partirà da {start_num}.',
            QMessageBox.Yes | QMessageBox.No, 
            QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
            
        features_renamed = 0
        current_num = start_num
        
        # Rinomina le feature in ogni layer
        for layer, selected_features in selected_features_by_layer.items():
            # Ottieni il campo nome dal layer
            name_field = layer.customProperty('import_name_field')
            
            # Se non c'è un campo nome specificato, cerca campi comuni
            if not name_field:
                possible_name_fields = ['nome', 'name', 'id', 'punto', 'point', 'numero', 'number']
                field_names = [f.name().lower() for f in layer.fields()]
                
                for possible_field in possible_name_fields:
                    if possible_field in field_names:
                        # Trova il nome esatto del campo (case-sensitive)
                        for field in layer.fields():
                            if field.name().lower() == possible_field:
                                name_field = field.name()
                                break
                        if name_field:
                            break
            
            if not name_field:
                QMessageBox.warning(
                    self, 
                    "Avviso", 
                    f"Il layer '{layer.name()}' non ha un campo nome riconosciuto. Saltato."
                )
                continue
                
            # Verifica che il layer sia in modalità di editing
            if not layer.isEditable():
                layer.startEditing()
                
            # Ottieni l'indice del campo nome
            name_field_idx = layer.fields().indexOf(name_field)
            if name_field_idx == -1:
                continue
                
            # Ordina le feature selezionate per coordinate (prima per X, poi per Y)
            features_sorted = []
            for feature in selected_features:
                geom = feature.geometry()
                if geom and not geom.isEmpty():
                    point = geom.asPoint()
                    features_sorted.append((feature, point.x(), point.y()))
            
            # Ordina prima per X (da sinistra a destra), poi per Y (dal basso all'alto)
            features_sorted.sort(key=lambda f: (f[1], -f[2]))
                
            # Rinomina ogni feature selezionata nell'ordine spaziale
            for feature_data in features_sorted:
                feature = feature_data[0]
                layer.changeAttributeValue(feature.id(), name_field_idx, str(current_num))
                features_renamed += 1
                current_num += 1
                
            # Salva le modifiche
            layer.commitChanges()
            layer.triggerRepaint()
            
            # Non riavviare automaticamente la modalità di modifica
            # layer.startEditing()
            
        if features_renamed > 0:
            QMessageBox.information(
                self, 
                "Completato", 
                f"Rinominati {features_renamed} punti.\n"
                f"Numerazione da {start_num} a {current_num - 1}"
            )
            
            # Aggiorna il contatore del campo estrai vertici
            self.start_vertex_number.setText(str(current_num))
            
            # Aggiorna anche il campo rinomina per la prossima operazione
            self.rename_start_number.setText(str(current_num))
        else:
            QMessageBox.warning(self, "Avviso", "Nessun punto è stato rinominato")
    
    def find_max_point_number(self):
        """Trova il numero massimo solo nel layer attivo per evitare rallentamenti"""
        max_num = 0
        
        # OTTIMIZZAZIONE: Controlla solo il layer attivo
        active_layer = self.iface.activeLayer()
        if (active_layer and 
            active_layer.type() == QgsVectorLayer.VectorLayer and 
            active_layer.geometryType() == QgsWkbTypes.PointGeometry):
            layer = active_layer
            
            # Prima prova con il campo nome specificato durante l'importazione
            name_field = layer.customProperty('import_name_field')
            
            # Se non c'è un campo nome specificato, cerca campi comuni
            if not name_field:
                # Cerca campi che potrebbero contenere il nome/numero del punto
                possible_name_fields = ['nome', 'name', 'id', 'punto', 'point', 'numero', 'number']
                field_names = [f.name().lower() for f in layer.fields()]
                
                for possible_field in possible_name_fields:
                    if possible_field in field_names:
                        # Trova il nome esatto del campo (case-sensitive)
                        for field in layer.fields():
                            if field.name().lower() == possible_field:
                                name_field = field.name()
                                break
                        if name_field:
                            break
                
            if name_field and name_field in layer.fields().names():
                for feature in layer.getFeatures():
                    value = feature[name_field]
                    if value:
                        try:
                            # Prova a estrarre numeri
                            import re
                            name_str = str(value)
                            # Se il nome è solo un numero o inizia con un numero seguito da non-cifre
                            if name_str.isdigit():
                                num = int(name_str)
                                max_num = max(max_num, num)
                            else:
                                # Cerca un numero all'inizio della stringa
                                match = re.match(r'^(\d+)(?:\D|$)', name_str)
                                if match:
                                    num = int(match.group(1))
                                    max_num = max(max_num, num)
                        except:
                            pass
        else:
            # Se non c'è un layer attivo appropriato, usa un valore di default
            max_num = 0
                        
        return max_num
    
    def enable_snap_on_startup(self):
        """Abilita lo snap all'avvio del plugin"""
        snapping_config = QgsProject.instance().snappingConfig()
        snapping_config.setEnabled(True)
        snapping_config.setMode(QgsSnappingConfig.AllLayers)
        snapping_config.setType(QgsSnappingConfig.VertexAndSegment)
        snapping_config.setTolerance(10)
        snapping_config.setUnits(QgsTolerance.Pixels)
        try:
            snapping_config.setIntersectionSnapping(True)
        except AttributeError:
            pass
        QgsProject.instance().setSnappingConfig(snapping_config)
        logging.info("Snap abilitato di default all'avvio")
    
    def initialize_elevation_field(self):
        """Inizializza il campo quota solo dal layer attivo all'avvio"""
        # OTTIMIZZAZIONE: Controlla solo il layer attivo per evitare rallentamenti
        active_layer = self.iface.activeLayer()
        if (active_layer and 
            active_layer.type() == QgsVectorLayer.VectorLayer and 
            active_layer.geometryType() == QgsWkbTypes.PointGeometry):
            
            # Recupera campo nome
            name_field = active_layer.customProperty('import_name_field')
            if name_field:
                self.name_field = name_field
                logging.info(f"Campo nome inizializzato all'avvio: {name_field}")
            
            # Recupera campo quota
            elevation_field = active_layer.customProperty('import_elevation_field')
            if elevation_field:
                self.selected_elevation_field = elevation_field
                logging.info(f"Campo quota inizializzato all'avvio: {elevation_field}")
                
            # Rileva i colori delle etichette esistenti
            if active_layer.labelsEnabled() and active_layer.labeling():
                labeling = active_layer.labeling()
                if hasattr(labeling, 'settings'):
                    settings = labeling.settings()
                    text_format = settings.format()
                    
                    # Controlla il tipo di etichetta dal campo
                    field_name = settings.fieldName
                    
                    # Se è un'espressione HTML per Nome+Quota, estrai i colori
                    if 'concat(' in field_name and '<span style' in field_name:
                        import re
                        # Estrai i colori dall'espressione HTML
                        color_matches = re.findall(r'color:\s*([^;"}]+)', field_name)
                        if len(color_matches) >= 2:
                            # Primo colore è per la quota, secondo per il nome
                            elevation_color = QColor(color_matches[0])
                            name_color = QColor(color_matches[1])
                            if elevation_color.isValid():
                                self.elevation_text_color = elevation_color
                                logging.info(f"Colore quota rilevato: {elevation_color.name()}")
                            if name_color.isValid():
                                self.name_text_color = name_color
                                logging.info(f"Colore nome rilevato: {name_color.name()}")
                    else:
                        # Per etichette semplici, prendi il colore dal formato testo
                        text_color = text_format.color()
                        
                        # Determina se è nome o quota basandosi sul campo
                        if elevation_field and field_name == elevation_field:
                            self.elevation_text_color = text_color
                            logging.info(f"Colore quota rilevato: {text_color.name()}")
                        elif name_field and field_name == name_field:
                            self.name_text_color = text_color
                            logging.info(f"Colore nome rilevato: {text_color.name()}")
        
        # Se non abbiamo trovato colori dal layer attivo, cerca in tutti i layer CSV
        if (self.name_text_color == self.default_name_text_color or 
            self.elevation_text_color == self.default_elevation_text_color):
            for layer in QgsProject.instance().mapLayers().values():
                if (layer.type() == QgsVectorLayer.VectorLayer and 
                    layer.customProperty('import_source') == 'csv' and
                    layer.labelsEnabled() and layer.labeling()):
                    
                    labeling = layer.labeling()
                    if hasattr(labeling, 'settings'):
                        settings = labeling.settings()
                        text_format = settings.format()
                        field_name = settings.fieldName
                        
                        # Se è un'espressione HTML per Nome+Quota, estrai i colori
                        if 'concat(' in field_name and '<span style' in field_name:
                            import re
                            color_matches = re.findall(r'color:\s*([^;"}]+)', field_name)
                            if len(color_matches) >= 2:
                                elevation_color = QColor(color_matches[0])
                                name_color = QColor(color_matches[1])
                                if elevation_color.isValid() and self.elevation_text_color == self.default_elevation_text_color:
                                    self.elevation_text_color = elevation_color
                                if name_color.isValid() and self.name_text_color == self.default_name_text_color:
                                    self.name_text_color = name_color
                        else:
                            # Per etichette semplici
                            text_color = text_format.color()
                            elevation_field = layer.customProperty('import_elevation_field')
                            name_field = layer.customProperty('import_name_field')
                            
                            if elevation_field and field_name == elevation_field and self.elevation_text_color == self.default_elevation_text_color:
                                self.elevation_text_color = text_color
                            elif name_field and field_name == name_field and self.name_text_color == self.default_name_text_color:
                                self.name_text_color = text_color
        
        if not self.selected_elevation_field:
            logging.info("Nessun campo quota trovato nel layer attivo all'avvio")
        
        # Aggiorna i pulsanti dei colori con i colori rilevati o di default
        if hasattr(self, 'color_button'):
            self.update_color_button()
        if hasattr(self, 'line_color_button'):
            self.update_line_color_button()
        if hasattr(self, 'polygon_color_button'):
            self.update_polygon_color_button()
        if hasattr(self, 'name_text_color_button'):
            self.update_name_text_color_button()
        if hasattr(self, 'elevation_text_color_button'):
            self.update_elevation_text_color_button()
    
    def enable_snap(self):
        """Abilita lo snap su tutti i layer"""
        snapping_config = QgsProject.instance().snappingConfig()
        
        # Toggle dello stato dello snap
        if snapping_config.enabled():
            # Se è già abilitato, disabilita
            snapping_config.setEnabled(False)
            # Pulsante rimosso
            QMessageBox.information(self, "Snap", "Snap disabilitato")
        else:
            # Se è disabilitato, abilita
            snapping_config.setEnabled(True)
            snapping_config.setMode(QgsSnappingConfig.AllLayers)
            # Per QGIS 3.x usa VertexAndSegment che include vertici e segmenti
            snapping_config.setType(QgsSnappingConfig.VertexAndSegment)
            snapping_config.setTolerance(10)
            snapping_config.setUnits(QgsTolerance.Pixels)
            # Abilita lo snapping all'intersezione se disponibile
            try:
                snapping_config.setIntersectionSnapping(True)
            except AttributeError:
                # Metodo non disponibile in questa versione di QGIS
                pass
            # Pulsante rimosso
            QMessageBox.information(self, "Snap", "Snap abilitato su tutti i layer")
            
        QgsProject.instance().setSnappingConfig(snapping_config)
    
    def start_placing_dxf(self):
        if not self.dxf_layer:
            QMessageBox.warning(self, "Avviso", "Nessun layer DXF valido disponibile")
            return

        # Imposta CRS del progetto al layer se non ne ha uno
        if not self.dxf_layer.crs().isValid():
            crs_project = QgsProject.instance().crs()
            self.dxf_layer.setCrs(crs_project)

        # Abilita snapping sempre quando si posiziona il DXF
        snapping_config = QgsProject.instance().snappingConfig()
        snapping_config.setEnabled(True)
        snapping_config.setMode(QgsSnappingConfig.AllLayers)
        snapping_config.setType(QgsSnappingConfig.VertexAndSegment)
        snapping_config.setTolerance(10)
        snapping_config.setUnits(QgsTolerance.Pixels)
        try:
            snapping_config.setIntersectionSnapping(True)
        except AttributeError:
            pass
        QgsProject.instance().setSnappingConfig(snapping_config)
        
        # Forza l'aggiornamento del canvas per attivare lo snap visivamente
        self.iface.mapCanvas().snappingUtils().setConfig(snapping_config)
        self.iface.mapCanvas().refresh()

        # Crea map tool personalizzato per il clic
        self.map_tool = DXFMapTool(self.iface.mapCanvas(), self.dxf_layer)
        self.map_tool.pointClicked.connect(self.place_dxf_on_map)
        self.iface.mapCanvas().setMapTool(self.map_tool)

        # Mostra anteprima del DXF
        extent = self.dxf_layer.extent()
        width = extent.width()
        height = extent.height()
        
        # Ottieni informazioni sui CRS
        dxf_crs = self.dxf_layer.crs()
        project_crs = QgsProject.instance().crs()
        
        # Determina le unità
        dxf_units = "gradi" if dxf_crs.isGeographic() else "metri"
        project_units = "gradi" if project_crs.isGeographic() else "metri"
        
        # Avviso se c'è mismatch tra geografico e proiettato
        warning_msg = ""
        if dxf_crs.isGeographic() != project_crs.isGeographic():
            warning_msg = "\n⚠️ ATTENZIONE: Il DXF e il progetto usano sistemi di coordinate diversi!\n"
        
        # Messagebox rimosso per richiesta utente
        # L'utente può cliccare direttamente sulla mappa per posizionare il DXF

    def place_dxf_on_map(self, qgs_point_xy):
        if not self.dxf_layer:
            QMessageBox.warning(self, "Errore", "Nessun layer DXF disponibile.")
            return

        # Ottieni CRS
        dxf_crs = self.dxf_layer.crs()
        project_crs = QgsProject.instance().crs()
        
        # Calcola il centroide di tutte le geometrie del DXF
        all_geoms = []
        for feat in self.dxf_layer.getFeatures():
            geom = feat.geometry()
            if geom:
                all_geoms.append(geom)
        
        if not all_geoms:
            QMessageBox.warning(self, "Errore", "Nessuna geometria valida trovata nel DXF")
            return
            
        # Combina tutte le geometrie e calcola il centroide
        combined_geom = QgsGeometry.unaryUnion(all_geoms)
        centroid = combined_geom.centroid()
        
        if not centroid or centroid.isEmpty():
            QMessageBox.warning(self, "Errore", "Impossibile calcolare il centroide del DXF")
            return
            
        centroid_point = centroid.asPoint()
        origin_x = centroid_point.x()
        origin_y = centroid_point.y()
        
        print(f"Click point: {qgs_point_xy.x()}, {qgs_point_xy.y()}")
        print(f"DXF centroide: x={origin_x}, y={origin_y}")
        print(f"DXF CRS: {dxf_crs.authid()}, Project CRS: {project_crs.authid()}")

        # Conta le features e determina il tipo
        feature_count = self.dxf_layer.featureCount()
        if feature_count == 0:
            QMessageBox.critical(self, "Errore", "DXF vuoto, nessuna geometria")
            return
            
        # Prima feature per determinare se line o polygon
        features = list(self.dxf_layer.getFeatures())
        if not features:
            QMessageBox.critical(self, "Errore", "Impossibile leggere le geometrie dal DXF")
            return
            
        first_feat = features[0]
        if not first_feat or not first_feat.geometry():
            QMessageBox.critical(self, "Errore", "Prima geometria non valida")
            return

        topo = QgsWkbTypes.geometryType(first_feat.geometry().wkbType())
        if topo == QgsWkbTypes.LineGeometry:
            geometry_string = "LineString"
        elif topo == QgsWkbTypes.PolygonGeometry:
            geometry_string = "Polygon"
        else:
            QMessageBox.critical(self, "Errore", "Tipo di geometria non supportato")
            return

        # Usa il CRS del progetto per il layer DXF posizionato
        target_crs = project_crs
        # Estrai il nome del file DXF senza percorso e estensione
        dxf_name = os.path.splitext(os.path.basename(self.dxf_path))[0] if self.dxf_path else "DXF_Posizionato"
        memory_layer = QgsVectorLayer(f"{geometry_string}?crs={target_crs.authid()}", dxf_name, "memory")
        provider = memory_layer.dataProvider()

        # Copia campi
        fields = self.dxf_layer.fields()
        provider.addAttributes(fields.toList())
        memory_layer.updateFields()

        # Prepara trasformazione coordinate se necessario
        if dxf_crs != target_crs:
            transform = QgsCoordinateTransform(dxf_crs, target_crs, QgsProject.instance())
        else:
            transform = None
            
        # Trasforma il punto cliccato nel CRS di destinazione se necessario
        if project_crs != target_crs:
            click_transform = QgsCoordinateTransform(project_crs, target_crs, QgsProject.instance())
            click_point = click_transform.transform(qgs_point_xy)
        else:
            click_point = qgs_point_xy
            
        # Calcola la traslazione corretta basata sul centroide
        # Se i CRS sono diversi, trasforma prima il centroide nel CRS di destinazione
        if transform:
            centroid_point = QgsPointXY(origin_x, origin_y)
            centroid_transformed = transform.transform(centroid_point)
            print(f"Centroide DXF trasformato: {centroid_transformed.x()}, {centroid_transformed.y()}")
            dx = click_point.x() - centroid_transformed.x()
            dy = click_point.y() - centroid_transformed.y()
        else:
            # Se i CRS sono uguali, calcola direttamente
            dx = click_point.x() - origin_x
            dy = click_point.y() - origin_y
            
        print(f"Traslazione finale: dx={dx}, dy={dy}")
        print(f"Distanza di traslazione: {(dx**2 + dy**2)**0.5} unità")
            
        # Trasla feature
        for feat in self.dxf_layer.getFeatures():
            geom = feat.geometry()
            if not geom:
                continue
            
            # Crea una copia della geometria per non modificare l'originale
            geom_copy = QgsGeometry(geom)
            
            # Prima trasforma al CRS di destinazione (EPSG:3857) se necessario
            if transform:
                geom_copy.transform(transform)
            
            # Poi trasla nella posizione desiderata  
            if not geom_copy.translate(dx, dy):
                print(f"Errore nella traslazione della geometria")
            
            new_feat = QgsFeature()
            new_feat.setFields(fields)
            new_feat.setAttributes(feat.attributes())
            new_feat.setGeometry(geom_copy)
            provider.addFeature(new_feat)
        
        memory_layer.updateExtents()
        
        # Imposta proprietà personalizzata per identificare il layer come DXF
        memory_layer.setCustomProperty('is_dxf_layer', True)
        
        QgsProject.instance().addMapLayer(memory_layer)

        # Stile personalizzato: usa i colori selezionati nelle impostazioni
        if geometry_string == "Polygon":
            # Per i poligoni: crea un nuovo simbolo con riempimento trasparente e bordo del colore scelto
            from qgis.core import QgsFillSymbol
            symbol = QgsFillSymbol.createSimple({
                'color': '0,0,0,0',  # Riempimento completamente trasparente
                'outline_color': f'{self.polygon_color.red()},{self.polygon_color.green()},{self.polygon_color.blue()}',
                'outline_width': '0.5',  # Larghezza bordo
                'outline_style': 'solid'
            })
            memory_layer.setRenderer(QgsSingleSymbolRenderer(symbol))
        else:
            # Per le linee: crea un nuovo simbolo linea del colore scelto
            from qgis.core import QgsLineSymbol
            symbol = QgsLineSymbol.createSimple({
                'color': f'{self.line_color.red()},{self.line_color.green()},{self.line_color.blue()}',
                'width': '0.5',
                'line_style': 'solid'
            })
            memory_layer.setRenderer(QgsSingleSymbolRenderer(symbol))
            
        memory_layer.triggerRepaint()
        
        # Aggiorna lo stato dei pulsanti dopo aver posizionato il DXF
        self.update_buttons_state()
        
        # Riordina i layer: punti sopra, linee e poligoni sotto
        self.reorder_layers()
        
        # Refresh della mappa senza cambiare lo zoom
        self.iface.mapCanvas().refresh()

        QMessageBox.information(self, "Completato", "DXF posizionato correttamente sulla mappa")

        # Riporta eventuali tool di digitalizzazione
        self.iface.actionAddFeature().trigger()
        self.iface.mapCanvas().refresh()

        # Scollega e disabilita map tool
        self.iface.mapCanvas().unsetMapTool(self.map_tool)
        self.map_tool = None
        
    ############################################################################
    #                               TAB 4: SETTINGS (MOVED TO GESTIONE)
    ############################################################################
    # Method moved to init_dxf_tab - no longer needed
    
    def on_stay_on_top_changed(self, state):
        """Gestisce il cambio di stato della finestra sempre in primo piano"""
        current_flags = self.windowFlags()
        
        if state == Qt.Checked:
            # Aggiungi il flag per rimanere sopra
            self.setWindowFlags(current_flags | Qt.WindowStaysOnTopHint)
        else:
            # Rimuovi il flag per rimanere sopra
            self.setWindowFlags(current_flags & ~Qt.WindowStaysOnTopHint)
        
        # Mostra nuovamente la finestra dopo aver cambiato i flag
        self.show()
    
    def on_snap_checkbox_changed(self, state):
        """Gestisce il cambio di stato dello snap"""
        snapping_config = QgsProject.instance().snappingConfig()
        
        if state == Qt.Checked:
            # Abilita snap
            snapping_config.setEnabled(True)
            snapping_config.setMode(QgsSnappingConfig.AllLayers)
            snapping_config.setType(QgsSnappingConfig.VertexAndSegment)
            snapping_config.setTolerance(10)
            snapping_config.setUnits(QgsTolerance.Pixels)
            try:
                snapping_config.setIntersectionSnapping(True)
            except AttributeError:
                pass
        else:
            # Disabilita snap
            snapping_config.setEnabled(False)
            
        QgsProject.instance().setSnappingConfig(snapping_config)
        logging.info(f"Snap {'abilitato' if state == Qt.Checked else 'disabilitato'}")
    
    def on_labels_checkbox_changed(self, state):
        """Gestisce il cambio di stato delle etichette per i layer"""
        # Salva lo stato per usarlo quando si creano nuovi layer
        self.labels_enabled = (state == Qt.Checked)
        # Abilita/disabilita il menu a tendina delle etichette
        self.label_type_combo.setEnabled(self.labels_enabled)
        # Aggiorna anche i layer esistenti
        self.update_labels_visibility()
        logging.info(f"Etichette {'abilitate' if self.labels_enabled else 'disabilitate'}")
    
    def update_color_button(self):
        """Aggiorna il colore di sfondo del pulsante colore"""
        self.color_button.setStyleSheet(
            f"background-color: rgb({self.point_color.red()}, "
            f"{self.point_color.green()}, {self.point_color.blue()}); "
            f"border: 1px solid black;"
        )
    
    def choose_point_color(self):
        """Apre il dialog per scegliere il colore dei punti"""
        color = QColorDialog.getColor(self.point_color, self, "Scegli il colore dei punti")
        if color.isValid():
            self.point_color = color
            self.update_color_button()
            self.apply_point_color_to_layers()
            logging.info(f"Colore punti cambiato in: RGB({color.red()}, {color.green()}, {color.blue()})")
    
    def update_line_color_button(self):
        """Aggiorna il colore di sfondo del pulsante colore linee"""
        self.line_color_button.setStyleSheet(
            f"background-color: rgb({self.line_color.red()}, "
            f"{self.line_color.green()}, {self.line_color.blue()}); "
            f"border: 1px solid black;"
        )
    
    def choose_line_color(self):
        """Apre il dialog per scegliere il colore delle linee"""
        color = QColorDialog.getColor(self.line_color, self, "Scegli il colore delle linee")
        if color.isValid():
            self.line_color = color
            self.update_line_color_button()
            self.apply_line_color_to_layers()
            logging.info(f"Colore linee cambiato in: RGB({color.red()}, {color.green()}, {color.blue()})")
    
    def update_polygon_color_button(self):
        """Aggiorna il colore di sfondo del pulsante colore poligoni"""
        self.polygon_color_button.setStyleSheet(
            f"background-color: rgb({self.polygon_color.red()}, "
            f"{self.polygon_color.green()}, {self.polygon_color.blue()}); "
            f"border: 1px solid black;"
        )
    
    def choose_polygon_color(self):
        """Apre il dialog per scegliere il colore dei poligoni"""
        color = QColorDialog.getColor(self.polygon_color, self, "Scegli il colore dei poligoni")
        if color.isValid():
            self.polygon_color = color
            self.update_polygon_color_button()
            self.apply_polygon_color_to_layers()
            logging.info(f"Colore poligoni cambiato in: RGB({color.red()}, {color.green()}, {color.blue()})")
    
    def update_name_text_color_button(self):
        """Aggiorna il colore di sfondo del pulsante colore testo nome"""
        self.name_text_color_button.setStyleSheet(
            f"background-color: rgb({self.name_text_color.red()}, "
            f"{self.name_text_color.green()}, {self.name_text_color.blue()}); "
            f"border: 1px solid black;"
        )
    
    def choose_name_text_color(self):
        """Apre il dialog per scegliere il colore del testo dei nomi"""
        color = QColorDialog.getColor(self.name_text_color, self, "Scegli il colore del testo dei nomi")
        if color.isValid():
            self.name_text_color = color
            self.update_name_text_color_button()
            self.update_labels_on_layers()  # Aggiorna le etichette
            logging.info(f"Colore testo nome cambiato in: RGB({color.red()}, {color.green()}, {color.blue()})")
    
    def update_elevation_text_color_button(self):
        """Aggiorna il colore di sfondo del pulsante colore testo quota"""
        self.elevation_text_color_button.setStyleSheet(
            f"background-color: rgb({self.elevation_text_color.red()}, "
            f"{self.elevation_text_color.green()}, {self.elevation_text_color.blue()}); "
            f"border: 1px solid black;"
        )
    
    def choose_elevation_text_color(self):
        """Apre il dialog per scegliere il colore del testo delle quote"""
        color = QColorDialog.getColor(self.elevation_text_color, self, "Scegli il colore del testo delle quote")
        if color.isValid():
            self.elevation_text_color = color
            self.update_elevation_text_color_button()
            self.update_labels_on_layers()  # Aggiorna le etichette
            logging.info(f"Colore testo quota cambiato in: RGB({color.red()}, {color.green()}, {color.blue()})")
    
    def on_label_type_changed(self, index):
        """Gestisce il cambio del tipo di etichetta da mostrare"""
        self.label_type = self.label_type_combo.currentData()
        
        # Se è selezionato Quota o Nome+Quota, verifica che ci sia un campo quota configurato
        if self.label_type in ["elevation", "both"]:
            # Cerca il campo quota nei layer esistenti
            found_elevation_field = False
            for layer in QgsProject.instance().mapLayers().values():
                if (layer.type() == QgsVectorLayer.VectorLayer and 
                    layer.geometryType() == QgsWkbTypes.PointGeometry):
                    elevation_field = layer.customProperty('import_elevation_field')
                    if elevation_field:
                        self.selected_elevation_field = elevation_field
                        found_elevation_field = True
                        break
            
            if not found_elevation_field:
                QMessageBox.information(
                    self,
                    "Campo quota non trovato",
                    "Nessun layer ha un campo quota configurato.\n\n"
                    "Durante l'importazione CSV, seleziona il campo quota (Hei)."
                )
                # Torna a Nome
                self.label_type_combo.setCurrentIndex(0)
                self.label_type = "name"
                return
        
        if self.labels_enabled:
            self.update_labels_on_layers()
        logging.info(f"Tipo etichetta cambiato a: {self.label_type}")
    
    def apply_point_color_to_layers(self):
        """Applica il colore selezionato solo al layer attivo se è un layer di punti CSV"""
        active_layer = self.iface.activeLayer()
        
        if (active_layer and 
            active_layer.type() == QgsVectorLayer.VectorLayer and 
            active_layer.geometryType() == QgsWkbTypes.PointGeometry and
            active_layer.customProperty('import_name_field')):  # Solo layer CSV importati
            
            # Crea nuovo simbolo con il colore selezionato
            symbol = QgsMarkerSymbol.createSimple({
                'name': 'circle', 
                'color': f'{self.point_color.red()},{self.point_color.green()},{self.point_color.blue()}',
                'size': '2.5'
            })
            active_layer.setRenderer(QgsSingleSymbolRenderer(symbol))
            active_layer.triggerRepaint()
            logging.info(f"Colore aggiornato per layer attivo: {active_layer.name()}")
        else:
            QMessageBox.information(self, "Info", "Seleziona un layer di punti CSV per applicare il colore")
    
    def apply_line_color_to_layers(self):
        """Applica il colore selezionato solo al layer attivo se è un layer di linee DXF"""
        from qgis.core import QgsLineSymbol
        
        active_layer = self.iface.activeLayer()
        
        if (active_layer and 
            active_layer.type() == QgsVectorLayer.VectorLayer and 
            active_layer.geometryType() == QgsWkbTypes.LineGeometry and
            active_layer.customProperty('is_dxf_layer')):  # Solo layer DXF
            
            # Crea nuovo simbolo con il colore selezionato
            symbol = QgsLineSymbol.createSimple({
                'color': f'{self.line_color.red()},{self.line_color.green()},{self.line_color.blue()}',
                'width': '0.5',
                'line_style': 'solid'
            })
            active_layer.setRenderer(QgsSingleSymbolRenderer(symbol))
            active_layer.triggerRepaint()
            logging.info(f"Colore linee aggiornato per layer attivo: {active_layer.name()}")
        else:
            QMessageBox.information(self, "Info", "Seleziona un layer di linee DXF per applicare il colore")
    
    def apply_polygon_color_to_layers(self):
        """Applica il colore selezionato solo al layer attivo se è un layer di poligoni DXF"""
        from qgis.core import QgsFillSymbol
        
        active_layer = self.iface.activeLayer()
        
        if (active_layer and 
            active_layer.type() == QgsVectorLayer.VectorLayer and 
            active_layer.geometryType() == QgsWkbTypes.PolygonGeometry and
            active_layer.customProperty('is_dxf_layer')):  # Solo layer DXF
            
            # Crea nuovo simbolo con il colore selezionato
            symbol = QgsFillSymbol.createSimple({
                'color': '0,0,0,0',  # Riempimento trasparente
                'outline_color': f'{self.polygon_color.red()},{self.polygon_color.green()},{self.polygon_color.blue()}',
                'outline_width': '0.5',
                'outline_style': 'solid'
            })
            active_layer.setRenderer(QgsSingleSymbolRenderer(symbol))
            active_layer.triggerRepaint()
            logging.info(f"Colore poligoni aggiornato per layer attivo: {active_layer.name()}")
        else:
            QMessageBox.information(self, "Info", "Seleziona un layer di poligoni DXF per applicare il colore")
    
    def update_labels_on_layers(self):
        """Aggiorna le etichette su tutti i layer CSV di punti per i colori dei testi"""
        if not self.labels_enabled:
            logging.info("Etichette disabilitate, skip update_labels_on_layers")
            return
        
        # Aggiorna tutti i layer CSV di punti per mantenere colori uniformi
        for layer_id, layer in QgsProject.instance().mapLayers().items():
            if (layer and 
                layer.type() == QgsVectorLayer.VectorLayer and 
                layer.geometryType() == QgsWkbTypes.PointGeometry and
                layer.customProperty('import_source') == 'csv'):  # Solo layer CSV importati
                
                # Prima prova a ottenere il campo nome dalle proprietà del layer (per layer CSV importati)
                name_field = layer.customProperty('import_name_field')
                
                # Se non c'è, cerca un campo nome comune
                if not name_field:
                    possible_name_fields = ['nome', 'name', 'id', 'punto', 'point', 'numero', 'number']
                    field_names_lower = [f.name().lower() for f in layer.fields()]
                    
                    for possible_field in possible_name_fields:
                        if possible_field in field_names_lower:
                            # Trova il nome esatto del campo (case-sensitive)
                            for field in layer.fields():
                                if field.name().lower() == possible_field:
                                    name_field = field.name()
                                    break
                            if name_field:
                                break
                    
                    # Se ancora non c'è, prendi il primo campo (utile per CSV senza header)
                    if not name_field and layer.fields().count() > 0:
                        name_field = layer.fields()[0].name()
                        logging.info(f"Usando il primo campo come nome: {name_field}")
                
                if not name_field:
                    logging.info(f"Nessun campo trovato per layer: {layer.name()}, skip")
                    continue
                
                # Recupera il campo elevation specifico del layer
                elevation_field = layer.customProperty('import_elevation_field')
                if not elevation_field:
                    # Se non c'è nelle proprietà personalizzate, non usare il campo elevation globale
                    elevation_field = None
                
                # Crea nuove impostazioni etichette
                label_settings = QgsPalLayerSettings()
                
                # Configura l'espressione per l'etichetta
                field_names = [f.name() for f in layer.fields()]
                logging.info(f"Layer {layer.name()} - Campi disponibili: {field_names}")
                
                # Configura l'etichetta in base al tipo selezionato
                if self.label_type == "name":
                    # Mostra solo il nome
                    label_settings.fieldName = name_field
                    label_settings.isExpression = False
                    logging.info(f"Impostata etichetta nome: {name_field}")
                    
                elif self.label_type == "elevation" and elevation_field and elevation_field in field_names:
                    # Mostra solo la quota
                    label_settings.fieldName = elevation_field
                    label_settings.isExpression = False
                    logging.info(f"Impostata etichetta quota: {elevation_field}")
                    
                elif self.label_type == "both" and elevation_field and elevation_field in field_names:
                    # Mostra nome e quota in un'unica etichetta
                    label_settings.isExpression = True
                    # Usa spazi vuoti per creare separazione verticale tra quota e nome
                    # Usa i colori configurati per nome e quota
                    elevation_color = self.elevation_text_color.name()
                    name_color = self.name_text_color.name()
                    label_settings.fieldName = 'concat(\'<span style="color: {};">\', "{}", \'</span>\', \'<br>\', \'&nbsp;\', \'<br>\', \'<span style="color: {};">\', "{}", \'</span>\')'.format(elevation_color, elevation_field, name_color, name_field)
                    
                    QgsMessageLog.logMessage(f"Update labels - Layer: {layer.name()}", 'spotter', Qgis.Info)
                    QgsMessageLog.logMessage(f"Update labels - Campo nome: {name_field}", 'spotter', Qgis.Info)
                    QgsMessageLog.logMessage(f"Update labels - Campo quota: {elevation_field}", 'spotter', Qgis.Info)
                    
                else:
                    # Fallback: mostra il nome
                    label_settings.fieldName = name_field
                    label_settings.isExpression = False
                    logging.info(f"Fallback a etichetta nome: {name_field}")
                
                label_settings.enabled = True
                
                # Non impostiamo placement per evitare errori di compatibilità
                # Le etichette saranno posizionate con le impostazioni di default di QGIS
                
                # Configura il formato del testo (mantieni le impostazioni originali)
                text_format = QgsTextFormat()
                text_format.setFont(QFont("Noto Sans", 12))
                text_format.setSize(12)
                
                # Usa sempre i colori correnti (non di default) per update_labels_on_layers
                # perché questa funzione viene chiamata solo quando l'utente cambia manualmente i colori
                if self.label_type == "elevation":
                    text_format.setColor(self.elevation_text_color)
                elif self.label_type == "name":
                    text_format.setColor(self.name_text_color)
                elif self.label_type == "both":
                    # Per Nome+Quota usiamo HTML quindi non impostiamo il colore qui
                    text_format.setAllowHtmlFormatting(True)
                
                # Buffer bianco per leggibilità
                buffer_settings = QgsTextBufferSettings()
                buffer_settings.setEnabled(True)
                buffer_settings.setSize(2)
                buffer_settings.setColor(QColor(255, 255, 255))
                text_format.setBuffer(buffer_settings)
                
                label_settings.setFormat(text_format)
                
                # Applica le nuove impostazioni
                # Prima rimuovi le etichette esistenti per forzare l'aggiornamento
                layer.setLabelsEnabled(False)
                layer.setLabeling(None)
                
                # Poi applica le nuove impostazioni
                labeling = QgsVectorLayerSimpleLabeling(label_settings)
                layer.setLabeling(labeling)
                layer.setLabelsEnabled(True)
                layer.triggerRepaint()
                logging.info(f"Etichette aggiornate per layer: {layer.name()} - Nome: {self.name_text_color.name()}, Quota: {self.elevation_text_color.name()}")
        
        # Forza il refresh della canvas dopo aver aggiornato tutti i layer
        self.iface.mapCanvas().refresh()
    
    def update_labels_visibility(self):
        """Abilita o disabilita le etichette su tutti i layer di punti"""
        if self.labels_enabled:
            # Se le etichette sono abilitate, riconfigura tutto
            self.update_labels_on_layers()
        else:
            # Se le etichette sono disabilitate, disabilitale su tutti i layer di punti
            for layer in QgsProject.instance().mapLayers().values():
                if (layer.type() == QgsVectorLayer.VectorLayer and 
                    layer.geometryType() == QgsWkbTypes.PointGeometry):  # Tutti i layer di punti
                    
                    layer.setLabelsEnabled(False)
                    layer.triggerRepaint()
                    logging.info(f"Etichette disabilitate per layer: {layer.name()}")

    ############################################################################
    #                               TAB 5: INFO
    ############################################################################
    def init_info_tab(self):
        layout = QVBoxLayout()
        layout.setSpacing(10)  # Riduci spazio tra elementi
        
        # Add initial spacing from top
        layout.addSpacing(10)
        
        # Informazioni sul plugin (senza Contatto)
        info_label = QLabel(
            "<p><b>Versione:</b> 1.1 del 22 luglio 2025</p>"
            "<p><b>Autore:</b> <a href='mailto:solutop@gmail.com'>marcuzz0</a></p>"
            "<p><b>Codice:</b> <a href='https://github.com/marcuzz0/spotter'>Github repository</a></p>"
            "<p><b>Supporta:</b> puoi fare una donazione per supportare il progetto da  <a href='https://ko-fi.com/marcuzz0'>qui</a></p>"
            "<p><b>Licenza:</b> spotter viene distribuito sotto licenza <a href='https://github.com/marcuzz0/spotter/blob/main/LICENSE'>GPL-3.0 license</a></p>"
            "<p><b>Descrizione:</b> Il plugin spotter è uno strumento per QGIS progettato per semplificare il flusso di lavoro relativo all'importazione ed esportazione di dati geografici, focalizzandosi in particolare su file CSV e DXF</p>"
        )
        info_label.setOpenExternalLinks(True)
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        # Aggiungi stretch per posizionare il logo a metà tra descrizione e fine finestra
        layout.addStretch()
        
        # Aggiungere il logo del plugin (se presente)
        icon_path = os.path.join(os.path.dirname(__file__), "icon.png")
        if os.path.exists(icon_path):
            logo_label = QLabel()
            logo_label.setPixmap(QPixmap(icon_path).scaled(150, 150, Qt.KeepAspectRatio))
            logo_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(logo_label)
        
        # Aggiungi stretch finale
        layout.addStretch()
        
        self.info_tab.setLayout(layout)

    ############################################################################
    #        METODI GENERICI / GESTIONE TAB / CHIUSURA
    ############################################################################
    def reset_to_defaults(self):
        """Ripristina tutte le impostazioni ai valori di fabbrica"""
        reply = QMessageBox.question(
            self,
            'Conferma Ripristino',
            'Vuoi ripristinare tutte le impostazioni ai valori di fabbrica?\n\n'
            'Questo includerà:\n'
            '- Colori punti, linee e poligoni\n'
            '- Colori testi (nome e quota)\n'
            '- Stato etichette e tipo\n'
            '- Checkbox snap e finestra in primo piano\n'
            '- Campi numerici\n'
            '- Stili e colori dei layer attivi\n\n'
            'Questa azione non può essere annullata.',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            # Ripristina colori vettori
            self.point_color = QColor(255, 0, 0)  # Rosso
            self.line_color = QColor(20, 181, 255)  # #14b5ff
            self.polygon_color = QColor(0, 255, 0)  # #00ff00
            
            # Ripristina colori testi
            self.name_text_color = QColor(0, 0, 0)  # Nero
            self.elevation_text_color = QColor(255, 0, 255)  # Magenta #ff00ff
            
            # Ripristina stato etichette
            self.labels_enabled = True
            self.label_type = "name"
            
            # Ripristina checkbox
            self.stay_on_top_checkbox.setChecked(False)
            self.snap_checkbox.setChecked(True)
            self.labels_checkbox.setChecked(True)
            
            # Ripristina tipo etichetta
            index = self.label_type_combo.findData(self.label_type)
            if index >= 0:
                self.label_type_combo.setCurrentIndex(index)
            
            # Ripristina campi numerici al prossimo numero disponibile
            max_num = self.find_max_point_number()
            next_num = str(max_num + 1)
            self.rename_start_number.setText(next_num)
            self.start_vertex_number.setText(next_num)
            self.reference_elevation.setText("")
            
            # Ripristina campo quota
            self.selected_elevation_field = None
            
            # Aggiorna i pulsanti colore
            self.update_color_button()
            self.update_line_color_button()
            self.update_polygon_color_button()
            self.update_name_text_color_button()
            self.update_elevation_text_color_button()
            
            # Ripristina stili e colori dei layer attivi
            for layer in QgsProject.instance().mapLayers().values():
                if layer.type() == QgsVectorLayer.VectorLayer:
                    # Ripristina colore del simbolo in base al tipo di geometria
                    geometry_type = layer.geometryType()
                    renderer = layer.renderer()
                    if renderer and hasattr(renderer, 'symbol') and renderer.symbol():
                        if geometry_type == QgsWkbTypes.PointGeometry:
                            # Per i punti, crea un nuovo simbolo per forzare l'aggiornamento della legenda
                            symbol = QgsMarkerSymbol.createSimple({
                                'name': 'circle', 
                                'color': f'{self.point_color.red()},{self.point_color.green()},{self.point_color.blue()}',
                                'size': '2.5'
                            })
                            layer.setRenderer(QgsSingleSymbolRenderer(symbol))
                        elif geometry_type == QgsWkbTypes.LineGeometry:
                            # Per le linee, crea un nuovo simbolo
                            from qgis.core import QgsLineSymbol
                            symbol = QgsLineSymbol.createSimple({
                                'color': f'{self.line_color.red()},{self.line_color.green()},{self.line_color.blue()}',
                                'width': '0.5',
                                'line_style': 'solid'
                            })
                            layer.setRenderer(QgsSingleSymbolRenderer(symbol))
                        elif geometry_type == QgsWkbTypes.PolygonGeometry:
                            # Per i poligoni, crea un nuovo simbolo
                            from qgis.core import QgsFillSymbol
                            symbol = QgsFillSymbol.createSimple({
                                'color': '0,0,0,0',  # Riempimento trasparente
                                'outline_color': f'{self.polygon_color.red()},{self.polygon_color.green()},{self.polygon_color.blue()}',
                                'outline_width': '0.5',
                                'outline_style': 'solid'
                            })
                            layer.setRenderer(QgsSingleSymbolRenderer(symbol))
                        layer.triggerRepaint()
                    
                    # Ripristina etichette se il layer ha un campo nome personalizzato
                    if layer.customProperty('import_name_field'):
                        # Riapplica le etichette con i colori di default
                        if layer.labelsEnabled() and layer.labeling():
                            labeling = layer.labeling()
                            if hasattr(labeling, 'settings'):
                                settings = labeling.settings()
                                text_format = settings.format()
                                
                                # Ripristina colore in base al tipo di etichetta
                                if layer.customProperty('label_type') == 'elevation':
                                    text_format.setColor(self.elevation_text_color)
                                elif layer.customProperty('label_type') == 'both':
                                    # Per etichette combinate, mantieni il formato HTML ma aggiorna i colori
                                    field_name = settings.fieldName
                                    if 'concat(' in field_name and '<span style' in field_name:
                                        # Sostituisci i colori nell'espressione HTML
                                        import re
                                        # Sostituisci colore nome (primo span)
                                        field_name = re.sub(
                                            r'(<span style="color:\s*)([^"]+)(">[^<]+</span>)',
                                            lambda m: m.group(1) + self.name_text_color.name() + m.group(3),
                                            field_name,
                                            count=1
                                        )
                                        # Sostituisci colore quota (secondo span)
                                        field_name = re.sub(
                                            r'(<span style="color:\s*)([^"]+)(">[^<]+</span>)',
                                            lambda m: m.group(1) + self.elevation_text_color.name() + m.group(3),
                                            field_name,
                                            count=1,
                                            flags=re.DOTALL
                                        )
                                        settings.fieldName = field_name
                                else:
                                    text_format.setColor(self.name_text_color)
                                
                                settings.setFormat(text_format)
                                labeling = QgsVectorLayerSimpleLabeling(settings)
                                layer.setLabeling(labeling)
                                layer.triggerRepaint()
            
            # Aggiorna etichette su tutti i layer
            self.update_labels_on_layers()
            
            QMessageBox.information(
                self,
                "Completato",
                "Tutte le impostazioni sono state ripristinate ai valori di fabbrica."
            )
            
            logging.info("Impostazioni ripristinate ai valori di fabbrica")
    
    def closeEvent(self, event):
        """Gestisce la chiusura della finestra"""
        # Disconnetti i segnali per evitare riferimenti pendenti
        try:
            QgsProject.instance().layersRemoved.disconnect(self.on_layers_removed)
            self.iface.layerTreeView().currentLayerChanged.disconnect(self.on_active_layer_changed)
        except:
            pass
        
        # Chiama il metodo della classe padre
        super().closeEvent(event)
    
    def update_buttons_state(self):
        """Aggiorna lo stato dei pulsanti in base ai layer attivi"""
        # OTTIMIZZAZIONE: Controlla solo il layer attivo invece di tutti i layer
        active_layer = self.iface.activeLayer()
        has_vector_layers = False
        has_geometry_layers = False
        
        if active_layer and active_layer.type() == QgsVectorLayer.VectorLayer:
            has_vector_layers = True
            if active_layer.geometryType() in [QgsWkbTypes.LineGeometry, QgsWkbTypes.PolygonGeometry]:
                has_geometry_layers = True
        
        # Abilita/disabilita i pulsanti
        self.rename_vertices_button.setEnabled(has_vector_layers)
        self.extract_vertices_button.setEnabled(has_geometry_layers)
        self.set_elevation_button.setEnabled(has_vector_layers)
        
        # Abilita/disabilita i campi numerici e svuota se disabilitati
        self.rename_start_number.setEnabled(has_vector_layers)
        if not has_vector_layers:
            self.rename_start_number.clear()
            
        self.start_vertex_number.setEnabled(has_geometry_layers)
        if not has_geometry_layers:
            self.start_vertex_number.clear()
            
        self.reference_elevation.setEnabled(has_vector_layers)
        if not has_vector_layers:
            self.reference_elevation.clear()
            self.reference_elevation.setPlaceholderText("")  # Rimuove il placeholder
        else:
            self.reference_elevation.setPlaceholderText("0.00")  # Ripristina il placeholder
    
    def on_layers_removed(self, layer_ids):
        """Chiamato quando uno o più layer vengono rimossi dal progetto"""
        # Aggiorna la lista dei layer esportabili
        self.populate_export_layers()
        # Aggiorna lo stato dei pulsanti
        self.update_buttons_state()
        logging.info(f"Layer rimossi: {layer_ids}, lista export aggiornata")
    
    def on_active_layer_changed(self, layer):
        """Chiamato quando cambia il layer attivo"""
        # Aggiorna lo stato dei pulsanti
        self.update_buttons_state()
        
        if not layer:
            return
            
        # NON aggiornare le etichette quando si cambia layer per evitare rallentamenti
            
        # Se siamo nel tab Gestione, aggiorna i numeri in base al layer attivo
        if self.tabs.currentWidget() == self.dxf_tab:
            if (layer.type() == QgsVectorLayer.VectorLayer and 
                layer.geometryType() == QgsWkbTypes.PointGeometry):
                # Trova il numero massimo nel layer attivo
                max_num = 0
                name_field = layer.customProperty('import_name_field')
                if name_field:
                    for feature in layer.getFeatures():
                        try:
                            name_value = str(feature[name_field])
                            # Prova a estrarre un numero dal nome
                            import re
                            # Se il nome è solo un numero o inizia con un numero seguito da non-cifre
                            if name_value.isdigit():
                                num = int(name_value)
                                max_num = max(max_num, num)
                            else:
                                # Cerca un numero all'inizio della stringa
                                match = re.match(r'^(\d+)(?:\D|$)', name_value)
                                if match:
                                    num = int(match.group(1))
                                    max_num = max(max_num, num)
                        except:
                            continue
                
                # Aggiorna sempre i campi numerici con il prossimo numero disponibile
                self.start_vertex_number.setText(str(max_num + 1))
                self.rename_start_number.setText(str(max_num + 1))
                logging.info(f"Layer attivo cambiato a {layer.name()}, prossimo numero: {max_num + 1}")
    
    def on_tab_changed(self, index):
        tab_name = self.tabs.tabText(index)
        if tab_name == "Esporta CSV":
            self.populate_export_layers()
        elif tab_name == "Gestione":
            # Aggiorna lo stato dei pulsanti
            self.update_buttons_state()
            # Aggiorna i numeri basandosi sul layer attivo
            active_layer = self.iface.activeLayer()
            if active_layer:
                self.on_active_layer_changed(active_layer)
            else:
                # Se non c'è un layer attivo, usa il metodo esistente
                max_num = self.find_max_point_number()
                self.start_vertex_number.setText(str(max_num + 1))
                self.rename_start_number.setText(str(max_num + 1))
            # Connetti ai layer di punti per aggiornamenti automatici
            self.connect_to_point_layers()
            
            # OTTIMIZZAZIONE: Controlla solo il layer attivo per il campo quota
            found_elevation_field = False
            active_layer = self.iface.activeLayer()
            if (active_layer and 
                active_layer.type() == QgsVectorLayer.VectorLayer and 
                active_layer.geometryType() == QgsWkbTypes.PointGeometry):
                elevation_field = active_layer.customProperty('import_elevation_field')
                if elevation_field:
                    self.selected_elevation_field = elevation_field
                    found_elevation_field = True
            
            self.set_elevation_button.setEnabled(found_elevation_field)
        elif tab_name == "Impostazioni":
            # Non c'è più bisogno di aggiornare i campi quota qui
            pass

    def dragEnterEvent(self, event):
        """Gestisce l'evento di trascinamento file sopra la finestra"""
        logging.info("dragEnterEvent chiamato")
        logging.info(f"Mime types: {event.mimeData().formats()}")
        
        if event.mimeData().hasUrls():
            logging.info(f"URLs trovate: {len(event.mimeData().urls())}")
            # Controlla se almeno uno dei file è un CSV o DXF
            for url in event.mimeData().urls():
                logging.info(f"URL: {url.toString()}")
                logging.info(f"URL scheme: {url.scheme()}")
                logging.info(f"URL host: {url.host()}")
                logging.info(f"URL path: {url.path()}")
                
                file_path = url.toLocalFile()
                logging.info(f"toLocalFile: {file_path}")
                
                if not file_path:
                    file_path = url.toString()
                    logging.info(f"Using toString: {file_path}")
                
                # Accetta anche se il path ha il prefisso file://
                if file_path and (file_path.lower().endswith(('.csv', '.dxf')) or 
                                'file:' in file_path and ('.csv' in file_path.lower() or '.dxf' in file_path.lower())):
                    logging.info(f"Accetto file: {file_path}")
                    event.acceptProposedAction()
                    return
        
        # Prova anche con hasText per debug
        if event.mimeData().hasText():
            text = event.mimeData().text()
            logging.info(f"Testo trovato: {text}")
            if text and (text.lower().endswith(('.csv', '.dxf')) or 
                        'file:' in text and ('.csv' in text.lower() or '.dxf' in text.lower())):
                logging.info(f"Accetto testo come file: {text}")
                event.acceptProposedAction()
                return
                
        logging.info("Evento ignorato")
        event.ignore()
    
    def dragMoveEvent(self, event):
        """Gestisce il movimento durante il trascinamento"""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()
    
    def dropEvent(self, event):
        """Gestisce il rilascio del file"""
        logging.info("dropEvent chiamato")
        logging.info(f"Mime types disponibili: {event.mimeData().formats()}")
        
        file_path = None
        
        # Prima prova con URLs
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if urls:
                url = urls[0]  # Prendi il primo file
                logging.info(f"URL originale: {url.toString()}")
                
                # Usa il metodo standard di Qt per ottenere il percorso locale
                file_path = url.toLocalFile()
                logging.info(f"File path da toLocalFile(): {file_path}")
                
                # Se toLocalFile() non ha funzionato correttamente, prova con path()
                if not file_path:
                    file_path = url.path()
                    logging.info(f"File path da path(): {file_path}")
                
                # Se ancora vuoto, prova a estrarre dall'URL completo
                if not file_path:
                    url_string = url.toString()
                    logging.info(f"Provo a estrarre da URL string: {url_string}")
                    if url_string.startswith('file:'):
                        # Rimuovi il prefisso file:
                        if url_string.startswith('file:///'):
                            file_path = url_string[7:]  # Su Linux file:/// diventa /
                        elif url_string.startswith('file://'):
                            file_path = url_string[7:]
                        elif url_string.startswith('file:'):
                            file_path = url_string[5:]
                
                # Se il path è ancora nel formato URL, estrai il percorso
                if file_path and file_path.startswith('file:'):
                    # Gestisci diversi formati di URL file
                    if file_path.startswith('file:///'):
                        file_path = file_path[7:]  # Su Linux file:/// diventa /
                    elif file_path.startswith('file://'):
                        file_path = file_path[7:]  # Rimuovi 'file://' (7 caratteri)
                    elif file_path.startswith('file:'):
                        file_path = file_path[5:]  # Rimuovi 'file:' (5 caratteri)
                
                # Su Windows, potrebbe esserci un '/' extra all'inizio
                if os.name == 'nt' and file_path.startswith('/') and len(file_path) > 2 and file_path[2] == ':':
                    file_path = file_path[1:]
                
                # Su Linux, assicurati che il path inizi con /
                if os.name != 'nt' and file_path and not file_path.startswith('/'):
                    file_path = '/' + file_path
                
                logging.info(f"File path dopo pulizia: {file_path}")
                
                # Verifica che il file esista e sia valido
                if file_path and os.path.exists(file_path):
                    if file_path.lower().endswith('.csv'):
                        logging.info(f"File CSV trascinato: {file_path}")
                        event.acceptProposedAction()
                        
                        # Vai al tab di importazione CSV
                        self.tabs.setCurrentIndex(0)
                        
                        # Forza l'aggiornamento dell'UI
                        from qgis.PyQt.QtWidgets import QApplication
                        QApplication.processEvents()
                        
                        # Imposta il percorso del file
                        self.import_file_line_edit.setText(file_path)
                        logging.info(f"Percorso impostato nel campo: {self.import_file_line_edit.text()}")
                        
                        # Aggiorna automaticamente il nome del layer con il nome del file
                        base_name = os.path.splitext(os.path.basename(file_path))[0]
                        self.layer_name_line_edit.setText(base_name)
                        
                        # Forza un altro aggiornamento
                        QApplication.processEvents()
                        
                        # Piccolo ritardo per assicurare che l'UI sia aggiornata
                        from qgis.PyQt.QtCore import QTimer
                        
                        def load_with_error_handling():
                            try:
                                self.import_load_fields()
                            except Exception as e:
                                logging.error(f"Errore durante il caricamento dei campi: {e}")
                                import traceback
                                logging.error(traceback.format_exc())
                                QMessageBox.warning(self, "Errore", f"Errore durante il caricamento del file CSV:\n{str(e)}")
                        
                        QTimer.singleShot(100, load_with_error_handling)
                        
                        logging.info("Caricamento campi programmato")
                    elif file_path.lower().endswith('.dxf'):
                        # Vai al tab di importazione DXF
                        self.tabs.setCurrentIndex(2)
                        # Imposta il percorso del file
                        self.dxf_file_line_edit.setText(file_path)
                        # Simula il click sul file selezionato
                        self.dxf_path = file_path
                        # Carica il DXF
                        self.load_dropped_dxf(file_path)
                        event.acceptProposedAction()
                else:
                    logging.warning(f"File non trovato: {file_path}")
                    QMessageBox.warning(self, "Errore", f"File non trovato:\n{file_path}")
                    event.ignore()
                    return
            else:
                logging.warning("Nessun URL valido trovato")
        
        # Se non abbiamo trovato un path valido con URLs, prova con il testo (fallback per Linux)
        if not file_path and event.mimeData().hasText():
            text = event.mimeData().text()
            logging.info(f"Tentativo con testo: {text}")
            if text:
                # Pulisci il testo da eventuali prefissi file://
                if text.startswith('file:///'):
                    file_path = text[7:]  # Su Linux file:/// diventa /
                elif text.startswith('file://'):
                    file_path = text[7:]
                elif text.startswith('file:'):
                    file_path = text[5:]
                else:
                    file_path = text.strip()
                
                logging.info(f"File path da testo: {file_path}")
        
        # Se abbiamo un percorso valido, processalo
        if file_path and os.path.exists(file_path):
            if file_path.lower().endswith('.csv'):
                logging.info(f"File CSV trascinato: {file_path}")
                event.acceptProposedAction()
                
                # Vai al tab di importazione CSV
                self.tabs.setCurrentIndex(0)
                
                # Forza l'aggiornamento dell'UI
                from qgis.PyQt.QtWidgets import QApplication
                QApplication.processEvents()
                
                # Imposta il percorso del file
                self.import_file_line_edit.setText(file_path)
                logging.info(f"Percorso impostato nel campo: {self.import_file_line_edit.text()}")
                
                # Aggiorna automaticamente il nome del layer con il nome del file
                base_name = os.path.splitext(os.path.basename(file_path))[0]
                self.layer_name_line_edit.setText(base_name)
                
                # Forza un altro aggiornamento
                QApplication.processEvents()
                
                # Piccolo ritardo per assicurare che l'UI sia aggiornata
                from qgis.PyQt.QtCore import QTimer
                
                def load_with_error_handling():
                    try:
                        self.import_load_fields()
                    except Exception as e:
                        logging.error(f"Errore durante il caricamento dei campi: {e}")
                        import traceback
                        logging.error(traceback.format_exc())
                        QMessageBox.warning(self, "Errore", f"Errore durante il caricamento del file CSV:\n{str(e)}")
                
                QTimer.singleShot(100, load_with_error_handling)
                
                logging.info("Caricamento campi programmato")
            elif file_path.lower().endswith('.dxf'):
                logging.info(f"File DXF trascinato: {file_path}")
                event.acceptProposedAction()
                # Vai al tab di importazione DXF
                self.tabs.setCurrentIndex(2)
                # Imposta il percorso del file
                self.dxf_file_line_edit.setText(file_path)
                # Simula il click sul file selezionato
                self.dxf_path = file_path
                # Carica il DXF
                self.load_dropped_dxf(file_path)
        else:
            if file_path:
                logging.warning(f"File non trovato: {file_path}")
                QMessageBox.warning(self, "Errore", f"File non trovato:\n{file_path}")
            else:
                logging.warning("Nessun percorso file valido trovato")
            event.ignore()
    
    def load_dropped_dxf(self, path):
        """Carica il DXF trascinato"""
        # Carica layer DXF in modo temporaneo (senza aggiungerlo al progetto)
        temp_dxf_layer = QgsVectorLayer(path, "DXF_Temp", "ogr")
        
        if not temp_dxf_layer.isValid():
            QMessageBox.critical(self, "Errore", "Errore durante l'importazione del DXF.\nVerifica che il file sia un DXF valido.")
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
            
            # Chiedi se vuole posizionare il DXF sulla mappa
            reply = QMessageBox.question(
                self,
                "DXF Caricato",
                "Il file DXF è stato caricato correttamente.\n\nVuoi posizionarlo sulla mappa?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes
            )
            
            if reply == QMessageBox.Yes:
                self.start_placing_dxf()
    
    def connect_to_point_layers(self):
        """Connette ai layer di punti per aggiornare il contatore quando vengono aggiunti punti"""
        # Prima disconnetti i segnali esistenti
        for layer_id, connection in self.layer_connections.items():
            try:
                layer = QgsProject.instance().mapLayer(layer_id)
                if layer:
                    layer.committedFeaturesAdded.disconnect(connection)
            except:
                pass
        
        self.layer_connections.clear()
        
        # Connetti ai nuovi layer di punti
        for layer in QgsProject.instance().mapLayers().values():
            if (layer.type() == QgsVectorLayer.VectorLayer and 
                layer.geometryType() == QgsWkbTypes.PointGeometry):
                # Connetti al segnale committedFeaturesAdded
                connection = layer.committedFeaturesAdded.connect(
                    lambda layer_id, features: self.on_features_added()
                )
                self.layer_connections[layer.id()] = connection
    
    def on_features_added(self):
        """Chiamato quando vengono aggiunte nuove features a un layer di punti"""
        # Aggiorna il contatore solo se siamo nel tab DXF
        if self.tabs.currentWidget() == self.dxf_tab:
            max_num = self.find_max_point_number()
            # Aggiorna sempre i campi con il prossimo numero disponibile
            self.start_vertex_number.setText(str(max_num + 1))
            self.rename_start_number.setText(str(max_num + 1))
            logging.info(f"Contatore aggiornato dopo aggiunta punti: {max_num + 1}")
    
    
    
    def start_elevation_reference(self):
        """Avvia il processo di selezione del punto di riferimento per le quote"""
        # Verifica che ci sia almeno un layer con campo quota configurato
        found_elevation_field = False
        for layer in QgsProject.instance().mapLayers().values():
            if (layer.type() == QgsVectorLayer.VectorLayer and 
                layer.geometryType() == QgsWkbTypes.PointGeometry):
                elevation_field = layer.customProperty('import_elevation_field')
                if elevation_field and elevation_field in layer.fields().names():
                    found_elevation_field = True
                    break
        
        if not found_elevation_field:
            QMessageBox.warning(
                self, 
                "Campo quota non configurato", 
                "Nessun layer ha un campo quota configurato.\n\n"
                "Durante l'importazione CSV, seleziona il campo quota (Hei)."
            )
            return
            
        try:
            reference_elev = float(self.reference_elevation.text())
        except ValueError:
            QMessageBox.warning(self, "Errore", "Inserisci un valore numerico valido per la quota di riferimento")
            return
            
        # Abilita lo snap su tutto
        snapping_config = QgsProject.instance().snappingConfig()
        snapping_config.setEnabled(True)
        snapping_config.setMode(QgsSnappingConfig.AllLayers)
        snapping_config.setType(QgsSnappingConfig.VertexAndSegment)  # Snap su vertici e segmenti
        snapping_config.setTolerance(20)  # Aumenta la tolleranza per facilitare lo snap
        snapping_config.setUnits(QgsTolerance.Pixels)
        try:
            snapping_config.setIntersectionSnapping(True)  # Abilita anche snap alle intersezioni
        except AttributeError:
            pass
        QgsProject.instance().setSnappingConfig(snapping_config)
        
        # Forza l'aggiornamento dello snapping utils del canvas
        self.iface.mapCanvas().snappingUtils().setConfig(snapping_config)
        self.iface.mapCanvas().refresh()
        
        # Crea map tool per selezionare il punto di riferimento
        self.elevation_map_tool = ElevationReferenceTool(self.iface.mapCanvas())
        self.elevation_map_tool.pointClicked.connect(
            lambda point: self.set_elevation_reference(point, reference_elev)
        )
        self.iface.mapCanvas().setMapTool(self.elevation_map_tool)
        
        QMessageBox.information(
            self, 
            "Seleziona punto di riferimento", 
            f"Clicca su un punto nella mappa per impostarlo come riferimento.\n"
            f"La sua quota sarà impostata a {reference_elev:.3f} e tutti gli altri punti "
            f"saranno ricalcolati di conseguenza."
        )
    
    def set_elevation_reference(self, clicked_point, new_elevation):
        """Imposta il punto di riferimento e ricalcola tutte le quote"""
        # Definisci una soglia di distanza (in unità mappa) per cercare i punti vicini
        canvas = self.iface.mapCanvas()
        
        # Ottieni il CRS della mappa
        map_crs = canvas.mapSettings().destinationCrs()
        
        logging.info(f"Map CRS (OTF): {map_crs.authid()}")
        
        # Trova tutti i punti entro il raggio di ricerca
        nearby_points = []
        
        # Prima controlla il layer attivo
        active_layer = self.iface.activeLayer()
        layers_to_check = []
        
        # Se il layer attivo è valido, controllalo per primo
        if (active_layer and 
            active_layer.type() == QgsVectorLayer.VectorLayer and 
            active_layer.geometryType() == QgsWkbTypes.PointGeometry):
            # Verifica se ha un campo elevation nelle proprietà personalizzate
            elevation_field = active_layer.customProperty('import_elevation_field')
            if elevation_field and elevation_field in active_layer.fields().names():
                layers_to_check.append(active_layer)
        
        # Poi aggiungi gli altri layer
        for layer in QgsProject.instance().mapLayers().values():
            if (layer != active_layer and
                layer.type() == QgsVectorLayer.VectorLayer and 
                layer.geometryType() == QgsWkbTypes.PointGeometry):
                # Verifica se ha un campo elevation nelle proprietà personalizzate
                elevation_field = layer.customProperty('import_elevation_field')
                if elevation_field and elevation_field in layer.fields().names():
                    layers_to_check.append(layer)
        
        for layer in layers_to_check:
            # Ottieni il CRS del layer
            layer_crs = layer.crs()
            logging.info(f"Layer {layer.name()} CRS: {layer_crs.authid()}")
            
            # Calcola il raggio di ricerca in base al CRS del LAYER (non della mappa)
            if layer_crs.isGeographic():
                # Sistema geografico (lat/lon in gradi) - es. EPSG:4326
                search_radius = 0.00005  # Circa 5 metri
            else:
                # Sistema proiettato (probabilmente in metri)
                search_radius = 5.0  # 5 metri
            
            # Trasforma il punto cliccato dal CRS della mappa al CRS del layer
            clicked_point_in_layer_crs = clicked_point
            if layer_crs != map_crs:
                transform = QgsCoordinateTransform(map_crs, layer_crs, QgsProject.instance())
                clicked_point_in_layer_crs = transform.transform(clicked_point)
                logging.info(f"Trasformazione click da {map_crs.authid()} a {layer_crs.authid()}")
            
            # Campo nome per identificare i punti
            name_field = layer.customProperty('import_name_field')
            if not name_field:
                # Cerca un campo nome comune
                for field_name in ['nome', 'name', 'id', 'punto', 'point']:
                    if field_name in [f.name().lower() for f in layer.fields()]:
                        for field in layer.fields():
                            if field.name().lower() == field_name:
                                name_field = field.name()
                                break
                        break
            
            # Recupera il campo elevation specifico del layer
            elevation_field = layer.customProperty('import_elevation_field')
            if not elevation_field:
                continue  # Skip layer se non ha campo elevation
            
            for feature in layer.getFeatures():
                geom = feature.geometry()
                if geom:
                    point = geom.asPoint()
                    
                    # Calcola la distanza nel CRS del layer
                    distance = clicked_point_in_layer_crs.distance(point)
                    if distance <= search_radius:
                        point_info = {
                            'feature': feature,
                            'layer': layer,
                            'distance': distance,
                            'name': str(feature[name_field]) if name_field else str(feature.id()),
                            'elevation': feature[elevation_field],
                            'elevation_field': elevation_field,  # Salva il nome del campo per uso successivo
                            'point': point,
                            'is_active_layer': layer == active_layer
                        }
                        nearby_points.append(point_info)
        
        logging.info(f"Trovati {len(nearby_points)} punti vicini al click")
        
        if not nearby_points:
            # Prova a trovare il punto più vicino senza limite di distanza per dare un feedback migliore
            closest_point = None
            min_distance = float('inf')
            
            for layer in QgsProject.instance().mapLayers().values():
                if (layer.type() == QgsVectorLayer.VectorLayer and 
                    layer.geometryType() == QgsWkbTypes.PointGeometry):
                    # Verifica se ha un campo elevation nelle proprietà personalizzate
                    elevation_field = layer.customProperty('import_elevation_field')
                    if not elevation_field or elevation_field not in layer.fields().names():
                        continue
                    
                    # Ottieni il CRS del layer
                    layer_crs = layer.crs()
                    
                    # Trasforma il punto cliccato nel CRS del layer
                    clicked_point_in_layer_crs = clicked_point
                    if layer_crs != map_crs:
                        transform = QgsCoordinateTransform(map_crs, layer_crs, QgsProject.instance())
                        clicked_point_in_layer_crs = transform.transform(clicked_point)
                    
                    for feature in layer.getFeatures():
                        geom = feature.geometry()
                        if geom:
                            point = geom.asPoint()
                            
                            # Calcola la distanza nel CRS del layer
                            distance = clicked_point_in_layer_crs.distance(point)
                            if distance < min_distance:
                                min_distance = distance
                                closest_point = point
            
            if closest_point:
                # Determina l'unità di misura in base al tipo di CRS
                if layer_crs and layer_crs.isGeographic():
                    unit_str = "gradi"
                    # Converti in metri approssimativi per dare un'idea
                    min_distance_meters = min_distance * 111000  # approssimazione
                    extra_info = f" (circa {min_distance_meters:.0f} metri)"
                else:
                    unit_str = "metri"
                    extra_info = ""
                
                QMessageBox.warning(
                    self, 
                    "Nessun punto trovato", 
                    f"Nessun punto trovato entro {search_radius:.4f} {unit_str}.\n"
                    f"Il punto più vicino è a {min_distance:.4f} {unit_str}{extra_info}.\n"
                    f"Clicca più vicino a un punto."
                )
            else:
                QMessageBox.warning(
                    self, 
                    "Nessun punto trovato", 
                    "Nessun layer di punti con campo quota trovato."
                )
            return
        
        # Ordina per distanza
        nearby_points.sort(key=lambda x: x['distance'])
        
        # Se c'è solo un punto, usalo direttamente
        if len(nearby_points) == 1:
            self.apply_elevation_reference(nearby_points[0], new_elevation)
        else:
            # Mostra una finestra di selezione non modale
            self.show_point_selection_dialog(nearby_points, new_elevation)
    
    def show_point_selection_dialog(self, nearby_points, new_elevation):
        """Mostra una finestra di selezione punti non modale"""
        from qgis.PyQt.QtWidgets import QDialog, QVBoxLayout, QListWidget, QDialogButtonBox, QListWidgetItem
        
        # Disabilita la finestra principale di Spotter
        self.setEnabled(False)
        
        dialog = QDialog(self)
        dialog.setWindowTitle("Seleziona punto di riferimento")
        dialog.setWindowModality(Qt.NonModal)  # Non blocca altre finestre
        dialog.setWindowFlags(
            Qt.Window |  # Finestra normale
            Qt.WindowTitleHint |  # Mostra titolo
            Qt.WindowCloseButtonHint |  # Pulsante chiudi
            Qt.WindowStaysOnTopHint  # Resta sopra ma non blocca
        )
        layout = QVBoxLayout()
        
        label = QLabel(f"Trovati {len(nearby_points)} punti vicini. Seleziona il punto di riferimento:")
        layout.addWidget(label)
        
        list_widget = QListWidget()
        for point_info in nearby_points[:10]:  # Mostra massimo 10 punti
            distance_m = point_info['distance']
            # Determina l'unità appropriata
            layer = point_info['layer']
            if layer.crs().isGeographic():
                distance_str = f"{distance_m:.6f} gradi"
            else:
                distance_str = f"{distance_m:.2f} m"
            item_text = f"{point_info['name']} - Quota: {point_info['elevation']} - Distanza: {distance_str}"
            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, point_info)
            list_widget.addItem(item)
        
        if len(nearby_points) > 0:
            list_widget.setCurrentRow(0)  # Seleziona il più vicino di default
        
        layout.addWidget(list_widget)
        
        # Funzione per gestire OK
        def on_ok_clicked():
            current_item = list_widget.currentItem()
            if current_item:
                selected_point = current_item.data(Qt.UserRole)
                self.apply_elevation_reference(selected_point, new_elevation)
            self.setEnabled(True)  # Riabilita la finestra principale
            dialog.close()
        
        # Funzione per gestire Cancel
        def on_cancel_clicked():
            self.setEnabled(True)  # Riabilita la finestra principale
            dialog.close()
        
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(on_ok_clicked)
        buttons.rejected.connect(on_cancel_clicked)
        layout.addWidget(buttons)
        
        dialog.setLayout(layout)
        
        # Gestisci la chiusura con X button
        def on_dialog_closed():
            self.setEnabled(True)  # Riabilita la finestra principale
        
        dialog.finished.connect(on_dialog_closed)
        
        dialog.show()  # Usa show() invece di exec_() per non bloccare
    
    def apply_elevation_reference(self, selected_point, new_elevation):
        """Applica il riferimento di quota al punto selezionato"""
        # Usa il punto selezionato
        closest_feature = selected_point['feature']
        closest_layer = selected_point['layer']
        old_elevation = selected_point['elevation']
        point_name = selected_point.get('name', 'Senza nome')
        elevation_field = selected_point.get('elevation_field')  # Recupera il campo elevation specifico
            
        # Calcola il delta quota
        try:
            old_elev = float(old_elevation) if old_elevation is not None else 0
            elevation_delta = new_elevation - old_elev
        except (ValueError, TypeError):
            QMessageBox.warning(self, "Errore", "Il punto selezionato non ha una quota valida")
            return
            
        # Chiedi conferma con finestra sempre in primo piano
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle('Conferma aggiornamento quote')
        msg_box.setText(
            f'Punto {point_name} con quota attuale: {old_elev:.3f}\n'
            f'Nuova quota di riferimento: {new_elevation:.3f}\n'
            f'Delta da applicare: {elevation_delta:+.3f}\n\n'
            f'Vuoi aggiornare tutte le quote del layer "{closest_layer.name()}"?'
        )
        msg_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        msg_box.setDefaultButton(QMessageBox.No)
        msg_box.setWindowFlags(msg_box.windowFlags() | Qt.WindowStaysOnTopHint)
        reply = msg_box.exec()
        
        if reply != QMessageBox.Yes:
            return
            
        # Aggiorna solo le quote del layer selezionato
        updated_count = 0
        
        # Se non abbiamo il campo elevation dal punto selezionato, recuperalo dalle proprietà del layer
        if not elevation_field:
            elevation_field = closest_layer.customProperty('import_elevation_field')
        
        if not elevation_field:
            QMessageBox.warning(self, "Errore", "Il layer non ha un campo quota configurato")
            return
            
        if not closest_layer.isEditable():
            closest_layer.startEditing()
            
        field_idx = closest_layer.fields().indexOf(elevation_field)
        
        # Aggiorna TUTTE le feature del layer selezionato
        for feature in closest_layer.getFeatures():
            old_value = feature[elevation_field]
            if old_value is not None:
                try:
                    old_val = float(old_value)
                    new_val = round(old_val + elevation_delta, 3)  # Arrotonda a 3 decimali
                    closest_layer.changeAttributeValue(feature.id(), field_idx, new_val)
                    updated_count += 1
                except (ValueError, TypeError):
                    continue
        
        closest_layer.commitChanges()
        closest_layer.triggerRepaint()
        # Non riavviare automaticamente la modalità di modifica
        # closest_layer.startEditing()
        
        QMessageBox.information(
            self,
            "Completato",
            f"Aggiornate le quote di {updated_count} punti nel layer '{closest_layer.name()}'.\n"
            f"Delta applicato: {elevation_delta:+.3f}"
        )
        
        # Disabilita il map tool
        self.iface.mapCanvas().unsetMapTool(self.elevation_map_tool)
        self.elevation_map_tool = None
    
    def reorder_layers(self):
        """Riordina i layer: mappe in fondo, poi poligoni, poi linee, poi punti in cima"""
        root = QgsProject.instance().layerTreeRoot()
        
        # Raccogli i layer per tipo
        point_layers = []
        line_layers = []
        polygon_layers = []
        raster_layers = []  # Layer raster (mappe)
        other_layers = []
        
        for layer in QgsProject.instance().mapLayers().values():
            if layer.type() == QgsVectorLayer.VectorLayer:
                if layer.geometryType() == QgsWkbTypes.PointGeometry:
                    point_layers.append(layer)
                elif layer.geometryType() == QgsWkbTypes.LineGeometry:
                    line_layers.append(layer)
                elif layer.geometryType() == QgsWkbTypes.PolygonGeometry:
                    polygon_layers.append(layer)
                else:
                    other_layers.append(layer)
            elif layer.type() == 1:  # QgsRasterLayer type value
                raster_layers.append(layer)
            else:
                other_layers.append(layer)
        
        # Riordina: mappe in fondo, poi poligoni, poi linee, poi punti in cima
        # L'ordine nella lista sarà invertito perché insertChildNode(0) mette all'inizio
        order = raster_layers + other_layers + polygon_layers + line_layers + point_layers
        
        # Applica il nuovo ordine inserendo dal fondo verso l'alto
        for layer in order:
            layer_node = root.findLayer(layer.id())
            if layer_node:
                clone = layer_node.clone()
                parent = layer_node.parent()
                parent.insertChildNode(0, clone)
                parent.removeChildNode(layer_node)
    
    def close_dialog(self):
        # Disconnetti tutti i segnali prima di chiudere
        for layer_id, connection in self.layer_connections.items():
            try:
                layer = QgsProject.instance().mapLayer(layer_id)
                if layer:
                    layer.committedFeaturesAdded.disconnect(connection)
            except:
                pass
        
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
        # Ottieni le coordinate del punto cliccato
        click_point = self.toMapCoordinates(event.pos())
        
        # Verifica lo stato dello snapping
        snapping_config = QgsProject.instance().snappingConfig()
        print(f"Snapping enabled: {snapping_config.enabled()}")
        print(f"Snapping mode: {snapping_config.mode()}")
        print(f"Snapping type: {snapping_config.type()}")
        
        # Prova a fare snap al punto
        snapping_utils = self.canvas.snappingUtils()
        snap_match = snapping_utils.snapToMap(click_point)
        
        final_point = click_point
        if snap_match.isValid():
            # Usa il punto snappato
            final_point = snap_match.point()
            snap_type = "unknown"
            if snap_match.hasVertex():
                snap_type = "vertex"
            elif snap_match.hasEdge():
                snap_type = "edge"
            elif snap_match.hasArea():
                snap_type = "area"
            print(f"Snapped to {snap_type} at: {final_point.x()}, {final_point.y()}")
        else:
            print(f"No snap, using click point: {final_point.x()}, {final_point.y()}")
            
        self.pointClicked.emit(final_point)
        # Disabilita il map tool dopo il click
        self.canvas.unsetMapTool(self)


###############################################################################
# MAP TOOL PER SELEZIONARE IL PUNTO DI RIFERIMENTO PER LE QUOTE
###############################################################################
class ElevationReferenceTool(QgsMapToolEmitPoint):
    pointClicked = pyqtSignal(QgsPointXY)
    
    def __init__(self, canvas):
        super().__init__(canvas)
        self.canvas = canvas
    
    def canvasReleaseEvent(self, event):
        # Ottieni le coordinate del punto cliccato
        point = self.toMapCoordinates(event.pos())
        
        # Configura lo snapping utils
        snapping_utils = self.canvas.snappingUtils()
        
        # Prova a fare snap
        snap_match = snapping_utils.snapToMap(point)
        
        if snap_match.isValid():
            # Usa il punto snappato
            point = snap_match.point()
            print(f"Snapped to point: {point.x()}, {point.y()}")
        else:
            print(f"No snap, using click point: {point.x()}, {point.y()}")
            
        self.pointClicked.emit(point)
        # Disabilita il map tool dopo il click
        self.canvas.unsetMapTool(self)


###############################################################################
# FUNZIONE DI AVVIO DELLA FINESTRA DI DIALOGO
###############################################################################
dialog_ref = None

def run_dialog():
    global dialog_ref
    # 'iface' deve essere disponibile (in QGIS lo è di default)
    dialog_ref = CombinedCsvDialog(iface)
    dialog_ref.show()