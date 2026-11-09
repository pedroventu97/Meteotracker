# PROPOSTA DI VALIDAZIONE — Scelta del valore del cap di warm-up dai test τ — v1

**Versione 1, 09/11/2026.** Da usare con `e0/PROTOCOLLO_TAU_WARMUP_v1.md`. Base: `e0/DECISIONE_CAP_WARMUP_20261109.md` (principio approvato, valore aperto, τ ≈ 10 s ritirato).
- **Questa regola è fissata PRIMA di qualsiasi misura.** Va committata prima che esista il primo file in `data/tau_tests/`.
- Ogni modifica successiva deve essere una nuova versione datata, con la motivazione, e approvata da Marco **prima** di guardare i risultati che riguarda.
- La regola è implementata e testata (dati sintetici) in `e0/tau_warmup_analysis.py::decide_cap` e in `tests/test_tau_warmup_analysis.py`.
- **R di P1 non entra in nessun punto.**

## 1. Piano di analisi
1. **Inventario:** leggere `data/tau_tests/TAU_SHEETS.csv`.
   - Contare i test validi e non validi per tipo, gruppo e cella, con i motivi di esclusione.
   - Verificare i minimi della §6.3 del protocollo; se non sono raggiunti → stato `INSUFFICIENT_DATA`.
2. **Allineamento:** CSV del MT (ora con offset, convertita in UTC) e CSV del REF (UTC corretto per l'offset dell'orologio) sulla griglia di 1 s (`align_to_ref`).
   - Nel foglio, `file_mt`/`file_ref` sono percorsi relativi a `data/tau_tests/` (es. `field/TAU_FIELD_…_MT.csv`).
3. **Test A:** per ogni test valido, `fit_first_order` → τ, d, b, RMSE, IC bootstrap.
   - Tra test: media di τ, IC 95 % t, **τ_UCB95 unilaterale**, massimo, discesa e risalita separate.
   - Sensibilità a 2 m/s riportata a parte.
   - Correzione τ_MT = τ_fit + τ_REF (§1.4 del protocollo).
4. **Test B:** per ogni partenza valida:
   - e(t), e_∞, t_s(0,2), t_s(0,1), ΔT0;
   - quota ventilata 0–300 s;
   - controllo della dev. std nella finestra finale ≤ 0,10 °C.
5. **Incertezza:** U verificata con i dati (dev. std della finestra finale, ritardi d) e confrontata con il budget del protocollo (§6.1). Se U > 0,15 °C → non si decide.
6. **Tabelle descrittive:**
   - distribuzione di t_s per gruppo e cella (mediana, p75, p90, max);
   - frazioni di superamento per T ∈ {120, 180, 300, 600} con IC Clopper–Pearson;
   - |e(T) − e_∞| per T;
   - ΔT0_p95 nelle COLD;
   - confronto WARM vs COLD (Mann–Whitney, descrittivo).
7. **Decisione:** `decide_cap`, applicata una volta in fase 1 ed eventualmente una volta in fase 2 (§4).

## 2. Quantità in ingresso alla regola
- `ts_cold`, `ts_intermediate`, `ts_warm`: t_s(0,2 °C) delle partenze valide (∞ se la stabilità non viene raggiunta entro 900 s).
- `tau_ucb95_s`: limite superiore unilaterale al 95 % di τ_MT dal Test A (5,6 m/s).
- `dT0_p95_c`: 95° percentile di |ΔT0| nelle COLD.
- `cells_cold`: t_s(0,2) delle COLD per cella C1–C4.

## 3. Regola di decisione (fissata in anticipo)
Per ciascuna soglia candidata **T ∈ {120, 180, 300, 600} s**, in ordine crescente, la soglia passa se valgono **tutte** le condizioni:

| Condizione | Definizione |
|---|---|
| **C1 (COLD, punto)** | k/n ≤ 0,10, con k = numero di COLD con t_s(0,2) > T, n ≥ 20 |
| **C1 (COLD, UCB)** | limite superiore unilaterale al 95 % di Clopper–Pearson di k/n ≤ 0,20 |
| **C2 (altri gruppi)** | INTERMEDIATE e WARM (n ≥ 10 ciascuno): frazione con t_s(0,2) > T ≤ 0,20 |
| **C3 (condizioni)** | ogni cella C1–C4 con ≥ 5 COLD: frazione con t_s(0,2) > T ≤ 0,20 |
| **C4 (fisica)** | τ_UCB95 · ln(ΔT0_p95 / 0,2) ≤ T |

- **Esito:** il valore proposto è la **più piccola T che passa** (stato `SELECTED`).
- **Confronto 300/600:** la tabella completa delle condizioni per 300 e per 600 si riporta sempre, anche quando la soglia scelta è un'altra.
- **Perché C4:** traduce l'ipotesi di risposta del primo ordine con il τ *misurato* (non più assunto). Serve a non accettare una soglia che l'evidenza di campo supera per caso con pochi dati.

## 4. Risultati ambigui o negativi
1. **Ambiguità statistica in fase 1** (stato `EXTEND_TO_PHASE_2`): esiste una T più piccola di quella che passa (o nessuna passa) che soddisfa C1-punto, C2, C3 e C4 ma non C1-UCB.
   - Per esempio, a 300 s si ha 1 superamento su 20 (UCB 21,6 %).
   - → **Una sola estensione** a 30 COLD (+10 singole), senza altre analisi intermedie. Poi si riapplica la regola con `phase=2`.
2. **Ancora ambiguo in fase 2** (`PROVISIONAL_CONSERVATIVE`): si propone la più piccola T che passa tutte le condizioni (es. 600 s), marcata come **provvisoria-conservativa**. Il valore inferiore resta ipotesi da verificare con nuovi dati.
3. **Nessuna soglia passa** (`NONE_PASSES`, cioè t_s oltre 600 s in una quota rilevante delle COLD):
   - nessun valore viene proposto per v0.3;
   - si riporta a Marco la distribuzione osservata;
   - opzioni da valutare separatamente:
     - cap più lungo;
     - cap dipendente dalla condizione (es. dal gap o da ΔT0);
     - uso della flag come WARNING invece di EXCLUDE.
   
   Nessuna di queste è pre-approvata.
4. **Disaccordo inverno/estate:** si ripete la regola sul blocco estivo da solo, con soglie ridotte: n = 10, C1 come k/n ≤ 0,10 senza UCB, più C4 con ΔT0 estivo.
   - Se il valore estivo è **maggiore** di quello invernale, vale il maggiore (principio conservativo) e la decisione va riproposta a Marco.
   - Se è minore o uguale, il valore invernale diventa definitivo.
5. **Test A e Test B in contrasto** (C4 lontano da C1, es. τ piccolo ma t_s lunghi): non cambia la regola, perché servono entrambe. Si riporta come evidenza che il transitorio è dominato dalla custodia e dalla conservazione, non dall'elemento sensibile.
6. **Dati sotto i minimi** (`INSUFFICIENT_DATA`): nessuna decisione.

## 5. Integrazione in v0.3 (solo dopo approvazione di Marco)
Nessun passo di questa sezione è autorizzato oggi. Sequenza proposta, con un task e un'autorizzazione separati:
1. **Rapporto risultati** (`e0/RISULTATI_TAU_WARMUP_<data>.md`): tabelle §1, esito di `decide_cap`, valore proposto. **Approvazione di Marco del valore numerico.**
2. **Implementazione v0.3** (task separato, con autorizzazione esplicita):
   - in `stabilization.py`, il cap `max_window_s` si applica anche alla conferma tardiva (oggi solo a STABILIZATION_NOT_REACHED);
   - nuove config `qc_E0R_<profilo>_v0.3.yaml` con `max_window_s = <valore>`, senza toccare le v0.2;
   - `threshold_provenance.csv` THR-WARM-004 da "engineering_default" a "empirical", con riferimento al rapporto.
3. **Coerenza:** lo stesso valore si applica anche al caso STABILIZATION_NOT_REACHED, che oggi è a 300 s. Se il valore scelto è diverso da 300 s, cambiano anche quelle campagne. Il numero atteso si calcola prima con lo script delle varianti, come in `e0/run_warmup_prereg_rules.py`.
4. **Test di accettazione** (dalla pre-registrazione, aggiornati al valore):
   - AT-1: conteggi attesi riga per riga;
   - AT-2: nessuna flag oltre il valore;
   - AT-3: caso 05-27 13:08;
   - AT-4: harness che dimostra 0 modifiche ad altri rilevatori, suite verde, schema;
   - AT-5: test unitari.
5. **Run versionato** in una nuova cartella `outputs/…_v03_<ts>/`. v0.1 e v0.2 restano intatte.
6. **P1** rieseguito solo come descrittivo. Nessuna QC dichiarata ufficiale senza decisione separata di Marco.

## 6. Limiti dichiarati in anticipo
- **Un solo percorso e uno o due dispositivi:** la generalizzazione ad altri percorsi e velocità è limitata (il blocco ≥ 70 km/h è solo descrittivo).
- **Il riferimento** ha una sua incertezza, ±0,1 °C (k = 2), e un suo tempo di risposta (≤ 5 s); il budget ne tiene conto.
- **La Guard Time dell'app** può nascondere i primi secondi; per questo si registrano `t_out` e `t_move`.
- **Soglie della regola:** 10 %/20 %, ε = 0,2 °C e n = 20/30 sono scelte di progetto motivate nel protocollo, non derivate da norme. Si fissano ora proprio per questo.