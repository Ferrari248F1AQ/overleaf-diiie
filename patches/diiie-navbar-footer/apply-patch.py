#!/usr/bin/env python3
"""
Patch DIIIE per navbar/footer (due modifiche indipendenti):

1. Il link "Sign up" nella navbar punta al modulo di registrazione esterno
   (Microsoft Forms) invece che alla pagina /register di Overleaf, cosi' le
   iscrizioni passano da un modulo controllato invece che dalla
   registrazione libera self-service.

2. Aggiunge in fondo a thin-footer.pug uno <script> con lo stesso nonce CSP
   che Overleaf usa per i propri script inline ("scriptNonce" - verificato
   in services/web/app/views/layout/layout-base.pug e altri file, che tutti
   passano nonce=scriptNonce). Senza il nonce corretto lo script sarebbe
   bloccato dal Content-Security-Policy di Overleaf (script-src usa
   'strict-dynamic', che ignora 'unsafe-inline': verificato dal vivo,
   uno <script> o un handler onerror/onclick iniettato via innerHTML (come
   fa il trucco OVERLEAF_LEFT_FOOTER/OVERLEAF_RIGHT_FOOTER per il CSS) non
   esegue mai). Lo script cerca elementi con classe
   "diiie-obfuscated-email" e attributi data-u/data-d (utente/dominio
   dell'email, in base64) e ricompone l'indirizzo reale (testo + href
   mailto:) solo lato client, dopo il caricamento della pagina: chi legge
   l'HTML grezzo (es. scraper di spam) non vede mai l'indirizzo in chiaro.
   OVERLEAF_RIGHT_FOOTER puo' quindi contenere un elemento del genere
   invece del mailto: in chiaro - vedi README, sezione "Contatto footer".

Uso: python3 apply-patch.py <path-repo-overleaf>
Fallisce (exit 1) con errore chiaro se gli anchor non vengono trovati, cosi'
la build CI si ferma invece di produrre un'immagine con la patch a meta'.
Testato empiricamente contro una copia reale dei due file sorgente prima di
essere collegato al workflow GitHub Actions.
"""
import sys
import pathlib

REGISTER_FORM_URL = "https://forms.office.com/e/cXybJ47Eva"

# Indentazione a TAB per restare coerenti con thin-footer.pug (Pug e'
# sensibile al tipo di indentazione: mescolare tab e spazi nello stesso
# file puo' causare errori di parsing).
EMAIL_SCRIPT = (
    "\n"
    "script(nonce=scriptNonce).\n"
    "\tdocument.addEventListener('DOMContentLoaded', function () {\n"
    "\t\tdocument.querySelectorAll('.diiie-obfuscated-email[data-u][data-d]').forEach(function (el) {\n"
    "\t\t\ttry {\n"
    "\t\t\t\tvar user = atob(el.getAttribute('data-u'))\n"
    "\t\t\t\tvar domain = atob(el.getAttribute('data-d'))\n"
    "\t\t\t\tvar address = user + '@' + domain\n"
    "\t\t\t\tel.textContent = address\n"
    "\t\t\t\tel.setAttribute('href', 'mailto:' + address)\n"
    "\t\t\t} catch (e) {}\n"
    "\t\t})\n"
    "\t})\n"
)


class AnchorNotFound(Exception):
    pass


def patch_signup_link(repo_root: pathlib.Path) -> None:
    path = repo_root / "services/web/app/views/layout/navbar-marketing.pug"
    content = path.read_text(encoding="utf-8")
    anchor = "href='/register'"
    count = content.count(anchor)
    if count != 1:
        raise AnchorNotFound(
            f"Atteso esattamente 1 occorrenza di {anchor!r} in {path}, "
            f"trovate {count}. navbar-marketing.pug e' cambiato: aggiorna "
            "l'anchor in questo script."
        )
    replacement = (
        f"href='{REGISTER_FORM_URL}' target='_blank' rel='noopener noreferrer'"
    )
    content = content.replace(anchor, replacement)
    path.write_text(content, encoding="utf-8")
    print(f"OK: Sign up ora punta a {REGISTER_FORM_URL} ({path})")


def patch_email_obfuscation(repo_root: pathlib.Path) -> None:
    path = repo_root / "services/web/app/views/layout/thin-footer.pug"
    content = path.read_text(encoding="utf-8")
    anchor = "nav.right_footer"
    count = content.count(anchor)
    if count != 1:
        raise AnchorNotFound(
            f"Atteso esattamente 1 occorrenza di {anchor!r} in {path}, "
            f"trovate {count}. thin-footer.pug e' cambiato: aggiorna "
            "l'anchor in questo script."
        )
    content = content.rstrip("\n") + "\n" + EMAIL_SCRIPT
    path.write_text(content, encoding="utf-8")
    print(f"OK: script di deobfuscation email aggiunto ({path})")


def main() -> None:
    if len(sys.argv) != 2:
        print("Uso: python3 apply-patch.py <path-repo-overleaf>", file=sys.stderr)
        sys.exit(1)
    repo_root = pathlib.Path(sys.argv[1])
    try:
        patch_signup_link(repo_root)
        patch_email_obfuscation(repo_root)
    except AnchorNotFound as e:
        print(f"ERRORE: {e}", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError as e:
        print(f"ERRORE: file non trovato: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
