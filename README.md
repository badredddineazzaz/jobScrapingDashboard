# JobScraper

Agrégateur d'offres d'emploi en France. Recherchez simultanément sur LinkedIn, HelloWork, France Travail, Welcome to the Jungle et Adzuna (Indeed, Monster...).

## Fonctionnalités

- **5 sources d'emploi** : LinkedIn, HelloWork, France Travail, WTTJ, Adzuna
- **Recherche géolocalisée** : Filtrage par ville et rayon (5-100 km)
- **Filtres avancés** : Type de contrat, expérience, télétravail, date de publication
- **Export flexible** : JSON, CSV ou affichage tableau
- **CLI intuitive** : Interface en ligne de commande avec Rich

## Installation

```bash
# Cloner le repository
git clone https://github.com/zeffut/jobscraper.git
cd jobscraper

# Créer un environnement virtuel
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# ou .venv\Scripts\activate  # Windows

# Installer les dépendances
pip install -e .
```

## Configuration

Copiez le fichier d'exemple et modifiez selon vos besoins (un fichier `.env`
local est également fourni pour le développement) :

```bash
cp .env.example .env
```

Les paramètres backend sont regroupés dans `.env` : base de données, niveau de
logs, proxy éventuel, activation et délais des sources. Les identifiants
Adzuna sont facultatifs et doivent rester uniquement dans `.env` local :

### Adzuna (optionnel)

Pour utiliser Adzuna (agrégateur Indeed, Monster, etc.), obtenez des clés API gratuites sur [developer.adzuna.com](https://developer.adzuna.com/) et ajoutez-les dans `.env` :

```env
ADZUNA_APP_ID=votre_app_id
ADZUNA_APP_KEY=votre_app_key
```

Le frontend utilise `frontend/.env`. En local, laissez `VITE_API_URL` vide :
Vite proxy alors `/api` vers le backend local. Pour un déploiement séparé,
définissez `VITE_API_URL` avec l'URL publique du backend. Le port du serveur
frontend est contrôlé par `VITE_DEV_SERVER_PORT`. Les fichiers `.env` sont
ignorés par Git ; ne commitez jamais de secrets.

## Utilisation

### Recherche simple

```bash
# Recherche "python" à Paris
jobscraper search -k python -l Paris

# Recherche "data engineer" en CDI
jobscraper search -k "data engineer" -c cdi

# Recherche avec rayon de 25km autour de Lyon
jobscraper search -k développeur -l Lyon -r 25
```

### Options de recherche

```bash
jobscraper search [OPTIONS]

Options:
  -k, --keywords TEXT       Mots-clés de recherche (peut être répété)
  -t, --title TEXT          Titre de poste exact
  -l, --location TEXT       Localisation (ville, région) [défaut: France]
  -r, --radius [5|10|25|50|100]  Rayon de recherche en km
  -c, --contract [cdi|cdd|stage|alternance|interim|freelance]  Type de contrat
  -e, --experience [internship|junior|mid|senior|lead|director]  Niveau d'expérience
  -w, --workplace [on_site|remote|hybrid]  Type de lieu de travail
  --date [past_24h|past_week|past_month|any_time]  Date de publication
  --sort [relevance|date]   Tri des résultats
  -n, --max-results INT     Nombre maximum de résultats [défaut: 50]
  -s, --source [linkedin|hellowork|francetravail|adzuna|wttj|all]  Sources
  -o, --output PATH         Fichier de sortie
  --format [json|csv|table] Format de sortie [défaut: table]
  -d, --details             Récupérer les détails complets
```

### Exemples avancés

```bash
# CDI senior en remote, export JSON
jobscraper search -k "data engineer" -c cdi -e senior -w remote -o jobs.json

# Recherche sur WTTJ uniquement
jobscraper search -k python -l Paris -s wttj

# Recherche sur toutes les sources
jobscraper search -k développeur -l Toulouse -s all

# Offres des 7 derniers jours, triées par date
jobscraper search -k devops --date past_week --sort date

# 100 résultats avec détails complets
jobscraper search -k react -n 100 --details -o react_jobs.json
```

### Lister les sources

```bash
jobscraper sources
```

## Sources supportées

| Source | Statut | Description |
|--------|--------|-------------|
| LinkedIn | Actif | Offres d'emploi LinkedIn |
| HelloWork | Actif | Portail d'emploi français |
| France Travail | Actif | Ex Pôle Emploi |
| WTTJ | Actif | Welcome to the Jungle (startups) |
| Adzuna | Actif* | Agrégateur (Indeed, Monster...) |

\* Nécessite des clés API gratuites

## Architecture

Le projet reste un monolithe modulaire, avec des frontières explicites plutôt
que des microservices prématurés :

- **Frontend** : application React/Vite dans `frontend/`, uniquement cliente
  de l'API HTTP.
- **Backend** : API FastAPI, exécution des runs, persistance et ports
  d'application dans `src/jobscraper/api/` et `src/jobscraper/backend/`.
- **Scraper** : stratégies de collecte, adaptateurs de sites et registre de
  factories dans `src/jobscraper/scrapers/` et
  `src/jobscraper/scraper/`.

Le backend dépend du port `ScraperGateway`, pas des classes concrètes de sites.
Le registre/factory est assemblé dans l'application scraper et peut être
remplacé par des factories de test ou, plus tard, par un worker séparé. Les
recherches longues restent pilotées par événements via le worker local actuel.

## Structure du projet

```
jobscraper/
├── src/jobscraper/
│   ├── cli.py              # Interface ligne de commande
│   ├── config.py           # Configuration
│   ├── backend/
│   │   └── ports.py        # Contrat backend -> scraper
│   ├── scraper/
│   │   └── registry.py     # Factory/registry des scrapers
│   ├── api/                # Application backend FastAPI et worker
│   ├── models/
│   │   └── job.py          # Modèles de données
│   ├── scrapers/
│   │   ├── base.py         # Port des stratégies de scraping
│   │   ├── linkedin.py     # Scraper LinkedIn
│   │   ├── hellowork.py    # Scraper HelloWork
│   │   ├── francetravail.py # Scraper France Travail
│   │   ├── wttj.py         # Scraper WTTJ (Algolia)
│   │   └── adzuna.py       # Client API Adzuna
│   └── utils/
│       └── geocoding.py    # Géocodage pour recherche par rayon
├── .env.example            # Template de configuration
├── pyproject.toml          # Configuration du projet
└── requirements.txt        # Dépendances
```

Les détails d'un site restent encapsulés dans une stratégie `BaseScraper`.
`ScraperRegistry` sélectionne la stratégie à créer, tandis que les repositories
isolent l'accès à la base de données.

## Développement

```bash
# Installer les dépendances de développement
pip install -e ".[dev]"

# Lancer les tests
pytest

# Formater le code
black src/
isort src/
```

### Base de données

Le dashboard utilise SQLite par défaut (`data/jobscraper.db`) et accepte une URL
PostgreSQL via `JOBSCRAPER_DATABASE_URL`.

```bash
# Créer ou mettre à jour le schéma
python -m alembic upgrade head

# Revenir d'une migration
python -m alembic downgrade -1
```

La couche `PersistentSearchRunner` enregistre chaque exécution, les résultats par
source et les offres normalisées. Une même offre trouvée plusieurs fois conserve
un seul enregistrement canonique tout en restant liée à chaque recherche et à
chaque source.

### API du dashboard

```bash
# Appliquer les migrations puis lancer l'API locale
python -m alembic upgrade head
python -m uvicorn --app-dir src jobscraper.api.app:app --reload --port 8001
```

L'API est disponible sur `http://localhost:8001`, sa documentation interactive
sur `http://localhost:8001/docs`, et son schéma OpenAPI sur
`http://localhost:8001/openapi.json`.

Principales routes :

- `POST /api/search-runs` lance une recherche en arrière-plan.
- `GET /api/search-runs/{id}` retourne son état persistant.
- `GET /api/search-runs/{id}/events` diffuse sa progression en SSE.
- `POST /api/search-runs/{id}/cancel` demande son annulation.
- `GET /api/jobs` fournit pagination, recherche, filtres et tri.
- `GET /api/jobs/{id}` retourne une offre et ses sources.

### Interface web

Le frontend React/TypeScript se trouve dans `frontend/`.

```bash
# Terminal 1 — API
python -m alembic upgrade head
python -m uvicorn --app-dir src jobscraper.api.app:app --reload --port 8001

# Terminal 2 — interface
cd frontend
npm install
npm run dev
```

Ouvrez ensuite `http://localhost:5173`. En développement, l'interface appelle
directement l'API sur `http://localhost:8001`. L'API autorise l'origine du
frontend via CORS. Définissez `VITE_API_URL` si le frontend et l'API sont
déployés sur des domaines différents.

Pour créer le bundle de production :

```bash
cd frontend
npm run build
```

L'interface permet de lancer une recherche multi-source, suivre sa progression,
filtrer les résultats, consulter les détails et gérer favoris, offres masquées,
notes et tags persistés dans la base de données.

### Suivi des candidatures

La phase 5 stocke désormais les favoris, offres masquées, notes et tags dans la
base de données. Depuis le détail d'une offre, utilisez **Track application**
pour l'ajouter au tableau Kanban.

Le pipeline comprend : Saved, Preparing, Applied, Screening, Interview et Offer,
avec les états terminaux Rejected, Withdrawn et Archived. Chaque déplacement
crée un événement d'historique immuable. L'API permet également de gérer les
prochaines actions et tâches de suivi.

Routes principales :

- `GET/POST /api/applications`
- `GET/PATCH /api/applications/{id}`
- `POST /api/applications/{id}/tasks`
- `PATCH /api/tasks/{id}`
- `PATCH /api/jobs/{id}` pour favoris, notes, tags et masquage
- `GET /api/analytics/overview`

### Automatisation et exploitation

La phase 6 ajoute des recherches enregistrées et planifiées. Ouvrez
**Automations** dans la barre latérale pour créer un horaire, l'activer ou le
mettre en pause, le lancer immédiatement, consulter l'état des sources et lire
les notifications. Les horaires sont stockés en base et sont donc restaurés au
redémarrage de l'API.

Routes principales :

- `GET/POST /api/saved-searches`
- `PATCH/DELETE /api/saved-searches/{id}`
- `POST /api/saved-searches/{id}/run`
- `GET /api/notifications`
- `GET /api/health/sources`
- `GET /api/export/jobs.csv`
- `GET /api/export/applications.csv`

Pour lancer l'ensemble avec PostgreSQL, Redis, l'API et l'interface :

```bash
docker compose up --build
```

Ouvrez ensuite `http://localhost:5173`. Les données PostgreSQL et Redis sont
conservées dans des volumes Docker. Copiez `.env.example` vers `.env` avant de
renseigner les clés optionnelles; ne placez jamais de secrets dans
`frontend/.env` car les variables Vite sont intégrées au bundle navigateur.

Le planificateur et les exécutions utilisent actuellement le processus API,
ce qui convient à une installation locale ou mono-instance. Redis est inclus
pour l'adaptateur de workers externes prévu lors d'un déploiement horizontal.

## Contribution

Les contributions sont les bienvenues ! N'hésitez pas à ouvrir une issue ou une pull request.
