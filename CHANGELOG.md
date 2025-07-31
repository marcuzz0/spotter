# CHANGELOG

## [1.1.0] - 2025-01-31

### 🎉 Novità
- **Riproiezione automatica a EPSG:3857**: Tutti i layer importati vengono automaticamente riproiettati per uniformità
- **Eredità colori intelligente**: I nuovi layer CSV ereditano automaticamente i colori dai layer esistenti
- **Persistenza colori**: I colori delle etichette vengono rilevati e mantenuti tra le sessioni
- **Pulsante Ripristina Default**: Nuovo pulsante per ripristinare tutte le impostazioni ai valori di fabbrica
- **Numerazione intelligente**: Il ripristino default legge automaticamente l'ultimo numero dai layer attivi

### 🐛 Correzioni
- Finestra conferma elevazione ora resta sempre in primo piano sopra altre finestre
- Funzione "Rinomina Punti" corretta con ordinamento spaziale (sinistra→destra, basso→alto)
- Campo numero iniziale per "Estrai Vertici" ora modificabile e mantiene il valore inserito
- Risolto problema etichette vuote in modalità Nome+Quota
- Corretti errori di indentazione che causavano malfunzionamenti
- Eliminati rallentamenti con progetti contenenti molti layer
- Fix calcolo distanze per diversi sistemi di coordinate

### 🔧 Miglioramenti
- Ottimizzazione performance: controllo solo del layer attivo dove possibile
- Migliorata gestione errori con messaggi più chiari
- Aggiornamento mirato delle etichette per migliori prestazioni
- Supporto migliorato per layer CSV con strutture diverse

---

## [1.0.0] - 2025-01-28

### 📋 Funzionalità Base

#### Importazione CSV
- Supporto file CSV con/senza header
- Rilevamento automatico delimitatore
- Selezione campi personalizzata
- Supporto coordinate DMS e decimali
- Layer temporanei editabili

#### Esportazione CSV
- Export layer punti in CSV
- Opzione header incluso/escluso
- Selezione CRS output
- Headers intelligenti (est/nord, lon/lat)
- Formattazione coordinate automatica

#### Importazione DXF
- Supporto linee e poligoni
- Posizionamento interattivo con click
- Snap automatico attivo
- Trasformazione coordinate al volo

#### Gestione Etichette
- Tre modalità: Nome, Quota, Nome+Quota
- Etichette HTML con colori personalizzabili
- Buffer bianco per leggibilità
- Aggiornamento automatico al cambio layer

#### Gestione Quote
- Punto di riferimento con quota nota
- Ricalcolo automatico quote layer
- Ricerca punti vicini (raggio 5m)
- Conferma con nome punto

#### Rinomina Punti
- Rinumerazione progressiva punti selezionati
- Numerazione basata su massimo esistente
- Supporto selezione multipla
- Solo su layer punti attivo

#### Estrai Vertici
- Estrazione da linee/poligoni
- Aggiunta a layer CSV destinazione
- Numerazione progressiva
- Evita duplicati vertici condivisi

#### Gestione Colori
- Colori personalizzabili per geometrie
- Colori separati nome/quota
- Applicazione a tutti i layer CSV
- Interfaccia intuitiva con preview

#### Interfaccia
- 4 tab organizzati: Import CSV, Export CSV, Import DXF, Info
- Tab Gestione per controlli avanzati
- Finestra singleton (istanza unica)
- Aggiornamento automatico contenuti

#### Ordinamento Layer
- Ordine automatico: Punti→Linee→Poligoni→Raster
- Mappe base sempre in fondo
- Riordino dopo ogni operazione

### 🔧 Requisiti Tecnici
- QGIS 3.0+
- Python 3.x
- PyQt5

### 📝 Note Tecniche
- Pattern singleton per stabilità
- Logging dettagliato per debug
- Gestione errori robusta
- Ottimizzato per grandi dataset