# DECISIONE — Cap del warm-up (`qc_sensor_stabilization`), 09/11/2026

**Decisione di Marco Ventura, 09/11/2026 ore 15:31 (Europe/Rome), comunicata via chief of project.**

1. **Principio del cap sul warm-up: APPROVATO.**
   - La finestra di warm-up del primo segmento deve avere un limite temporale massimo anche quando il gate di pendenza conferma la stabilità in ritardo.
   - Motivazione registrata nei chiarimenti (`a70ab1d`, §1 e §5): nelle 4 campagne anomale il warm-up di 14–35 min non corrisponde a un transitorio del sensore.
2. **Valore numerico: APERTO.** Né 300 s né 600 s sono approvati. Il valore sarà fissato solo con la procedura di `e0/PROTOCOLLO_TAU_WARMUP_v1.md` e `e0/PROPOSTA_VALIDAZIONE_TAU_v1.md`, e solo dopo una nuova approvazione di Marco.
3. **L'ipotesi τ ≈ 10 s è RITIRATA.**
   - Il produttore non pubblica τ.
   - Il manuale dell'app MeteoTracker+ rev.1, §9.1 ("≥ 15 °C variation detected over a 30 s interval at 20 km/h, under a stepped temperature change of 30 °C"), documenta solo **τ ≤ 43 s**, e solo nell'ipotesi di risposta del primo ordine (30/ln 2 = 43,3 s).
4. **La pre-registrazione `bbc3121` NON è soddisfatta sulla condizione 3** (T_cap ≥ 10 τ).
   - Con il valore documentato, 10τ può arrivare a 433 s e la condizione resta indeterminata.
   - La selezione T_cap = 300 s di `bbc3121` §4 non è quindi valida come scelta pre-registrata.
   - Le condizioni 1, 2 e 4 restano come evidenza descrittiva: mediana t_q 250 s, IC bootstrap [143; 644] s; punto medio AMT 255 s, intervallo 132–378 s.

**Cosa NON cambia**
- `bbc3121` (pre-registrazione), `db013eb` (sensibilità R descrittiva) e `a70ab1d` (chiarimenti) restano come sono: questo documento li integra e non li riscrive.
- Nessuna modifica a codice QC, config, severità o soglie. v0.3 non è implementata. v0.1 e v0.2 sono preservate. Nessuna QC è dichiarata ufficiale.
- R di P1 resta escluso da qualsiasi criterio di scelta del valore.

**Prossimo passo:** misura empirica di τ e del tempo di stabilità secondo il protocollo, poi applicazione della regola decisionale pre-fissata. Infine proposta del valore a Marco per l'approvazione, e solo dopo implementazione v0.3 in un task separato.