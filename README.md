# SQL Talk with BigQuery

To deploy this app to Cloud Run:

1. cd into the `web-app/` directory

2. Run the following command to have the app built with Cloud Build and deployed
   to Cloud Run, replacing the `service-account` and `project` values with your
   own

```
gcloud run deploy sql-talk --allow-unauthenticated --region us-central1 --service-account sql-talk@koverholt-devrel-355716.iam.gserviceaccount.com --source .
```
