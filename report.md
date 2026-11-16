AI SOFTWARE ACADEMY
Documento di sintesi – Analisi funzionale e architetturale

Versione: 1.0
Tipologia: Documento di analisi e indirizzo architetturale
Ambito: Intelligenza artificiale, RAG, formazione adattiva e software per la Pubblica Amministrazione.

1. Executive Summary

AI Software Academy è una piattaforma di formazione intelligente progettata per supportare l'apprendimento e l'utilizzo dei software gestionali destinati alla Pubblica Amministrazione.

L'obiettivo è superare il modello tradizionale di e-learning, introducendo un sistema nel quale l'intelligenza artificiale non si limita a fornire assistenza agli utenti, ma contribuisce attivamente alla produzione dei contenuti didattici, all'individuazione delle lacune conoscitive e alla valutazione dell'apprendimento.

La piattaforma si fonda su un'architettura RAG (Retrieval-Augmented Generation) già esistente, sviluppata in Python ed esposta tramite API, che costituisce il patrimonio conoscitivo centrale del sistema.

A partire da questa infrastruttura vengono introdotte tre aree funzionali:

AI Knowledge-to-Course Engine: analisi della documentazione e generazione automatica di corsi.
AI Course Generator: generazione strutturata di curriculum, lezioni, esempi ed esercitazioni.
Adaptive Learning & Custom Quiz Engine: personalizzazione dei quiz sulla base dello storico individuale e misurazione dell'effettivo apprendimento.

Il modello di generazione previsto per le risposte e i contenuti AI è Qwen.

La piattaforma è concepita per supportare più produttori software, più applicativi e più amministrazioni, mantenendo separazione dei dati, delle fonti documentali e dei profili degli utenti.

La modalità formativa principale è il self-learning, con possibilità di apprendimento autonomo e supporto continuo dell'AI Tutor.

2. Contesto e obiettivi
2.1 Scenario di riferimento

La Pubblica Amministrazione utilizza numerosi applicativi software per la gestione dei processi amministrativi, contabili, documentali e organizzativi.

L'utilizzo efficace di questi strumenti richiede:

Conoscenza delle funzionalità applicative.
Comprensione delle procedure operative.
Conoscenza delle regole e dei vincoli.
Capacità di risolvere autonomamente le problematiche più comuni.
Aggiornamento continuo in funzione delle evoluzioni software.

La documentazione tecnica e operativa è spesso distribuita tra manuali, guide, comunicazioni, circolari, FAQ e procedure aziendali.

AI Software Academy intende valorizzare questo patrimonio documentale, trasformandolo in un sistema di apprendimento dinamico e personalizzato.

2.2 Obiettivi strategici
Ridurre i tempi necessari per apprendere l'utilizzo dei software gestionali.
Aumentare l'autonomia degli operatori.
Ridurre le richieste di assistenza dovute a difficoltà operative.
Automatizzare la produzione e l'aggiornamento dei contenuti formativi.
Personalizzare l'apprendimento in funzione delle conoscenze individuali.
Misurare l'efficacia reale della formazione.
Valorizzare la documentazione già disponibile presso i produttori software.
2.3 Destinatari

La piattaforma prevede due principali categorie di utenti.

Produttori software

Gestione della documentazione.
Gestione della knowledge base.
Analisi delle opportunità formative.
Generazione e revisione dei corsi.
Pubblicazione dei contenuti.
Monitoraggio dell'efficacia formativa.

Operatori della Pubblica Amministrazione

Consultazione dei corsi.
Apprendimento autonomo.
Utilizzo dell'AI Tutor.
Esecuzione dei quiz.
Ricezione di percorsi formativi personalizzati.
Monitoraggio dei propri progressi.
3. Architettura di riferimento
3.1 Principio architetturale fondamentale

Il progetto parte da un RAG già funzionante, sviluppato in Python ed esposto tramite API.

La scelta architetturale è quella di estendere progressivamente questa infrastruttura, evitando di realizzare un secondo sistema di retrieval o duplicare i servizi già disponibili.

Il RAG rappresenta il livello centrale di accesso alla conoscenza.

I nuovi moduli devono riutilizzare:

Pipeline di ingestion.
Gestione documentale.
Chunking e metadati.
Vector database e servizi di retrieval.
Servizi di generazione LLM.
Gestione delle fonti.
Autenticazione e autorizzazione.
Database e infrastruttura applicativa.

Il progetto deve mantenere la compatibilità con gli entry point e le API già esistenti.

3.2 Architettura logica complessiva
mermaid
flowchart TB
    subgraph SOURCES["Documentazione"]
        D1["Manuali software"]
        D2["Procedure operative"]
        D3["FAQ e comunicazioni"]
        D4["Guide e documenti"]
    end

    subgraph CORE["RAG Core - Python API"]
        ING["Document Ingestion"]
        RET["Retrieval Engine"]
        LLM["LLM Service - Qwen"]
        KB["Knowledge Base"]
    end

    subgraph ACADEMY["AI Software Academy"]
        TUTOR["AI Tutor"]
        KI["Knowledge Intelligence"]
        CG["AI Course Generator"]
        AL["Adaptive Learning Engine"]
        CQ["Custom Quiz Engine"]
    end

    subgraph DATA["Persistenza"]
        DB1["Documenti e metadati"]
        DB2["Corsi e lezioni"]
        DB3["Profili conoscitivi"]
        DB4["Quiz e risultati"]
        DB5["Metriche di apprendimento"]
    end

    subgraph USERS["Utenti"]
        PROD["Software Publisher"]
        PA["Operatori PA"]
    end

    SOURCES --> ING
    ING --> KB
    KB --> RET
    RET --> LLM

    RET --> TUTOR
    KB --> KI
    KI --> CG
    CG --> AL
    AL --> CQ

    CORE --> DATA
    ACADEMY --> DATA

    PROD --> KI
    PROD --> CG
    PA --> TUTOR
    PA --> CQ


Schema logico concettuale. Non rappresenta necessariamente la topologia fisica o i componenti già implementati.

3.3 Separazione delle responsabilità

L'architettura prevede una distinzione tra:

RAG Core

Recupero delle informazioni.
Consultazione della documentazione.
Generazione delle risposte.
Gestione delle fonti.

Knowledge Intelligence

Analisi del patrimonio documentale.
Identificazione degli argomenti rilevanti.
Valutazione delle opportunità formative.
Individuazione delle lacune documentali.

Course Generation

Progettazione dei percorsi.
Generazione delle lezioni.
Generazione dei quiz didattici.
Produzione dei contenuti formativi.

Adaptive Learning

Analisi delle interazioni individuali.
Individuazione delle lacune conoscitive.
Generazione dei Custom Quiz.
Misurazione dell'apprendimento.

Questa separazione consente di evolvere le singole funzionalità senza compromettere il funzionamento del RAG.

4. AI Tutor – Assistenza intelligente

L'AI Tutor rappresenta il primo livello di interazione dell'utente con la conoscenza documentale.

L'utente può interrogare il sistema in linguaggio naturale per ottenere informazioni sulle funzionalità dei software, sulle procedure e sulle modalità operative.

Le risposte vengono generate utilizzando il RAG esistente.

Requisiti architetturali:

Utilizzo del modello Qwen.
Retrieval delle fonti pertinenti.
Risposte contestualizzate rispetto al software e al modulo.
Riferimenti documentali.
Rispetto dei permessi di accesso.
Tracciamento delle interazioni, nei limiti delle policy di conservazione.
Disponibilità dello storico delle richieste per le successive elaborazioni di Adaptive Learning.

L'AI Tutor costituisce anche una delle principali fonti di evidenza per l'individuazione delle esigenze formative individuali.

5. AI Knowledge-to-Course Engine
5.1 Obiettivo

Il sistema deve essere in grado di analizzare autonomamente la knowledge base e individuare quali conoscenze meritano di essere trasformate in contenuti formativi.

Non si tratta di convertire automaticamente ogni documento in un corso.

L'obiettivo è identificare argomenti, procedure e conoscenze con reale valore didattico.

Un corso può derivare:

Da un singolo documento.
Da più documenti correlati.
Da un'intera area funzionale.
Da una specifica procedura.
Da una combinazione di documentazione tecnica e operativa.
5.2 Knowledge Intelligence Engine

È previsto un nuovo componente denominato Knowledge Intelligence Engine.

Le sue responsabilità sono:

Knowledge Extraction

Estrazione di:

Argomenti principali.
Procedure.
Regole operative.
Concetti ricorrenti.
Esempi.
Errori frequenti.
Vincoli.
Relazioni tra argomenti.

Topic Classification

Classificazione delle conoscenze in categorie, tra cui:

Utilizzo del software.
Procedure operative.
Gestione degli errori.
Assistenza tecnica.
Normativa e regolamenti.
Amministrazione e contabilità.
Gestione documentale.
Sicurezza e autorizzazioni.
Best practice.

Relevance Scoring

Valutazione dell'importanza formativa degli argomenti considerando:

Importanza operativa.
Frequenza nella documentazione.
Criticità di un eventuale errore.
Complessità.
Utilità per l'autonomia dell'operatore.
Completezza delle informazioni.
Attualità delle fonti.
Applicabilità ai diversi software e ruoli.

Knowledge Gap Detection

Individuazione di:

Argomenti non sufficientemente documentati.
Procedure incomplete.
Informazioni contraddittorie.
Contenuti obsoleti.
Necessità di integrazioni documentali.
5.3 Training Opportunities

Il risultato dell'analisi non deve essere immediatamente un corso pubblicato.

Deve essere una proposta formativa strutturata contenente:

Titolo.
Descrizione.
Obiettivi didattici.
Argomenti.
Documenti sorgente.
Software e moduli interessati.
Destinatari suggeriti.
Livello di difficoltà.
Rilevanza formativa.
Completezza documentale.
Eventuali criticità.

Il produttore software può esaminare le proposte e decidere quali trasformare in corsi.

6. AI Course Generator
6.1 Obiettivo

Il modulo AI Course Generator trasforma le opportunità formative individuate dal Knowledge Intelligence Engine in corsi strutturati.

Deve poter generare automaticamente:

Titolo e descrizione.
Obiettivi formativi.
Prerequisiti.
Curriculum.
Moduli didattici.
Lezioni.
Spiegazioni.
Esempi pratici.
Procedure passo-passo.
Errori frequenti.
Quiz.
Esercitazioni.
Riepiloghi.

La struttura deve dipendere dalle conoscenze realmente disponibili, evitando lezioni artificiali o ripetitive.

6.2 Tipologie di corso

Sono previste due categorie.

Corsi documentali

Orientati all'apprendimento di:

Regole operative.
Procedure aziendali.
Modalità di assistenza.
Processi amministrativi.
Comportamenti corretti e scorretti.
Best practice.

Corsi applicativi

Orientati all'apprendimento di:

Funzionalità specifiche del software.
Utilizzo dei singoli moduli.
Procedure operative nel gestionale.
Gestione degli errori.
Esecuzione di attività concrete.
6.3 Esempio applicativo

Documento sorgente: Comunicazione n. 01/2024 – Modalità di richiesta assistenza.

Il sistema può generare il corso:

"Come richiedere correttamente assistenza su Cityware Online".

Possibile curriculum:

Funzionamento del servizio di assistenza.
Quando aprire un ticket.
Come scrivere un ticket efficace.
Errori da evitare.
Analisi di esempi corretti e scorretti.

Il corso può comprendere quiz ed esercitazioni basati sugli esempi presenti nel documento.

6.4 Grounding e tracciabilità

Ogni contenuto generato deve mantenere il collegamento con le fonti originali.

Per ogni lezione devono essere conservati, quando disponibili:

ID documento.
Titolo.
Versione.
ID chunk.
Pagina.
Sezione o paragrafo.
Data di aggiornamento.

Devono essere rilevati:

Affermazioni prive di supporto.
Fonti contraddittorie.
Informazioni obsolete.
Differenze tra versioni software.

Non devono essere presentate come procedure ufficiali informazioni generate autonomamente dall'AI.

6.5 Workflow editoriale

I corsi seguono un processo di revisione:

text
PROPOSED
    |
    v
GENERATED
    |
    v
UNDER_REVIEW
    |
    v
APPROVED
    |
    v
PUBLISHED


La generazione non comporta pubblicazione automatica.

È previsto il controllo editoriale del produttore software.

Devono essere mantenuti lo storico delle revisioni e il collegamento tra corsi e versioni della documentazione.

7. Adaptive Learning & Custom Quiz Engine
7.1 Obiettivo

La terza milestone introduce un sistema di apprendimento adattivo.

A differenza dei quiz tradizionali contenuti nei corsi, i Custom Quiz vengono generati individualmente sulla base dello storico di utilizzo della piattaforma.

Il sistema deve identificare le lacune conoscitive dimostrate dall'utente, proporre verifiche mirate e misurare nel tempo se tali lacune vengono effettivamente colmate.

7.2 Distinzione tra quiz tradizionali e Custom Quiz

Quiz tradizionali

Sono associati ai corsi.
Verificano la comprensione delle lezioni.
Sono basati sui contenuti didattici.
Vengono utilizzati per la valutazione del corso.

Custom Quiz

Sono individuali.
Sono generati sulla base dello storico dell'utente.
Verificano argomenti sui quali sono emerse difficoltà.
Evolvono in funzione dei risultati precedenti.
Contribuiscono alla costruzione del profilo conoscitivo individuale.

I due sistemi devono rimanere distinti, pur condividendo eventuali componenti comuni.

7.3 Fonti delle evidenze individuali

Il sistema deve analizzare:

Storico RAG

Domande frequenti.
Argomenti ricorrenti.
Richieste ripetute.
Richieste di chiarimento.
Incomprensioni esplicitamente dichiarate.

Risultati dei quiz tradizionali

Domande sbagliate.
Argomenti con errori ricorrenti.
Risposte corrette e scorrette.
Evoluzione dei risultati.

Storico Custom Quiz

Risultati precedenti.
Errori ripetuti.
Miglioramenti.
Competenze verificate.
Retention delle conoscenze.

Una domanda frequente non deve essere automaticamente interpretata come una lacuna: potrebbe derivare dalla normale attività lavorativa dell'utente.

È necessario distinguere tra frequenza di utilizzo, difficoltà dimostrata e competenza effettivamente verificata.

7.4 User Knowledge Profile

Ogni utente deve disporre di un profilo conoscitivo individuale.

Il profilo comprende:

Identificativo utente.
Software utilizzati.
Moduli applicativi interessati.
Argomenti conosciuti.
Argomenti sui quali emergono difficoltà.
Errori nei quiz.
Risultati dei Custom Quiz.
Livello conoscitivo stimato.
Numero di verifiche.
Ultima data di valutazione.
Evoluzione delle competenze.

Il profilo deve essere aggiornato progressivamente.

7.5 Learning Gap Detection

Il sistema individua le lacune conoscitive sulla base delle evidenze disponibili.

Ogni lacuna deve contenere:

Argomento.
Software e modulo.
Evidenze che hanno determinato la segnalazione.
Fonti delle evidenze.
Priorità.
Livello di confidenza.
Data di individuazione.
Stato.

Stati previsti:

text
OPEN
  |
  v
IN_PROGRESS
  |
  v
IMPROVING
  |
  v
RESOLVED


La risoluzione deve essere supportata da verifiche successive positive, non da una semplice dichiarazione del sistema.

7.6 Custom Quiz Generator

Il generatore deve produrre quiz specifici per l'utente.

Requisito obbligatorio: ogni domanda deve avere esattamente quattro possibili risposte, con una sola risposta corretta.

Ogni domanda deve contenere:

Testo.
Quattro opzioni.
Identificativo della risposta corretta.
Spiegazione.
Argomento verificato.
Livello di difficoltà.
Fonti documentali.
Collegamento alla lacuna che ha originato la domanda.

Le domande devono essere differenti dai quiz precedenti e verificare la reale comprensione, non la semplice memorizzazione.

Le risposte corrette devono rimanere nascoste fino alla conclusione del quiz.

7.7 Nuovo entry point: customquiz

È previsto un entry point applicativo dedicato denominato:

customquiz

Deve essere integrato nell'architettura Python esistente, rispettando le convenzioni degli entry point già presenti.

Le principali operazioni previste sono:

Analisi delle lacune di un utente.
Generazione di un Custom Quiz.
Recupero di un quiz esistente.
Consultazione dello storico.
Registrazione delle risposte.
Calcolo dei risultati.
Aggiornamento del profilo conoscitivo.
Aggiornamento delle lacune.
Consultazione delle metriche.

Endpoint indicativi:

http
POST /customquiz/generate

GET /customquiz/{quiz_id}

GET /customquiz/user/{user_id}

POST /customquiz/{quiz_id}/submit

GET /customquiz/{quiz_id}/results

GET /customquiz/user/{user_id}/learning-profile

GET /customquiz/user/{user_id}/learning-metrics

POST /customquiz/user/{user_id}/analyze-gaps


Gli endpoint definitivi devono essere adattati al framework e alle convenzioni API già presenti.

8. Learning Metrics – Misurazione dell'efficacia formativa

Uno degli elementi distintivi di AI Software Academy è la possibilità di misurare l'effettiva acquisizione delle conoscenze.

Non è sufficiente misurare il numero di quiz completati o il punteggio ottenuto.

Il sistema deve verificare se le lacune inizialmente individuate vengono progressivamente colmate.

8.1 Metriche principali
Metrica	Significato
Quiz Accuracy	Percentuale di risposte corrette
Learning Improvement	Miglioramento tra verifiche successive
Knowledge Gap Resolution Rate	Percentuale di lacune risolte
Retention Rate	Capacità di mantenere le conoscenze nel tempo
Repeated Error Rate	Frequenza degli errori che si ripetono
Learning Progress	Evoluzione complessiva delle competenze
8.2 Verifica longitudinale

Il sistema deve prevedere verifiche successive.

Esempio:

L'utente sbaglia domande sulla corretta apertura dei ticket.
Il sistema individua una lacuna conoscitiva.
Viene generato un Custom Quiz specifico.
L'utente completa il quiz.
Dopo un intervallo di tempo viene generato un nuovo quiz sullo stesso argomento.
Le nuove domande sono differenti dalle precedenti.
Il sistema confronta i risultati.
La lacuna viene classificata come migliorata, risolta o ancora aperta.

La retention è particolarmente importante: il superamento immediato di un quiz non garantisce che la conoscenza sia stata effettivamente acquisita e mantenuta.

8.3 Livelli di apprendimento

Il sistema deve poter distinguere:

Lacuna individuata.
Apprendimento in corso.
Miglioramento verificato.
Competenza consolidata.

Le metriche devono essere consultabili per:

Utente.
Argomento.
Software.
Modulo applicativo.
Periodo temporale.
9. Modello dati e persistenza

Le nuove funzionalità richiedono una persistenza strutturata.

Il vector database continua a essere utilizzato per il recupero documentale, mentre il database applicativo gestisce i dati relativi a corsi, utenti, quiz e risultati.

Entità logiche previste:

Entità	Responsabilità
KnowledgeAnalysisJob	Processi di analisi documentale
ExtractedTopic	Argomenti individuati
TopicRelevanceScore	Valutazioni formative
KnowledgeGap	Lacune documentali o conoscitive
TrainingOpportunity	Proposte formative
Course	Corsi
CourseModule	Moduli didattici
Lesson	Lezioni
LessonSource	Fonti delle lezioni
Quiz	Quiz tradizionali
CustomQuiz	Quiz personalizzati
CustomQuizQuestion	Domande e risposte
CustomQuizAttempt	Tentativi effettuati
UserKnowledgeProfile	Profilo conoscitivo
LearningMetric	Metriche di apprendimento

È necessario mantenere relazioni esplicite tra:

Utenti e quiz.
Quiz e domande.
Domande e argomenti.
Argomenti e lacune.
Lezioni e documenti sorgente.
Risultati e profili conoscitivi.

Le risposte corrette non devono essere esposte prima della conclusione del quiz.

10. Multi-tenancy, ruoli e sicurezza

L'architettura deve essere predisposta per supportare più produttori software e più amministrazioni.

La segregazione dei dati deve essere nativa.

10.1 Ambiti di separazione
Produttori software.
Amministrazioni.
Utenti.
Software.
Moduli applicativi.
Documentazione.
Corsi.
Profili conoscitivi.
Quiz e risultati.
10.2 Principi di sicurezza
Controllo degli accessi basato sui ruoli.
Isolamento dei tenant.
Verifica dei permessi sulle fonti RAG.
Protezione dello storico delle interazioni.
Separazione dei dati personali.
Audit delle operazioni.
Politiche di conservazione.
Anonimizzazione e cancellazione secondo le policy applicabili.

I contenuti documentali devono essere considerati dati non attendibili rispetto alle istruzioni del modello AI, evitando che eventuali istruzioni contenute nei documenti possano modificare i prompt di sistema o i controlli di sicurezza.

Il profilo conoscitivo non deve essere utilizzato per penalizzare o classificare negativamente gli operatori.

11. Automazione e aggiornamento

L'architettura deve prevedere modalità differenti di elaborazione.

11.1 Analisi all'ingestione

Quando viene aggiunto un documento:

Il RAG lo indicizza.
Il Knowledge Intelligence analizza i nuovi contenuti.
Vengono individuati gli argomenti.
Vengono verificate eventuali opportunità formative.
Vengono rilevati possibili aggiornamenti ai corsi esistenti.
11.2 Analisi periodica

Una scansione periodica della knowledge base consente di individuare nuove opportunità formative derivanti dalla correlazione di documenti differenti.

11.3 Analisi su richiesta

Il produttore software può avviare analisi specifiche, ad esempio:

"Analizza tutta la documentazione di Cityfinancing e proponi i corsi che ritieni opportuni".

Oppure:

"Individua le dieci procedure più importanti che un nuovo operatore di ragioneria dovrebbe conoscere".

11.4 Analisi incrementale

L'elaborazione deve evitare scansioni complete non necessarie.

Devono essere gestiti:

Identificativi e versioni dei documenti.
Hash o altri indicatori di modifica.
Cache dei risultati.
Processi asincroni.
Retry controllati.
Tracciamento dello stato dei job.
12. Requisiti tecnologici e integrazione

Il progetto deve mantenere l'architettura tecnologica esistente.

Componente	Indirizzo architetturale
Backend	Python
API	API esistenti, estese con nuovi endpoint
Knowledge Retrieval	RAG già funzionante
Modello generativo	Qwen
Document Ingestion	Pipeline esistente
Vector Database	Componente esistente
Database applicativo	Da estendere in base all'architettura corrente
Course Generation	Nuovo modulo integrato
Adaptive Learning	Nuovo modulo integrato
Custom Quiz	Nuovo entry point dedicato
Background Jobs	Infrastruttura esistente o soluzione compatibile

I dettagli implementativi del progetto attuale, inclusi framework, database, vector store e sistema di autenticazione, devono essere verificati direttamente sul codice.

Non devono essere introdotte dipendenze o infrastrutture duplicate senza motivazioni tecniche.

12.1 Entry point e compatibilità

Tutte le nuove funzionalità devono integrarsi con gli entry point già presenti.

Per la terza milestone è richiesto un nuovo entry point denominato:

customquiz

La sua implementazione deve rispettare le convenzioni esistenti, senza alterare il funzionamento degli entry point già operativi.

13. Roadmap evolutiva

Il progetto può essere organizzato in quattro macro-release.

Release 1 – Academy Foundation
Gestione utenti.
Multi-tenancy.
Catalogo software.
Catalogo corsi.
Lezioni.
Integrazione RAG.
AI Tutor.
Quiz tradizionali.
Progress tracking.
Release 2 – AI Knowledge-to-Course Engine
Analisi della knowledge base.
Estrazione degli argomenti.
Relevance Scoring.
Knowledge Gap Detection.
Training Opportunities.
Generazione curriculum.
Generazione lezioni.
Generazione quiz.
Validazione e approvazione.
Release 3 – Adaptive Learning & Custom Quiz
User Knowledge Profile.
Analisi dello storico RAG.
Analisi degli errori nei quiz.
Learning Gap Detection individuale.
Personalizzazione dei quiz.
Nuovo entry point customquiz.
Persistenza dei quiz.
Learning Metrics.
Verifica della retention.
Release 4 – Enterprise Ecosystem

Possibili evoluzioni:

Simulation Engine.
Esercitazioni interattive.
Certificazioni.
Analytics multi-ente.
Integrazioni LMS.
Standard SCORM e xAPI.
API per sistemi esterni.
Integrazione con help desk.
Dashboard avanzate per produttori e amministrazioni.
14. KPI e indicatori di successo

L'efficacia di AI Software Academy deve essere misurata non soltanto attraverso l'utilizzo della piattaforma, ma soprattutto attraverso i risultati formativi.

KPI didattici
Course Completion Rate.
Assessment Success Rate.
Learning Improvement.
Knowledge Gap Resolution Rate.
Retention Rate.
Time to Competency.
KPI AI e RAG
Tutor Resolution Rate.
Source Grounding.
Version Accuracy.
Percentuale di contenuti formativi supportati da fonti.
Percentuale di quiz generati con fonti verificabili.
KPI operativi
Riduzione delle richieste di assistenza ripetitive.
Riduzione dei tempi di onboarding.
Maggiore autonomia degli operatori.
Riduzione degli errori operativi.
Tempo necessario per acquisire competenze su un nuovo applicativo.

Un indicatore particolarmente significativo è il tempo necessario a un nuovo operatore per diventare autonomo nell'utilizzo di uno specifico gestionale.

15. Principi architetturali da preservare

Le seguenti decisioni costituiscono i principi guida del progetto.

1. Un solo RAG

Il RAG esistente rappresenta il patrimonio conoscitivo centrale. Non devono essere realizzati sistemi di retrieval duplicati.

2. Qwen come modello di generazione

Le funzionalità AI devono utilizzare il servizio LLM già presente, mantenendo Qwen come modello previsto e configurabile.

3. Multi-tenancy nativa

La separazione tra produttori, amministrazioni e utenti deve essere prevista fin dall'architettura di base.

4. Version-aware learning

I contenuti didattici devono essere associati alle versioni software e documentali pertinenti.

5. Grounding obbligatorio

Le informazioni didattiche devono essere riconducibili a fonti verificabili.

6. Human-in-the-loop

I corsi generati dall'AI devono essere sottoposti a revisione prima della pubblicazione.

7. Adaptive Learning

Lo storico individuale deve contribuire a personalizzare la formazione, senza interpretare automaticamente ogni richiesta come una lacuna.

8. Misurazione longitudinale

L'apprendimento deve essere valutato nel tempo, distinguendo il superamento di un singolo quiz dall'effettivo consolidamento delle competenze.

9. Integrazione incrementale

Ogni nuova funzionalità deve estendere il progetto Python esistente, riutilizzando gli entry point, i servizi e le API già disponibili.

10. Sicurezza e privacy

Profili conoscitivi, storico delle interazioni e risultati individuali devono essere protetti e accessibili esclusivamente secondo le autorizzazioni previste.

16. Visione complessiva del prodotto

AI Software Academy si configura come una piattaforma di Digital Adoption e Software Learning per la Pubblica Amministrazione.

Non è semplicemente un LMS con un chatbot integrato.

È un ecosistema nel quale:

La documentazione aziendale viene trasformata in conoscenza interrogabile.
La conoscenza viene analizzata per individuare opportunità formative.
L'intelligenza artificiale genera corsi e lezioni.
L'utente apprende attraverso percorsi autonomi.
L'AI Tutor supporta l'utilizzo quotidiano dei software.
Lo storico delle interazioni e dei test consente di individuare difficoltà individuali.
I Custom Quiz verificano il superamento delle lacune.
Le metriche misurano l'effettiva evoluzione delle competenze.

Il sistema crea così un ciclo continuo:

text
DOCUMENTAZIONE
      |
      v
KNOWLEDGE BASE
      |
      v
KNOWLEDGE INTELLIGENCE
      |
      v
GENERAZIONE CORSI
      |
      v
APPRENDIMENTO
      |
      v
INTERAZIONI E QUIZ
      |
      v
ANALISI DELLE LACUNE
      |
      v
CUSTOM QUIZ
      |
      v
MISURAZIONE APPRENDIMENTO
      |
      +----------> NUOVE OPPORTUNITÀ FORMATIVE

Conclusione

Il valore distintivo di AI Software Academy risiede nella capacità di trasformare la documentazione dei produttori software in un patrimonio formativo dinamico, personalizzato e misurabile.

La piattaforma non si limita a spiegare come utilizzare un software, ma cerca di accompagnare ogni operatore verso una maggiore autonomia, identificando le difficoltà, proponendo contenuti mirati e verificando nel tempo l'acquisizione delle competenze.

La visione finale è quella di un sistema di apprendimento continuo, nel quale la conoscenza documentale, l'assistenza intelligente e la formazione adattiva costituiscono un unico ecosistema.