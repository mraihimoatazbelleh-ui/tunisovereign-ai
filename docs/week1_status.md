# État de la semaine 1 (au 20 novembre 2026)

Projet TuniSovereign-AI, Track 1 TunicChain-Sovereign. Ce document dit ce qui a été vérifié, comment, et ce qui reste à faire.

## Vérifié, avec la preuve

- **Modèles et migrations** : `python manage.py makemigrations --check --dry-run` répond `No changes detected`. Les migrations `0001_initial` et `0002_agentloopexecution_node` s'appliquent sur PostgreSQL. 15 tests dans `tests_models.py` (contraintes, valeurs par défaut, index, reçu unique).
- **Authentification JWT et droits par rôle** : inscription, connexion et rafraîchissement du token, avec le rôle dans le token. Lecture ouverte à tout utilisateur connecté, écriture réservée par rôle. 10 tests dans `tests_rbac.py`.
- **REST (DRF)** : ViewSets, filtres, validation, codes 200, 201, 400, 403 et 404. 12 tests dans `tests_rest.py`.
- **GraphQL** : DataLoader, nombre de requêtes SQL constant quand les données augmentent (test dans `tests_graphql.py`).
- **gRPC et simulateur** : le simulateur envoie 216 paquets signés (HMAC) au serveur gRPC. Résultat : `accepted=216 rejected=0`, et 216 lignes `TelemetryReading` avec `ingestion_protocol='gRPC'` en base. Avec `--tamper`, les 216 paquets sont rejetés.
- **Suite complète** : `python manage.py test` donne 44 tests `OK` sur `main`.

## Correctif en cours

- **GraphQL sans authentification** : `/graphql/` répondait sans token et exposait anomalies et reçus à tout le monde. Correctif dans la branche `fix/graphql-auth` : JWT obligatoire, anomalies et exécutions de l'agent réservées aux rôles auditeur, administrateur et agent, ajout du type des exécutions de l'agent.

## Non vérifié

- **`docker compose up`** : à prouver par un membre qui a Docker (capture de tous les services démarrés).

## À faire

- Ré-exporter les deux PNG du UML (`docs/uml-class.png`, `docs/uml-sequence.png`) à partir des `.mmd` à jour.
- Mettre à jour le README et le rapport (PostgreSQL, migration `0002`, champ `node`, droits par rôle).

## Notes pour la suite

- **gRPC** : le seuil d'humidité renvoie `anomaly_triggered` et un `thread_id`, mais aucun `AnomalyAndForecastEvent` ni `AgentLoopExecution` n'est enregistré. À brancher avec le module ML (semaine 2) et l'agent (semaine 3).
- **gRPC** : `timezone.utc` a été retiré de Django 5.0, il faut utiliser `datetime.timezone.utc` pour les horodatages sans fuseau.
- **gRPC** : un paquet signé peut être rejoué. Un nonce ou une fenêtre de validité sur l'horodatage règlerait le problème.
- **Docker** : `env_file: .env` exige un `.env` (ignoré par Git), le simulateur est dans le profil `sim`, et le service `migrate` relance `seed_demo`, qui efface les mesures des 3 parcelles à chaque démarrage.
