# Analisi del Repository e dei Dati (`data/`)

**Progetto:** Operator Copilot — Milestone 1 (RAG Engine)  
**Data analisi:** 2026-11-11  
**Metodo:** Scansione automatica completa tramite [`scripts/analyze_data.py`](../scripts/analyze_data.py) e ispezione diretta dei campioni rappresentativi.

---

## 1. Stato del Repository Esistente (Pre-Implementazione)

Dall'ispezione della root del repository prima dell'avvio della Milestone 1 risultano presenti:
- Un prototipo sperimentale precedente in **Node.js / JavaScript** (`package.json`, `Dockerfile`, `docker-compose.yml`, `README.md`, `src/*.js`).
- **Nessun codice Python**, nessun ambiente virtuale, nessun database relazionale (SQLite/PostgreSQL), nessun vector store popolato (Chroma/FAISS) e nessun file `.env`.
- La cartella `data/` contenente l'intero corpus documentale aziendale in formato Markdown.

> Il prototipo Node.js preesistente non viene modificato né eliminato; la nuova implementazione **Operator Copilot (Python 3.11+, LangChain, FastAPI)** viene strutturata in modo pulito e modulare sotto `src/operator_copilot/`, `scripts/`, `tests/`, `docs/` e `storage/`.

---

## 2. Struttura e Volumetria di `data/`

| Metrica | Valore Misurato |
| :--- | :--- |
| **File totali** | **1.532** |
| **Estensioni presenti** | `.md` (1.532 file — **100%**) |
| **Formati assenti** | PDF, DOCX, DOC, TXT, HTML, CSV, XLSX, JSON (0 file) |
| **Sottocartelle totali** | **143** (raggruppate in **49 aree tematiche** numerate `01`..`59` + file root `INDEX.md`) |
| **Dimensione complessiva** | **10.562.497 byte (~10,07 MB)** |
| **File leggibili (UTF-8)** | **1.532 / 1.532 (100%)** |
| **File non leggibili / corrotti** | **0** |
| **File vuoti (0 byte o soli spazi)** | **0** |
| **Errori di encoding** | **0** (tutti decodificati correttamente in UTF-8) |

### Distribuzione delle Aree Principali
Le aree più dense del corpus riguardano la suite gestionale per la Pubblica Amministrazione (**Cityware / Cityware Online — CWOL**, Palitalsoft):
- `03 - SERVIZI DEMOGRAFICI`: **399 file** (Anagrafe, Elettorale, Stato Civile, ANPR, ANSC, AIRE)
- `10 - Area Economico - Finanziaria`: **169 file** (Bilancio, Contabilità, Entrate, Uscite, Controllo di Gestione)
- `15 - Codice della Strada`: **147 file** (Verbali, Ruoli, Ricorsi, Notifiche)
- `27 - Comunicazioni`: **128 file** (Circolari tecniche dal 2019 al 2025/2026)
- `05 - Segreteria degli Atti`: **107 file** (Determine, Delibere, Decreti, Pubblicazioni)
- `12 - Sportelli (SUAP - SUE - Servizi)`: **69 file**
- `09 - Timbrature`: **65 file** (include il manuale da 91 KB `manuale_timbrature.md`)
- `14 - P@rtecipo`: **60 file**
- `04 - Protocollo`: **55 file**
- `46 - Manuali IMU` (39 file), `49 - Manuali TARI` (38 file), `11 - Tributi` (26 file), `16 - Illeciti Amministrativi` (25 file), `43 - Manuali Bilancio` (23 file), `50 - Manuali Uscite` (21 file), `08 - Registro Notifiche` (20 file), `54 - Parametri Workflow` (15 file), oltre ad altre aree minori (AppIO, AVCP-L190, ZTL, Opere Pubbliche, FAQ, Slide, Webinar, ecc.).

---

## 3. Statistiche sulla Lunghezza e Struttura dei Documenti

| Statistica | Caratteri | Parole |
| :--- | ---: | ---: |
| **Minimo** | 301 | 45 |
| **25° percentile** | 1.956 | — |
| **Mediana** | 3.760,5 | 542 |
| **Media** | 6.752,9 | 959,3 |
| **75° percentile** | 8.122 | — |
| **95° percentile** | 22.236 | 3.170 |
| **Massimo** | 452.233 (`INDEX.md`) | 58.623 |

- **File molto lunghi (>30.000 caratteri):** **18 file** (es. `INDEX.md` da 452 KB, `manuale_timbrature.md` da 91,7 KB, `2025_manuale_coge_cwol.md` da 50,2 KB, `manuale_modulo_cwol_lavori_pubblici.md` da 46,2 KB).
- **Intestazioni Markdown (`#`, `##`, `###`):** presenti nel **100% dei file** (1.532/1.532), con una media di **9,4 heading per file**.
- **Percorsi di menu / Breadcrumb (`⇒`, `→`, `▶`):** presenti in **873 file (57,0%)**, fondamentali per rispondere a domande operative su dove cliccare nel gestionale.
- **Tabelle Markdown:** presenti in **512 file (33,4%)**, di cui **65 file a contenuto prevalentemente tabellare** (>=45% di righe tabellari, es. tabelle campi, parametri, codici causale, elenchi revisioni).
- **Descrizione schermate / UI (`[Schermata: ...]`, `[Screenshot: ...]`):** presenti in **1.258 file (82,1%)** per un totale di **10.529 blocchi descrittivi** di interfacce grafiche.
- **Link Markdown immagine:** solo **2 file** (`109 - pubblicazione decreto.md`, `110 - pubblicazione delibera.md`), con URL fittizio `(placeholder)` (es. `![icona gruppo](placeholder)`).

---

## 4. Tipologie Documentali Individuate

Dall'analisi combinata di percorsi, prefissi e contenuto emergono le seguenti tipologie:
1. **Manuali e Guide Operative (`~1.332` file)**: istruzioni passo-passo sulle maschere di Cityware / CWOL (percorsi di menu, campi obbligatori, pulsanti, salvataggio).
2. **Comunicazioni e Circolari Tecniche (`~135` file)**: aggiornamenti normativi/funzionali datati per anno (`2019_c01_...`, `2024_c07_...`, `2025_c10_...`).
3. **Trascrizioni/Guide da Video (`video/`, `~40+` file)**: procedure sintetiche e dirette (es. `15 - Codice della Strada/video/3.md`).
4. **Materiali Webinar e Slide (`~39` file)**: sintesi da presentazioni e sessioni formative (`25 - Webinar`, `26 - Slide`).
5. **Indici e Mappe (`15` file + `INDEX.md` root)**: file `001 - INDICE - ...` e l'indice generale `INDEX.md`.
6. **FAQ, Note di Rilascio e Normative (`~11` file)**: es. `37 - Frequently Asked Questions`, `31 - Cronologia rilasci`.

---

## 5. Problemi Rilevati per il RAG e Rischi Critici

L'analisi empirica del corpus evidenzia **6 criticità concrete** che degraderebbero un RAG standard se non gestite in fase di parsing, metadata e retrieval:

### 5.1 Duplicati Esatti e Massiccia Presenza di Quasi-Duplicati (Wiki Variants)
- **Duplicati esatti (SHA-256 identico):** **2 coppie (4 file)**:
  - `11 - Tributi/video/sintesi_per_importazione_e_gestione_bonus.md` ≡ `49 - Manuali TARI/video/sintesi_operativita_per_importazione_e_gestione_bonus.md`
  - `15 - Codice della Strada/video/ultimi_avvisi.md` ≡ `15 - Codice della Strada/video/ultimi_avvisi_editato.md`
- **Quasi-duplicati strutturali (criticità alta):**
  - **108 gruppi** di file hanno esattamente lo stesso nome dopo il prefisso numerico (es. `accesso.md` in 9 aree; `035..039 - APERTURA DELLE OPERAZIONI ELETTORALI.md` in 5 file; `075..077 - Come personalizzare il Formulario.md` in 3 file).
  - **151 gruppi** condividono lo stesso titolo `# H1`, generando **238 coppie con similarità testuale >= 0,75**.
  - **Causa accertata:** in molti casi (es. `035` vs `039`) l'intero manuale procedurale è identico al ~98% e varia solo la riga iniziale `**Link utili:** ...` ereditata dal portale wiki. In altri casi esistono copie del medesimo manuale in due aree diverse (es. `2025_manuale_coge_cwol.md` in `10 - Area Economico - Finanziaria` da 50,2 KB e in `43 - Manuali Bilancio` da 48,5 KB).
- **Impatto sul RAG:** senza deduplicazione canonica/near-duplicate o raggruppamento per hash normalizzato, un `top_k=5` restituirebbe 4-5 copie dello stesso documento, saturando il context window ed escludendo documenti complementari.

### 5.2 Il File `INDEX.md` da 452 KB (Inquinamento del Retrieval)
- `data/INDEX.md` è un meta-indice auto-generato da 2.219 righe e 58.623 parole (4,3% dell'intero volume del dataset) contenente brevi descrizioni di tutti i 1.531 file e riferimenti a un file storico non presente (`verifica_scarti_report.md`).
- **Impatto sul RAG:** se indicizzato come un normale documento nel vector store, genererebbe oltre 300 chunk tabellari densi di parole chiave che catturerebbero il retrieval al posto dei veri manuali operativi. **Va escluso dall'indice semantico dei contenuti** (o usato solo come registro ausiliario di routing/metadata).

### 5.3 Conflitti Temporali e Stratificazione Storica (2010–2026)
- Nei documenti compaiono riferimenti temporali dal **2010 al 2026**, con picchi su **2025 (1.283 occorrenze)**, **2019 (1.262)**, **2024 (1.135)** e **2023 (1.039)**.
- Alcune comunicazioni del 2019/2020 hanno varianti aggiornate (`_v1`, `rev1`) salvate anche in cartelle del 2023 (es. `27 - Comunicazioni/06 - Comunicazioni 2023/allegati/2020_c09_..._v1.md`).
- **Impatto sul RAG:** senza metadata temporali (`doc_year`, `version_tag`, `is_communication`), il retrieval può mescolare istruzioni obsolete (es. Cityware Client/Server) con le nuove procedure **CWOL** (Cityware Online).

### 5.4 Riferimenti a PDF Esterni Assenti e Placeholder Visivi
- I documenti contengono **10.529 blocchi `[Schermata: ...]`**: in realtà questi non sono immagini rotte ma **trascrizioni testuali ricche** di campi, pulsanti e messaggi di errore (estremamente utili per il RAG!).
- Tuttavia, sono presenti link fittizi `![icona gruppo](placeholder)` (2 file) e riferimenti a file `.pdf` esterni non presenti in `data/` (es. `2020_c10_liquidazione_pagamenti_pagopa.pdf` citato nelle FAQ), che richiedono un comportamento trasparente del sistema (non inventare link né scaricare risorse esterne).

### 5.5 Fragilità di Tabelle e Procedure Multi-Passo al Chunking Naive
- Oltre metà dei documenti contiene **percorsi di navigazione UI (`⇒`, `→`, `▶`)** separati dai passaggi numerati e dalle relative tabelle dei campi.
- Un chunking a lunghezza fissa senza rispetto delle intestazioni `# / ## / ###` e delle tabelle Markdown spezza le righe delle tabelle e priva i passaggi numerati del percorso di menu iniziale.

### 5.6 Dati Personali (PII) e Informazioni Sensibili nei Campioni
Dalla scansione su tutto il corpus sono emersi:
- **Codici Fiscali (`19` file, `29` occorrenze):** molti sono esempi palesemente fittizi (`RSSMRA12A23B456C`, `RSSPLA51L11G157A`), ma compaiono anche codici formalmente realistici derivati da trascrizioni di schermate (es. `RGGRMS75D05F205R`, `LBRRLR67S06I156M`, `CNRFNC74S29A271R`).
- **IBAN (`6` file, `9` occorrenze):** presenti in esempi di flussi SIOPE+/OPI e liquidazioni (es. `IT41D0306905048031780160117`, `IT70M0301503200000003638635`).
- **Indirizzi Email / PEC (`44` file, `61` occorrenze):** prevalentemente email istituzionali/supporto (`cityware@palitalsoft.it`, `certificata@pec.italsoft-mc.it`) ed esempi (`test@pec.it`).
- **Menzioni di `password`, `token`, `PIN`, `credenziali` (`132` file, `658` occorrenze):** si riferiscono principalmente alle guide di accesso MFA/login e non contengono segreti di produzione esposti, ma vanno trattati con attenzione nei log.
- **Numeri IP / Codici punteggiati (`94` file):** la maggior parte dei match `x.x.x.x` è in realtà numerazione di voci di menu/capitoli di bilancio (es. `1.03.01.02`, `04.02.02.00`), con rari IP di rete interna di esempio (`10.12.0.200`).

---

## 6. Strategie Consigliate per l'Implementazione

### 6.1 Strategia di Parsing & Normalizzazione
1. **Esclusione di `INDEX.md`**: saltare `data/INDEX.md` dall'indicizzazione dei chunk (o usarlo opzionalmente solo come mappa), evitando l'inquinamento del vector store.
2. **Pulizia leggera e preservazione semantica**:
   - Rimuovere tag immagine fittizi (`![...](placeholder)`).
   - **Preservare** i blocchi `[Schermata: ...]` ripulendo solo eventuali rumori ripetuti come la riga `**Link utili:** ...` ai fini del calcolo dell'hash di deduplicazione canonica.
3. **Deduplicazione a due livelli**:
   - Livello 1: **SHA-256 esatto** su testo normalizzato.
   - Livello 2: **Near-duplicate detection** (normalizzazione rimuovendo `**Link utili:**` e prefissi numerici, più confronto su shingle/Jaccard o MinHash/fuzzy >= 0,90 sullo stesso titolo H1) per evitare copie multiple delle varianti wiki mantenendo solo la variante più completa/recente.
4. **Sanitizzazione PII nei Log e Audit**: mascherare eventuali CF/IBAN nei log applicativi e non memorizzare dati sensibili in chiaro nelle metriche.

### 6.2 Strategia di Metadata
Estrarre automaticamente metadati deterministici da percorso, nome file e contenuto:
```python
{
    "source": "03 - SERVIZI DEMOGRAFICI/067 - Cancellazione, la pratica resta in corso.md",
    "filename": "067 - Cancellazione, la pratica resta in corso.md",
    "document_id": "<sha256_prefix>",
    "title": "Cancellazione, la pratica resta in corso",
    "area_code": "03",
    "area_name": "SERVIZI DEMOGRAFICI",
    "subcategory": "allegati | video | root | ...",
    "document_type": "manual | communication | faq | webinar | slide | release_note | index",
    "doc_year": 2024,          # estratto da nome file/cartella/tabella revisioni se presente
    "section": "Percorso da seguire",
    "heading_path": "Cancellazione, la pratica resta in corso > Percorso da seguire",
    "has_table": True,
    "file_hash": "<sha256>",
    "updated_at": "<iso_mtime>"
}
```

### 6.3 Strategia di Chunking
Poiché il 100% dei file è Markdown strutturato con una media di 9,4 heading e mediana ~3.760 caratteri:
1. **Markdown Header-Aware Splitting** (`MarkdownHeaderTextSplitter` su `#`, `##`, `###`): mantiene ogni sezione unita sotto la gerarchia di titoli, iniettando `heading_path` nei metadata del chunk.
2. **Protezione delle Tabelle Markdown**: evitare di spezzare righe all'interno di uno stesso blocco tabella; se una sottosezione supera il limite massimo, applicare uno splitter secondario (`RecursiveCharacterTextSplitter`) con separatori che rispettino prima `\n\n` e solo in ultimo `\n`.
3. **Parametri consigliati**:
   - `chunk_size = 1200` caratteri (~250-300 token, ideale per mantenere insieme percorso di menu + passaggi operativi + nota schermata).
   - `chunk_overlap = 180` caratteri (~15%) per preservare la continuità tra passaggi adiacenti.
   - **Prepending del contesto**: anteporre al testo del chunk il titolo del documento e il percorso della sezione (`[Area: ... | Documento: ... | Sezione: ...]`) per migliorare drasticamente l'embedding e il retrieval tra procedure con sezioni omonime (es. *"Percorso di accesso"*).

### 6.4 Strategia di Vector Store & Retrieval
- Con 1.532 file (~10 MB totali, stimati ~4.500–6.000 chunk dopo deduplicazione), **ChromaDB** locale persistente (o FAISS) è ampiamente dimensionato, semplice, veloce e privo di infrastruttura distribuita superflua.
- **Hybrid / Lexical + Semantic Retrieval (opzionale ma fortemente raccomandato per questo dominio)**: l'altissima densità di acronimi tecnici (`ANPR`, `ANSC`, `SIOPE+`, `IUV`, `AP10`, `VRE`, `CVE`, `F7`, `F3`) rende la combinazione **Dense Vector Similarity + BM25 (o keyword boost)** molto più precisa rispetto al solo embedding denso, gestendo il filtro per `area_name` / `doc_year` e applicando una **soglia minima di rilevanza** con astensione controllata.
