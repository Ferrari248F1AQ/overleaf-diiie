#!/usr/bin/env python3
"""
Applica la patch UNIVAQ DIIIE "purge progetti vecchi" sopra un checkout
pulito di yu-i-i/overleaf-cep (o overleaf/overleaf), PRIMA della build
Docker. Pensato per girare come step del workflow GitHub Actions
raspberrypi/github-actions/build-app-arm64.yml, ma puoi lanciarlo anche a
mano per testare in locale su un checkout del sorgente.

Cosa fa:
  1. Copia due file NUOVI (nessuna sovrascrittura di file esistenti):
       PurgeOldProjectsController.js -> services/web/app/src/Features/ServerAdmin/
       purge-old-projects.pug        -> services/web/app/views/admin/
  2. Inserisce, in modo ancorato a testo letterale, 3 piccole modifiche in
     file esistenti:
       - router.mjs: import del controller + 2 nuove route POST
       - admin/index.pug: un link dal pannello Admin verso la nuova pagina

Se un punto di ancoraggio non viene trovato (es. perche' il fork
yu-i-i/overleaf-cep ha modificato quel file rispetto a quanto mi aspetto),
lo script uscira' con un errore chiaro ed exit code diverso da 0, cosi' la
build su GitHub Actions FALLISCE in modo visibile invece di pubblicare
un'immagine con la patch applicata solo a meta'. Guarda il messaggio
d'errore: indica esattamente quale file e quale testo non ha trovato, cosi'
puoi aggiustare l'ancora qui sotto.

Uso:
  python3 apply-patch.py /percorso/al/checkout/overleaf-cep
"""
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).parent


class AnchorNotFound(Exception):
    pass


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def copy_new_files(root: Path) -> None:
    targets = {
        "PurgeOldProjectsController.js": root
        / "services/web/app/src/Features/ServerAdmin/PurgeOldProjectsController.js",
        "purge-old-projects.pug": root
        / "services/web/app/views/admin/purge-old-projects.pug",
    }
    for src_name, dest in targets.items():
        src = HERE / src_name
        if not src.exists():
            raise AnchorNotFound(f"file sorgente mancante: {src}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
        print(f"[copiato] {src_name} -> {dest}")


def patch_router(root: Path) -> None:
    path = root / "services/web/app/src/router.mjs"
    content = read(path)

    import_anchor = (
        "import AdminController from './Features/ServerAdmin/AdminController.js'"
    )
    if import_anchor not in content:
        raise AnchorNotFound(f"router.mjs: import di AdminController non trovato (atteso: {import_anchor!r})")

    new_import = (
        "import PurgeOldProjectsController from "
        "'./Features/ServerAdmin/PurgeOldProjectsController.js'"
    )
    if new_import not in content:
        content = content.replace(
            import_anchor, import_anchor + "\n" + new_import, 1
        )

    routes_anchor = (
        "  webRouter.post(\n"
        "    '/admin/messages/clear',\n"
        "    AuthorizationMiddleware.ensureUserIsSiteAdmin,\n"
        "    AdminController.clearMessages\n"
        "  )\n"
    )
    if routes_anchor not in content:
        raise AnchorNotFound(
            "router.mjs: blocco route '/admin/messages/clear' non trovato "
            f"(atteso testo letterale):\n{routes_anchor}"
        )

    new_routes = (
        "  webRouter.post(\n"
        "    '/admin/purgeOldProjects/preview',\n"
        "    AuthorizationMiddleware.ensureUserIsSiteAdmin,\n"
        "    PurgeOldProjectsController.preview\n"
        "  )\n"
        "  webRouter.post(\n"
        "    '/admin/purgeOldProjects/execute',\n"
        "    AuthorizationMiddleware.ensureUserIsSiteAdmin,\n"
        "    PurgeOldProjectsController.execute\n"
        "  )\n"
        "  webRouter.get(\n"
        "    '/admin/purge-old-projects',\n"
        "    AuthorizationMiddleware.ensureUserIsSiteAdmin,\n"
        "    PurgeOldProjectsController.form\n"
        "  )\n"
    )
    if "PurgeOldProjectsController.preview" not in content:
        content = content.replace(
            routes_anchor, routes_anchor + new_routes, 1
        )

    write(path, content)
    print(f"[patchato] {path}")


def patch_admin_index_view(root: Path) -> None:
    path = root / "services/web/app/views/admin/index.pug"
    text = read(path)
    lines = text.split("\n")

    anchor_stripped = "h1 Admin Panel"
    idx = None
    for i, line in enumerate(lines):
        if line.strip() == anchor_stripped:
            idx = i
            break
    if idx is None:
        raise AnchorNotFound(
            f"admin/index.pug: riga '{anchor_stripped}' non trovata"
        )

    leading_ws = lines[idx][: len(lines[idx]) - len(lines[idx].lstrip("\t"))]
    parent_indent = leading_ws[:-1] if leading_ws else ""

    link_line = (
        f"{parent_indent}p: a(href='/admin/purge-old-projects') "
        "→ Purge progetti vecchi (libera spazio)"
    )

    if link_line.strip() not in text:
        lines.insert(idx + 1, link_line)
        write(path, "\n".join(lines))
        print(f"[patchato] {path}")
    else:
        print(f"[gia' presente, salto] {path}")


def main() -> None:
    if len(sys.argv) != 2:
        print("Uso: python3 apply-patch.py /percorso/al/checkout", file=sys.stderr)
        sys.exit(2)

    root = Path(sys.argv[1]).resolve()
    if not root.exists():
        print(f"Percorso non trovato: {root}", file=sys.stderr)
        sys.exit(2)

    copy_new_files(root)
    patch_router(root)
    patch_admin_index_view(root)
    print("\nPatch applicata con successo.")


if __name__ == "__main__":
    try:
        main()
    except AnchorNotFound as e:
        print("\nERRORE: punto di ancoraggio non trovato durante il patching.", file=sys.stderr)
        print(str(e), file=sys.stderr)
        print(
            "\nQuesto succede se il fork yu-i-i/overleaf-cep ha un testo "
            "diverso in quel punto rispetto a overleaf/overleaf upstream. "
            "Apri il file indicato, guarda cosa c'e' realmente in quel "
            "punto, e aggiorna la variabile di ancoraggio corrispondente "
            "in questo script (apply-patch.py).",
            file=sys.stderr,
        )
        sys.exit(1)
