def enhance_terraform_error(error_message: str) -> str:
    enhancements = {
        "secretmanager.versions.access": (
            "\n\nSOLUTION: Grant Secret Manager Admin role to service account.\n"
            "Command: gcloud projects add-iam-policy-binding PROJECT_ID "
            "--member='serviceAccount:SA_EMAIL' --role='roles/secretmanager.admin'"
        ),
        "cloudsql.instances.create": (
            "\n\nSOLUTION: Grant Cloud SQL Admin role to service account.\n"
            "Command: gcloud projects add-iam-policy-binding PROJECT_ID "
            "--member='serviceAccount:SA_EMAIL' --role='roles/cloudsql.admin'"
        ),
        "storage.buckets.create": (
            "\n\nSOLUTION: Grant Storage Admin role to service account.\n"
            "Command: gcloud projects add-iam-policy-binding PROJECT_ID "
            "--member='serviceAccount:SA_EMAIL' --role='roles/storage.admin'"
        ),
        "compute.firewalls.create": (
            "\n\nSOLUTION: Grant Compute Network Admin role to service account.\n"
            "Command: gcloud projects add-iam-policy-binding PROJECT_ID "
            "--member='serviceAccount:SA_EMAIL' --role='roles/compute.networkAdmin'"
        ),
        "already exists": (
            "\n\nSOLUTION: Resource already exists from previous deployment.\n"
            "Either destroy the existing resource or use a different name/region."
        ),
        "Permission denied": (
            "\n\nSOLUTION: Service account lacks required GCP permissions.\n"
            "Check service account roles and permissions."
        )
    }
    
    enhanced_message = error_message
    
    for keyword, solution in enhancements.items():
        if keyword in error_message:
            enhanced_message += solution
            break
    
    return enhanced_message
