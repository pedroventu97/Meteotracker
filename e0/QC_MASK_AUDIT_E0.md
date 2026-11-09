# Audit maschere QC E0 (flag_table_E0 vs keep_*)

Lancio: `python e0/run_qc_mask_audit_e0.py [--n-boot 1000]`. Scrive in una nuova cartella `outputs/qc_mask_audit_E0_<YYYYMMDDTHHMM>`. Per rigenerare solo le figure: `--figures-only <cartella>`. Gli input sono in sola lettura: `outputs/e0_qc_split_20261105T1703/` (split parquet, flagged.csv, `flag_table_E0.parquet`).

## Metodo
- **Stato per punto:**
  - `exclude` se esiste almeno una riga FT con severity exclude (source_row ≥ 0);
  - `warn_only` se ci sono solo warn/info;
  - `ok` altrimenti.

  Le righe file-level DUP_* sono ignorate.
- **Confronto:** contro `keep_permissive/recommended/restrictive`. Per ogni maschera: confusione, accordo e κ di Cohen, globali e per campagna.
- **Disaccordo per flag_code**, nelle due direzioni:
  - FT exclude e pipeline tiene;
  - pipeline scarta e nessun FT exclude.

  Riporta i punti con il codice e i punti in cui il codice è l'unico.
- **Mappa severità** schema E0 ↔ `config/flag_policy.csv`, con numeri di riga, e controllo degli alias.
- **Tassi** per route, blocco 500 m, fascia di quota, ora Europe/Rome, campagna e giorno; 5 esempi.
- **Impatto P1** con `meteotracker_qc.p1_repeatability`: stessi parametri, seed 20261109, coppie di giorni diversi. Maschere:
  - recommended;
  - consensus = recommended ∧ nessun FT exclude;
  - union = recommended ∨ nessun FT exclude;
  - solo flag-table.

Test: `tests/test_qc_mask_audit.py`. Livello: IMPLEMENTATO / TESTATO / NON VALIDATO. L'audit non dichiara alcuna QC ufficiale.
