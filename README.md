# TuniSovereign-AI — Track 1 : TunicChain-Sovereign

Projet DS2 2026–2027, ISG Tunis. Plateforme de gestion de l'eau et des ressources agricoles pour les coopératives des gouvernorats de l'intérieur (Kasserine, Sidi Bouzid, Gafsa).

- **Groupe :** Mraihi moataz belleh - Bouali oussema - Zouaghi nour el houda - Labidi oumaima
- **Dépôt :** https://github.com/mraihimoatazbelleh-ui/tunisovereign-ai
- **Rendu :** mardi 8 décembre 2026, 23h59. Soutenances du 9 au 11 décembre 2026.

## État d'avancement

| Semaine | Contenu | État |
| :--- | :--- | :--- |
| 1 | Modèles Django 6, JWT et rôles, REST (DRF), GraphQL (Strawberry + DataLoader), gRPC + simulateur, Docker, UML | Fait, voir `docs/week1_status.md` |
| 2 | Moteur ML (IsolationForest + z-score), serveur FastMCP, 3 skills de l'agent | À faire |
| 3 | Agent LangGraph, contrat Solidity et reçus ZK | À faire |
| 4 | Dashboard Streamlit, workflow n8n, vidéo de démonstration | À faire |

Les dossiers `agent/`, `mcp_server/`, `contracts/`, `dashboard/` et `workflows/` viennent du template du professeur. Ils ne sont pas encore intégrés ni validés par le groupe.

## Architecture de la semaine 1

```text
Simulateur --(gRPC, signé HMAC)--> Serveur gRPC --> Base de données <-- REST (DRF) / GraphQL
 (capteurs)      port 50051                         (7 modèles)         protégés par JWT
```

Diagrammes UML : `docs/uml_class.mmd` et `docs/uml_sequence.mmd` (sources Mermaid).

## Structure du dépôt

```text
backend/
  manage.py
  config/                     # settings.py, urls.py
  tunisovereign_core/
    models.py                 # 7 modèles + StakeholderUser (4 rôles)
    migrations/               # 0001_initial, 0002_agentloopexecution_node
    api_rest.py               # JWT, permissions par rôle, ViewSets, webhook darja
    api_urls.py               # routes /api/v1/
    graphql_schema.py         # schéma Strawberry + DataLoaders
    graphql_urls.py           # vue /graphql/ (JWT obligatoire)
    admin.py
    management/commands/seed_demo.py
    tests_*.py                # modèles, REST, RBAC, GraphQL, gRPC
protos/tunisovereign.proto    # contrat gRPC
grpc_service/                 # server.py, servicer.py, stubs générés
simulator/tunisian_simulator.py
docs/                         # UML et état d'avancement
docker-compose.yml, Dockerfile, .env.example
```

## Prérequis

- Python **3.12** ou plus (Django 6 ne fonctionne pas avec 3.11).
- Base de données : SQLite par défaut. PostgreSQL **15 ou plus** est utilisé dès que `POSTGRES_HOST` est défini (Docker fournit la version 16).

## Lancement en local

Depuis la racine du projet :

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env

cd backend
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

- Administration : http://127.0.0.1:8000/admin/ (créer un compte avec `python manage.py createsuperuser`).
- GraphiQL : http://127.0.0.1:8000/graphql/ (nécessite un token JWT).

### Comptes de démonstration

`seed_demo` crée 6 comptes, tous avec le mot de passe `demo1234` :

| Utilisateur | Rôle |
| :--- | :--- |
| `farmer_kasserine`, `farmer_sidibouzid`, `farmer_gafsa` | COOP_MEMBER |
| `auditor_gafsa` | REGIONAL_AUDITOR |
| `admin_national` | NATIONAL_ADMIN |
| `agent_mcp` | AGENT_SERVICE |

La commande crée aussi 3 coopératives, 3 parcelles et 72 mesures d'humidité (graine aléatoire 42, reproductible). **Relancer `seed_demo` efface et recrée les mesures de ces 3 parcelles.**

## API

### Authentification

| Méthode | Route | Rôle |
| :--- | :--- | :--- |
| POST | `/api/auth/register/` | Ouvert. Le rôle n'est pas modifiable : un nouvel utilisateur est toujours COOP_MEMBER |
| POST | `/api/auth/login/` | Renvoie `access` et `refresh`. Le token contient `role`, `governorate`, `wallet_address`, `preferred_dialect` |
| POST | `/api/auth/refresh/` | Nouveau token d'accès |

Ensuite, envoyer l'en-tête `Authorization: Bearer <access>`.

### REST (`/api/v1/`, pagination de 50)

| Route | Lecture | Écriture | Filtres |
| :--- | :--- | :--- | :--- |
| `cooperatives/` | tout utilisateur connecté | NATIONAL_ADMIN | `governorate` |
| `telemetry/` | tout utilisateur connecté | REGIONAL_AUDITOR, NATIONAL_ADMIN, AGENT_SERVICE | `node`, `metric_type` |
| `anomalies/` | REGIONAL_AUDITOR, NATIONAL_ADMIN, AGENT_SERVICE | NATIONAL_ADMIN | `node`, `severity` |
| `zk-receipts/` | tout utilisateur connecté | lecture seule | `network_name`, `is_verified_on_chain` |
| `darja-intent/` (POST) | tout utilisateur connecté | | |

Validations : quota de coopérative strictement positif et humidité du sol entre 0 et 100, avec réponse 400 claire avant la contrainte SQL. Le webhook `darja-intent/` renvoie 400 si l'entrée est vide ou si une mesure n'est pas un nombre, et 503 si l'agent n'est pas disponible.

### GraphQL (`/graphql/`)

Un token JWT valide est obligatoire (401 sinon). La chaîne Coopérative, Nodes, Anomalies, Exécutions, Receipts est chargée par DataLoader : une seule requête SQL par niveau, quel que soit le nombre de coopératives. Les anomalies et les exécutions de l'agent sont réservées aux rôles REGIONAL_AUDITOR, NATIONAL_ADMIN et AGENT_SERVICE.

```graphql
{
  cooperatives {
    name
    governorate
    nodes { nodeCode receipts { txHash } }
  }
}
```

Exemple avec curl (obtenir d'abord un token via `/api/auth/login/`) :

```bash
curl -X POST http://127.0.0.1:8000/graphql/ \
  -H "Authorization: Bearer <access>" -H "Content-Type: application/json" \
  -d '{"query": "{ cooperatives { name governorate } }"}'
```

## gRPC et simulateur

```powershell
# terminal 1, depuis la racine du projet
python grpc_service/server.py

# terminal 2
python simulator/tunisian_simulator.py            # envoie 216 paquets signés
python simulator/tunisian_simulator.py --tamper   # signatures falsifiées, tout est rejeté
```

Options du simulateur : `--hours`, `--seed`, `--anomaly-hour`, `--no-anomaly`, `--host`, `--dry-run`, `--tamper`. Le serveur vérifie la signature HMAC-SHA256 de chaque paquet (secret `GRPC_HMAC_SECRET`), valide le nœud et la métrique, puis enregistre les mesures par lots.

Après une modification de `protos/tunisovereign.proto`, régénérer les stubs et corriger l'import dans le second fichier :

```powershell
python -m grpc_tools.protoc -I protos --python_out=grpc_service --grpc_python_out=grpc_service protos/tunisovereign.proto
# dans tunisovereign_pb2_grpc.py : remplacer "import tunisovereign_pb2" par "from . import tunisovereign_pb2"
```

## Docker

```powershell
copy .env.example .env
docker compose up -d --build grpc                  # db, migrate (migrations + seed_demo), serveur gRPC
docker compose --profile sim run --rm simulator    # envoie les mesures simulées
docker compose logs grpc
docker compose down
```

Points d'attention :
- Le service `migrate` relance `seed_demo` à chaque démarrage, ce qui efface les mesures des 3 parcelles.
- Le port 5432 de la base est publié sur la machine. En cas de conflit avec un PostgreSQL local, créer un `docker-compose.override.yml` personnel (ignoré par Git) pour changer le port.

## Tests

```powershell
cd backend
python manage.py test                         # toute la suite
python manage.py test tunisovereign_core.tests_grpc -v 2
```

Couverture : contraintes et index des modèles, REST (200, 201, 400, 403, 404), droits par rôle, GraphQL (authentification, droits, nombre de requêtes SQL constant), gRPC (signature, nœud inconnu, métrique invalide, anomalie, horodatage sans fuseau).

## Limites connues

- Le canal gRPC n'est pas chiffré (`insecure_channel`) : TLS ou mTLS en production.
- Un paquet signé peut être rejoué : il faudrait un nonce ou une fenêtre de validité sur l'horodatage.
- Le secret HMAC est partagé : un capteur compromis le révèle.
- L'anomalie gRPC est un simple seuil (humidité sous 35). Elle déclenche un identifiant de thread, mais aucun `AnomalyAndForecastEvent` ni `AgentLoopExecution` n'est encore enregistré. Le ML arrive en semaine 2 et l'agent en semaine 3.
- `bulk_create` n'envoie pas de signaux Django : le module ML devra être appelé explicitement.
- `docker compose up` complet (Redis, Anvil, n8n, dashboard) n'est pas encore validé.
