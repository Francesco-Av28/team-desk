# team-desk

[![CI](https://github.com/Francesco-Av28/team-desk/actions/workflows/ci.yml/badge.svg)](https://github.com/Francesco-Av28/team-desk/actions/workflows/ci.yml)
[![Licenza: Apache 2.0](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)

**Team di agenti Claude Code su tmux, con regole e budget.** Un leader coordina; ogni membro fa un solo lavoro,
con il modello adatto, dentro i file che gli spettano, dopo i membri da cui dipende.

*[Read in English](README.md)*

![demo di team-desk](docs/demo.gif)

## Perché

La mia prima sessione con un team di agenti ha consumato **36,6 milioni di token in un'ora**. Tutti i compagni giravano
sul modello del leader (Opus), il leader ha avviato in anticipo nove fasi che restavano in attesa, e un membro di
"ricerca di mercato" ha raccolto 517 recensioni senza alcun limite. I numeri sono nel [case study](examples/chess-clone/CASE_STUDY.md).

team-desk trasforma quelle lezioni in impostazioni predefinite:

| Problema visto | Default di team-desk |
|---|---|
| I compagni ereditano il modello costoso del leader | Modello per **tipo di lavoro**: `research` Haiku, `design`/`doc`/`review` Sonnet, `code` Opus. Compagni `general-purpose` vietati |
| Fasi avviate prima che esistano i loro input | Dipendenze `after`: un membro parte solo quando esiste il `.done` di chi lo precede |
| Troppi membri insieme | `max_active` (default 2) |
| Ricerca e scraping senza limiti | 25 turni e 10 ricerche web per membro, niente scraping |
| Membri che si sovrascrivono i file | `owns` per membro, fatto rispettare da un hook PreToolUse |
| La spesa si scopre a cose fatte | `team-desk cost` per membro, soglie al 50% e 80% del budget |
| Ctrl+Z (l'"annulla" di Windows) sospende Claude nel pannello | configurazione tmux opzionale che lo trasforma in annulla |

## Requisiti

Linux, WSL2 o macOS · `python3` (solo libreria standard) · `tmux` · [Claude Code](https://docs.claude.com/en/docs/claude-code)
con gli agent team (team-desk imposta `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` solo nella propria sessione).

## Installazione

```bash
git clone https://github.com/Francesco-Av28/team-desk.git
cd team-desk && ./install.sh            # collega ~/.local/bin/team-desk e ~/.claude/skills/team-desk
team-desk tmux-conf                     # opzionale: mostra la config tmux; con -y la installa (con backup)
```

## Avvio rapido

```bash
cd mio-progetto
team-desk init --propose     # analizza progetto e skill, propone un team, scrive team.json
# oppure, dentro Claude Code: /team-desk   (intervista con opzioni cliccabili)
team-desk up                 # sessione tmux: leader a sinistra (60%), i membri compaiono a destra
```

Il leader ti chiede conferma prima di avviare ogni membro. Intanto, da un altro terminale:

```bash
team-desk status    # in attesa / pronto / al lavoro / bloccato / fatto, e chi è il prossimo
team-desk cost      # turni e token per membro, quota del budget
team-desk dash      # sessione tmux separata che aggiorna stato + costi ogni 30 s
team-desk stop      # Esc in ogni pannello (prima il leader): ferma il lavoro, non chiude nulla
team-desk down      # chiude la sessione del team e la dashboard
```

## team.json

Lo schema completo, con un esempio, è nel [README inglese](README.md#teamjson). In breve:

| Campo | Significato |
|---|---|
| `work` | `research`, `design`, `doc`, `code` o `review`: decide modello e tool di default |
| `role` / `skill` | un compito descritto a parole, una skill da seguire, o entrambi |
| `owns` | i percorsi in cui il membro può scrivere (relativi al progetto, o assoluti per codice tenuto altrove) |
| `after` | i membri che devono aver finito prima |
| `inputs` | i file da leggere per primi |
| `model`, `tools`, `max_turns`, `max_fetches` | eccezioni per singolo membro |

`total_tokens` è in **token pesati**: input 1×, lettura da cache 0,1×, scrittura in cache 1,25×, output 5× (i rapporti
di prezzo di Anthropic). Misura la spesa relativa, vale sia per l'API sia per gli abbonamenti; non è un importo in euro.

## Regime globale (v0.2): tutti i subagent, tutti i progetti

`team-desk global init` mette tutti i subagent sotto un unico regime stretto, anche fuori da tmux e dagli agent team:

| Pezzo | Cosa fa |
|---|---|
| `~/.claude/team-desk/rules.json` | Un solo file di regole: tipi di agente ammessi, domini vietati, tre profili con i loro limiti |
| `~/.claude/agents/td-research.md`, `td-doc.md`, `td-code.md` | Agenti governati: ricerca (Haiku, web, scrive solo in `tmp/`), documenti (Sonnet, niente web, `tmp/`), codice (Opus, niente web, file del progetto) |
| `hooks/td_guard.py` come hook globale `PreToolUse` | Applicato a ogni chiamata: si possono avviare solo agenti `td-*` (il `general-purpose` viene rifiutato); per ogni agente: strumenti ammessi, max 40 azioni, max 15 ricerche web (ricerca), domini vietati, niente comandi di rete senza accesso web, perimetro di scrittura, percorsi protetti (`.claude/`, `.git/`, `.env`) |
| `team-desk cost --global` | Turni e token di ogni subagent in ogni progetto; segnala chi supera 40 turni o 1,5M token pesati, o non è governato |

```bash
team-desk global init -y      # regole + agenti + hook in ~/.claude/settings.json (con backup)
team-desk global status       # profili, hook, chiamate bloccate oggi
team-desk global off | on     # interruttore (anche: TEAMDESK_OFF=1)
team-desk global remove       # toglie l'hook, tiene regole e agenti
team-desk cost --global --hours 24
```

I membri di progetto (`td-<nome>` in `team.json`) tengono i loro strumenti e `max_fetches` e in più ricevono i limiti globali.
I limiti si contano per agente (`agent_id` nell'evento dell'hook). Dopo `init` riavvia le sessioni aperte: gli hook si leggono all'avvio.

## Limiti

- v0.1 (solo team di progetto): tetto di ricerche e divieto di scraping erano istruzioni; con il regime globale v0.2 li applica l'hook.
- I turni sono limitati dal campo `maxTurns` degli agenti; l'hook limita le chiamate agli strumenti (azioni). Una chiamata consentita dall'hook ma poi negata dai permessi viene comunque contata.
- L'hook `owns` controlla i tool che scrivono file (Write, Edit, MultiEdit, NotebookEdit), non i comandi da shell.
- Negli ultimi test (Claude Code 2.1.293) gli hook scritti dentro il file di un agente non venivano eseguiti: per questo il controllo è un hook di progetto.
- Gli agent team sono una funzione sperimentale di Claude Code e il comportamento può cambiare tra versioni.

## Licenza e nome

Codice: [Apache License 2.0](LICENSE). Il nome "team-desk" e il suo logo non sono coperti dalla licenza (vedi [NOTICE](NOTICE)).
