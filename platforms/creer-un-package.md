# Créer un package (bundle format 2) pour un jeu MPF « custom »

Guide pour un humain : comment transformer un dossier de jeu MPF + Godot (GMC) en package installable sur la plateforme, et ce que fait
chaque outil Python du dépôt. Les règles de référence (clés de `bundle.json`, règles de build, échecs connus) restent dans
[game-bundles.md](game-bundles.md) ; la procédure de portage d'un jeu existant du format 1 au format 2 est dans
[game-bundle-format2.md](game-bundle-format2.md). Cette page est le chemin court : « j'ai un dossier, je veux un package ».

## 1. Principe

Un package est une archive `.tar.xz` de **fichiers et de faits** (décision du propriétaire, 2026-10-30) :

- **Le package contient** : la machine MPF (config, modes, code des règles), le projet Godot avec son import déjà fait, les assets du jeu,
  ses add-ons (art fait une fois et stocké dans un dépôt), le manifeste PuP si le jeu en a un, et `bundle.json` (des faits, aucune commande).
- **Le package ne contient jamais** : un script de démarrage, un outil de réglages, un binaire (GoZen, GMC patché, `dmd_out`,
  `dmd_bridge`, libzedmd, libserum), la ROM, ni **aucun fichier du PuP Pack** (le zip de l'auteur est assigné séparément sur la page).
- **La plateforme** installe, vérifie et lance : `python -m mpf_godot run <game_dir> -c <configs> -- <options Godot> -- <arguments utilisateur>`,
  choisit la sortie DMD, stocke les réglages, détecte la carte (`rpi4`, `rpi5`, `jetson`, `x86`).

Limites : **MPF 0.80.1, GMC 1.0.0, Godot 4.6.3** (versions figées dans `mpf_godot/toolchain.py`). Pas de `mpf-mc`/Kivy, aucun paquet pip en
plus de MPF, le jeu n'écrit que dans son propre dossier (la racine est en lecture seule en production) ou dans `MPF_GAME_DATA`.

## 2. Prérequis du dossier de jeu

1. `project.godot` (avec GMC activé : voir `examples/minimal/`) et le dossier `config/` de MPF **côte à côte** (ils peuvent être à la racine
   du dépôt, alors `game_dir` vaut `.`).
2. Les configs MPF découpées par matériel : les fichiers communs (`config.yaml`…) d'un côté ; un fichier `hw_virtual.yaml`
   (`hardware: platform: virtual`), `hw_proc.yaml` (`platform: p_roc`)… de l'autre. La plateforme ajoute le jeu de fichiers choisi par le
   réglage *Hardware* (défaut `virtual`).
3. Le jeu lit seulement les variables fixes de la plateforme (`MPF_DMD_OUTPUT`, `MPF_PUP_PACK`, `MPF_ADDONS`, `MPF_BOARD`, `MPF_GAME_DATA`)
   et accepte tout argument utilisateur Godot inconnu. Il ne détecte aucun matériel DMD, n'ouvre aucun port série, ne lance aucun processus.
4. Tous les fichiers dont il a besoin sont dans le dossier (ou listés dans `copy`, voir §4) : le build ne génère rien.
5. `project.godot` a une section `[rendering]` (le build y écrit les formats de texture et s'arrête sinon : « no [rendering] section ») ; mettre
   `config/features=PackedStringArray("4.6", "Mobile")` et `renderer/rendering_method="mobile"` comme `examples/minimal/`.
6. Le code du jeu n'importe que la bibliothèque standard et ce que MPF installe : **pas de PyYAML** (`import yaml` donne `No module named 'yaml'`
   au chargement du premier mode, MPF s'arrête sur `KeyError: 'attract'`), utiliser `ruamel.yaml` (`YAML(typ="safe").load`). Le contrôle
   `mpf_bundlecheck.problems(dossier, python=<venv de la plateforme>, b=bundle.json)` le signale avant l'envoi.
7. Le projet Godot a été importé une fois (`godot --headless --path DOSSIER --import`) pour que la machine n'ait pas à le faire.

## 3. Chemin simple : `make_bundle.py` (un dossier, pas de build)

Pour du code MPF « tel quel » (pas de génération de médias, pas de PuP).

```sh
godot --headless --path ~/ma-machine --import
python3 common/games/make_bundle.py ~/ma-machine --id ma-machine --name "Ma machine" --version 1.0 \
        --hardware virtual=hw_virtual --hardware proc=hw_proc --keep data -o dist/
# dist/ma-machine@1.0.tar.xz  +  dist/ma-machine@1.0.tar.xz.sha256
```

| | |
|---|---|
| **Fait** | copie le dossier dans `game/` de l'archive, écrit `bundle.json` (format 2), le schéma de réglages, `SHA256SUMS`, l'archive et son `.sha256`. Refuse le package si le contrat est cassé (`mpf_contract.problems`) : `project.godot` ou fichier de config absent, schéma invalide, clé interdite. |
| **Entrées** | `SRC` (dossier MPF + Godot) ; `--id` (minuscules, chiffres, `. _ -`), `--version` ; `--configs` (défaut `config`) ; `--hardware NOM=cfg1,cfg2` (répétable ; ≥ 2 jeux ajoutent un réglage *Hardware* sur la page) ; `--settings FICHIER` (schéma de réglages du jeu) ; `--keep CHEMIN` (conservé d'une version à l'autre : scores, audits…) ; `--dmd-rom` ; `--pup-rom` + `--pup-manifest` (ensemble) ; `--arch` (`all` par défaut) ; `--platform-addon` (défaut `gde_gozen`, `mpf-gmc`) ; `--exclude` ; `--description`, `--icon`. |
| **Sortie** | `<id>@<version>.tar.xz` + `.sha256`. Dossier unique `<id>@<version>/` contenant `bundle.json`, `SHA256SUMS`, `settings.json` (si réglages) et `game/…`. Ne génère rien d'autre : pas d'import Godot (avertit s'il manque `.godot/`), pas de texture VRAM. |

Limite : pas d'import avec compression VRAM ni de contrôle des imports Python ; pour un jeu avec beaucoup de textures, utiliser le chemin §4.

## 4. Chemin complet : `bundle_spec.json` + `python -m mpf_godot bundle`

Pour un jeu avec médias générés, textures à compresser pour le GPU (S3TC sur PC, ETC2 sur Pi 4/Jetson), add-ons et manifeste PuP.
Le jeu se décrit dans un `bundle_spec.json` **à la racine de son dépôt** ; l'exemple commenté est `examples/bundle/bundle_spec.json`, le schéma JSON
`schema/game_package.schema.json`.

```sh
python -m mpf_godot setup --no-monitor                 # une fois : MPF, Godot 4.6.3, GMC patché (outil de la plateforme)
python -m mpf_godot bundle bundle_spec.json --target all --version 1.4.0 --label base --out dist
# dist/<id>-1.4.0-base-linux-all.tar.xz  +  .sha256
```

| | |
|---|---|
| **Fait (dans l'ordre)** | 1. met en place les fichiers suivis par git (`git_tracked`, moins `git_exclude`) + la liste `copy` (config/médias/sons générés) ; s'arrête si un chemin `never` ou un motif `never_names` (`data`, `audits`, `logs`, `*.local.cfg`) s'y trouve. 2. écrit les fichiers `.import` manquants (`import_seed`) / force la compression VRAM (`force_vram`). 3. lance l'import Godot (`--headless --import`, deux fois) pour les formats de texture de la cible. 4. n'emballe aucun binaire (`platform_addons` va dans `bundle.json`). 5. écrit `bundle.json` (copie telle quelle les faits `game_dir`, `mpf`, `dmd`, `pup`, `addons`, `settings`, `profiles`…), vérifie le contrat (`mpf_contract.problems`), écrit `SHA256SUMS` et l'archive. |
| **Entrées** | le spec ; `--target all\|arm64\|x86_64` (`all` = un seul paquet pour toutes les machines, ~300 Mo pour un jeu à images HD) ; `--version`, `--label` (nom : `<id>-<version>-<label>-linux-<cible>`, jamais de hash de commit) ; `GODOT=` ou `mpf_godot setup` fait. |
| **Sortie** | l'archive `.tar.xz`, son `.sha256`, `bundle.json` avec la section `source` (commit du jeu). |

Clés du spec à connaître : `"format": 2` (obligatoire), `game_dir`, `mpf.configs`, `mpf.hardware`, `settings.schema` (aussi dans `copy`), `profiles`
(données par carte), `platform_addons` (`mpf-gmc` toujours, `gde_gozen` si vidéos, `dmd_out` si le jeu rend un DMD 128x32), `addons`,
`pup.manifest`, `keep_on_update`. **Interdit** en format 2 : `run`, `launch`, `options.tool`, `extra`, `requires.env`, `pup.install`… (le build refuse).

Un jeu qui génère médias/config ou a des étapes avant le build les place **dans son propre dépôt** (convention : `scripts/setup.py` puis
`scripts/package/build_bundle.py`, qui écrit le spec et appelle `mpf_godot bundle`) ; la plateforme n'en connaît rien. Le jeu porte aussi
`scripts/package/game_package.json` (sa description de package).

### Rebuild rapide pendant les tests : `--fast`

Quand le dépôt du jeu contient déjà tous ses médias (rien n'est généré), refaire le package n'est qu'un **réemballage** : seul l'import
Godot travaille vraiment. Avec `--fast`, l'arbre préparé et son import Godot sont **gardés** dans `dist/cache/<id>-<cible>/` ; chaque build
ne copie que les fichiers changés (taille ou date), supprime ceux qui ont disparu, Godot ne réimporte que les médias modifiés, les SHA256
des fichiers inchangés sont repris, et l'archive est faite en `xz -0` (PNG et OGG sont déjà compressés).

```sh
python -m mpf_godot bundle bundle_spec.json --target all --label test --fast --out dist
python3 common/games/build_game_package.py ~/mon-jeu --skip-setup --allow-branch --fast --out dist   # même chose via l'outil complet
```

Le premier build `--fast` coûte autant qu'un build normal ; les suivants prennent quelques secondes plus l'import de ce qui a changé.
Garder `--target all` (une cible unique élague l'import gardé et force un réimport complet). Le package livré se fait toujours sans
`--fast`, depuis main. Détails : [game-bundles.md](game-bundles.md#fast-rebuild---fast-the-test-loop).

## 5. Réglages, add-ons, PuP : ce qui est déclaré

- **Réglages** : un fichier JSON `groups` + `options` ; chaque option (`id`, `group`, `label`, `type` bool/choice/integer/number/string, `default`…)
  a **une seule** cible : `{"godot_arg": "--nom"}` (reçu comme `--nom=valeur` par `OS.get_cmdline_user_args()`), `{"ini": "chemin", "section": "s",
  "key": "k"}` (écrit avant chaque démarrage), ou `{"hardware": true}`. Les valeurs sont gardées dans `.platform/settings.json`.
- **Profils** (`profiles.<carte>`) : `limits`, `defaults`, `godot_args`, en données uniquement.
- **Add-ons du jeu** (`addons`: `id`, `dir`, `setting`, `when`) : art fait **une fois, hors build**, versionné dans le dépôt du jeu, copié tel quel dans
  `addons/<id>/`. Passés au jeu par `MPF_ADDONS`. Le build ne génère rien.
- **PuP** : le pack reste le zip de son auteur, assigné sur la page. Le paquet contient seulement le **manifeste** (liste des fichiers du pack utilisés :
  chemin, taille, durée), écrit une fois par le créateur du jeu et commité ; le jeu lit le pack en place via `MPF_PUP_PACK`. Le dépôt du jeu
  contient tout sauf le pack lui-même.
- **DMD** : le jeu ne rend que le DMD 128x32 exact ; la plateforme choisit LCD / PIN2DMD / ZeDMD et gère Serum (`dmd.rom` = colorisation par défaut).

## 6. Vérifier avant d'installer

| Outil | Ce qu'il fait | Entrées | Sortie |
|---|---|---|---|
| `common/netconfig/mpf_contract.py` | le contrat format 2 : `problems(bundle.json, dossier)` liste ce qui le casse ; `plan(dossier, bundle, carte)` donne ce que la plateforme lancerait | un `bundle.json` + le dossier décompressé | liste de problèmes ou plan (configs, arguments Godot, clés ini, environnement) |
| `common/netconfig/mpf_bundlecheck.py` | suit les `import` Python de tous les `.py` sous `game_dir` ; signale tout module absent du paquet et non installé | dossier décompressé, Python du jeu | liste des modules manquants (même contrôle que la page ; un paquet refusé laisse le jeu actif intact) |
| `common/games/build_game_package.py` | construit le paquet d'un jeu depuis son dépôt (URL git ou clone) : met en place le dépôt, lance le `setup` et le `build` **du jeu** (`mpf-package.json`, convention SAM ou `bundle_spec.json`), puis vérifie l'archive (sha256, `bundle.json`, add-ons existants, pas de données de machine, pas de GoZen dans un paquet universel) ; refuse un commit qui n'est pas sur la branche par défaut (`--allow-branch` pour un essai) ; `--publish URL` envoie sur WebDAV | URL/dossier du jeu, `--ref`, `--version`, `--label`, `--target`, `--skip-setup`, `--check`, `--dry-run` | l'archive + `.sha256`, taille, hash, et (option) dépôt WebDAV avec `mpf-games.json` |
| `common/games/check_installed.sh 60` | sur la machine : redémarre `mpf-game.service` et vérifie 60 s qu'il reste actif sans redémarrage (sinon affiche le journal) | durée en secondes | OK / échec + premières erreurs. **Un paquet qui « passe » le build n'est pas encore un paquet qui tourne** : toujours l'exécuter. |
| `common/games/replay_scenario.py` | rejoue dans un MPF en marche un scénario enregistré par le *Monitor* de la page (changements de switch minutés) | `scenario.json`, `--host`, `--port` (BCP, 5051), `--speed`, `--wait` | code 0 ok / 1 switch inconnu / 2 connexion impossible : test de non-régression après un changement de règles |

Un paquet n'a pas les add-ons de la plateforme (GMC) : pour l'essayer dans le bac à sable, `python -m mpf_godot addons DOSSIER/game`, puis **relancer deux fois**
`godot --headless --path DOSSIER/game --import` (sinon `Could not find base class "MPFSlide"`, GMC n'ouvre jamais le port 5050), puis
`python -m mpf_godot run DOSSIER/game -c config,hw_virtual --seconds 40 --xvfb` ; l'attract est atteint quand `logs/*mpf-vm.log` contient
`mode_attract_started` et aucun `Traceback`. Sans GPU (`VK_KHR_surface not found`) Godot continue quand même.
Un dossier `.csv` dans le projet Godot est importé comme traduction (`*.translation` écrits à côté) : sans conséquence, à ignorer dans git.

Test sans machine : décompresser l'archive et lancer
`python3 -c "import sys; sys.path.insert(0,'common/netconfig'); import json, mpf_contract as K; b=json.load(open('DIR/bundle.json')); print(K.problems(b,'DIR') or 'ok'); print(K.plan('DIR', b, 'x86'))"`.
Sur un PC : `python -m mpf_godot run DOSSIER -c config,hw_virtual` (lance Godot/GMC puis MPF, options : `--monitor`, `--seconds`) est exactement ce que la plateforme exécute.
`python -m mpf_godot addons DOSSIER --video [--dmd]` copie le GMC patché (et GoZen / `dmd_out`) dans un dossier de jeu pour ce test.

## 7. Livrer

| Outil | Ce qu'il fait | Entrées | Sortie |
|---|---|---|---|
| Page de réglages (port 8080, *Games*) ou boîte `/data/inbox/` | vérifie `.sha256`, déballe, contrôle `target.os/arch`, `sha256sum -c`, contrat + imports, installe les add-ons de la plateforme (`platform_addons`), reporte `keep_on_update`, bascule | l'archive (+ `.sha256`) | jeu dans `/opt/games/<id>@<version>` (`/data/persist/games` en production), l'ancienne version est gardée |
| `common/games/inject_image.py` | ajoute à une image disque **avant le flash** une partition `mpfdata` avec `inbox/` (bundles, packs PuP) ; installés au premier démarrage comme un envoi sur la page ; ne touche pas aux autres partitions, sans root ni réseau | `IMAGE(.img/.xz/.gz)`, `--bundle FICHIER…` (le premier devient actif), `--pup ZIP[:JEU]`, `-o`, `--extra-mb` | image `*-games.img` (Pi 4, x86 ; Jetson : copier dans l'inbox en SSH) |
| `common/games/webdav_tidy.py` | range un dossier de mises à jour WebDAV : un sous-dossier par jeu, `PuP Packs` pour les zips ; sans `--apply` montre seulement ; `--put-pack ZIP` ajoute un pack | URL WebDAV, `WEBDAV_USER` / `WEBDAV_PASS` | fichiers déplacés, `mpf-games.json` suivi |

Pour mettre à jour un jeu installé (nouvelle version) : même procédure, la version précédente reste choisissable et ses réglages, scores
(`keep_on_update`) et pack PuP sont repris.

## 8. Liste de contrôle

- [ ] Dossier : `project.godot` + `config/`, importé ; configs découpées par matériel ; MPF 0.80.1 / GMC 1.0.0 / Godot 4.6.3.
- [ ] Aucun pip, aucune génération au démarrage, aucune commande dans `bundle.json` ; le jeu n'écrit que dans son dossier.
- [ ] Rien de cabinet (`data`, `audits`, `logs`, `*.local.cfg`) ; ils sont dans `keep_on_update` seulement.
- [ ] `platform_addons` correct ; aucun binaire dans le paquet ; aucun fichier du PuP Pack (manifeste et add-ons : oui).
- [ ] Construit depuis la branche par défaut fusionnée, `mpf_contract.problems` vide.
- [ ] **Installé sur une machine et lancé** : `check_installed.sh 60`.

Non vérifié par ces outils : qu'un jeu ne supportant pas un DMD 128x32 (`dmd_out`) fonctionne sur ZeDMD / PIN2DMD ; laisser la sortie DMD sur LCD dans ce cas.
