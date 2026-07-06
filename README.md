# Wheelchair Layout Solver

Toolkit open source per verificare, in pianta 2D:

- la compatibilità di una posa della carrozzina con muri e ostacoli;
- una sequenza manuale di manovre;
- l'inviluppo geometrico della carrozzina;
- il margine minimo dagli ostacoli;
- in futuro: ricerca automatica A*/Hybrid A*, verifica funzionale e ottimizzazione del layout.

## Stato del progetto

Versione iniziale `0.1.0`: collision checker deterministico, validazione di un percorso
campionato, CLI, API FastAPI e adattatore Hops di base.

> Il software è uno strumento di supporto alla progettazione. Non certifica da solo
> la conformità normativa.

## Installazione rapida su Windows

1. Estrai la cartella sul Desktop.
2. Apri la cartella in Visual Studio Code.
3. Apri PowerShell nel terminale di VS Code.
4. Esegui:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
./scripts/setup_windows.ps1
```

5. Seleziona come interprete Python:

```text
.venv\Scripts\python.exe
```

6. Verifica l'installazione:

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\wheelchair-solver.exe check-pose samples/bathroom_01.json --x 1.2 --y 1.2 --angle 0
```

## Installazione manuale

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev,cad,api]"
pytest
```

Per installare anche il ponte Grasshopper Hops:

```powershell
python -m pip install -e ".[hops]"
```

## Avvio dell'API

```powershell
wheelchair-solver serve --host 127.0.0.1 --port 8000
```

Documentazione interattiva:

```text
http://127.0.0.1:8000/docs
```

## Avvio del server Hops

```powershell
python -m wheelchair_layout_solver.hops_server
```

Endpoint Hops iniziale:

```text
http://127.0.0.1:5000/check_pose
```

## Convenzioni geometriche

- Unità consigliata: metri.
- Asse locale carrozzina: `+X` verso il fronte, `+Y` verso sinistra.
- Angoli: gradi antiorari.
- La posa è `(x, y, angle_deg)`.
- La sagoma base è rettangolare e può essere ampliata da un margine di sicurezza.

## Comandi CLI

Controllo di una posa:

```powershell
wheelchair-solver check-pose samples/bathroom_01.json --x 1.2 --y 1.2 --angle 0
```

Controllo del percorso contenuto nel file:

```powershell
wheelchair-solver check-path samples/bathroom_01.json
```

## Struttura

```text
src/wheelchair_layout_solver/
  models.py       modelli e schema JSON
  geometry.py     conversioni e sagoma carrozzina
  collision.py    verifica di una posa
  path.py         interpolazione e verifica del percorso
  io.py           lettura/scrittura JSON
  api.py          API FastAPI
  hops_server.py  adattatore Hops
  cli.py          comandi da terminale
```

## Roadmap

1. Importazione DXF/3DM.
2. Porte dinamiche.
3. Zone funzionali per WC, lavabo e doccia.
4. A* nello spazio `(x, y, theta)`.
5. Hybrid A* e primitive cinematiche.
6. Ottimizzazione dei layout entro tolleranze.
7. Robustezza Monte Carlo.
8. Definizione Grasshopper e interfaccia dedicata.

## Licenza

MIT. Vedi `LICENSE`.
