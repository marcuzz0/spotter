import os
from qgis.PyQt.QtCore import QCoreApplication
from qgis.PyQt.QtWidgets import QAction, QMessageBox
from qgis.PyQt.QtGui import QIcon

# Importa la tua finestra di dialogo, ad esempio se è in main.py
from .main import CombinedCsvDialog

class SpotterPlugin:
    def __init__(self, iface):
        """Costruttore del plugin."""
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.action = None
        self.dialog = None

    def tr(self, message):
        """Metodo per la traduzione dei testi."""
        return QCoreApplication.translate("spotter", message)

    def initGui(self):
        """Inizializza l'interfaccia grafica del plugin aggiungendo l'azione."""
        icon_path = os.path.join(self.plugin_dir, "icon.png")
        self.action = QAction(QIcon(icon_path), self.tr("spotter"), self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToMenu(self.tr("&spotter"), self.action)

    def unload(self):
        """Rimuove l'azione quando il plugin viene disabilitato o chiuso."""
        self.iface.removePluginMenu(self.tr("&spotter"), self.action)
        self.iface.removeToolBarIcon(self.action)
        
        # Chiudi la finestra se è aperta
        if self.dialog is not None:
            self.dialog.close()
            self.dialog = None

    def run(self):
        """Esegue il plugin, mostrando la finestra di dialogo."""
        try:
            # Se la finestra esiste già, la porta in primo piano
            if self.dialog is not None:
                self.dialog.raise_()
                self.dialog.activateWindow()
                self.dialog.show()
            else:
                # Crea una nuova finestra solo se non esiste
                self.dialog = CombinedCsvDialog(self.iface)
                # Connetti il segnale di chiusura per resettare il riferimento
                self.dialog.finished.connect(self.on_dialog_closed)
                self.dialog.show()
        except Exception as e:
            QMessageBox.critical(self.iface.mainWindow(), self.tr("Errore"), str(e))
    
    def on_dialog_closed(self):
        """Chiamato quando la finestra viene chiusa."""
        self.dialog = None

