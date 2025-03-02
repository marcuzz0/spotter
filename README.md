# Che cos'è?

Il plugin Open Source spotter è uno strumento per QGIS progettato per semplificare il flusso di lavoro relativo all’importazione ed esportazione di dati geografici, focalizzandosi in particolare su file CSV e DXF.

# Funzionalità Principali

- Importa CSV: consente di importare dati da file CSV, configurare i campi da utilizzare e creare un layer georeferenziato
- Esporta CSV: permette di selezionare un layer esistente nel progetto, scegliere i campi da esportare, impostare il sistema di coordinate e salvare i dati in un nuovo file CSV
- Importa DXF: fornisce strumenti per caricare file DXF, verificare la validità delle geometrie e posizionare il contenuto sulla mappa mediante un tool interattivo (clic sulla mappa)
- Info: mostra le informazioni sul plugin, inclusi dettagli sulla versione, autore, descrizione, licenza e link utili. Qui è possibile anche integrare i metodi di donazione e altre risorse di supporto


# Come si usa?

## Installazione:
Il plugin viene distribuito come un file ZIP con una struttura di cartella corretta. Dopo averlo installato tramite il gestore plugin di QGIS, apparirà un’icona e/o una voce di menu associata a «spotter». Puoi scaricare il file zippato direttamente dalla sezione release

## Avvio del Plugin:

Cliccando sull’icona o selezionando il plugin dal menu, si apre la finestra di dialogo con i vari tab.

## Flusso di Lavoro:

- Per importare dati CSV: Seleziona il file, configura i campi, e importa. Il layer verrà aggiunto al progetto e potrai modificarlo direttamente
- Per esportare dati: Scegli il layer da esportare, configura i parametri e salva il file CSV con le coordinate trasformate se necessario
- Per importare DXF: Seleziona il file DXF, verifica le geometrie e posiziona il contenuto sulla mappa cliccando nel punto desiderato.
- Informazioni e Supporto: Nel tab Info trovi tutte le informazioni sul plugin, inclusi link per donazioni o per contattare l’autore.

## Test:

Sono disponibili nella cartella esempi tre file per fare dei test:
- **test_ch.csv** (file *.csv con header)
- **test_ch.csv** (file *.csv senza header)
- **123.dxf** (oggetto poligonale in *.dxf)
  
# Architettura

Il plugin è strutturato in più file per separare le diverse componenti:

- **main.py**: contiene la definizione della classe CombinedCsvDialog, che gestisce l’interfaccia utente e tutte le funzionalità. Qui sono definiti i metodi per ciascun tab (importazione CSV, esportazione CSV, importazione DXF, tab Info) e le relative logiche operative.

- **spotter_plugin.py**: definisce la classe principale SpotterPlugin che integra il dialogo nel ciclo di vita del plugin QGIS. Qui vengono gestiti l’inizializzazione, l’aggiunta dell’azione all’interfaccia e la gestione dell’avvio e della chiusura del plugin.

- **__init__.py**: contiene la funzione classFactory(iface) che espone il plugin a QGIS. Questa funzione importa la classe SpotterPlugin e la restituisce, consentendo a QGIS di inizializzare il plugin correttamente.
- Altri file (opzionali): Sono inclusi file di risorse (come icon.png per l’icona) e file di licenza (come LICENSE) per documentare la licenza del plugin.


