# Create a BigQuery extension

## Upload the YAML file to GCS

```
gsutil cp extension.yaml gs://...
```

## Create the extension

```
python create.py
```

## Call the extension

```
python query.py
```

## Deploy the backend

```
gcloud run deploy extension --allow-unauthenticated --region us-central1 --source .
```

## Deploy the frontend

```
npm install
```

```
npm run build
```

```
firebase deploy
```
