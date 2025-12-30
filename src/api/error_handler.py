def enhance_terraform_error(error_message: str) -> str:
    enhancements = {
        "secretmanager.versions.access": (
            "\n\nSOLUTION: Grant Secret Manager Admin role to service account.\n"
            "Command: gcloud projects add-iam-policy-binding PROJECT_ID "
            "--member='serviceAccount:SA_EMAIL' --role='roles/secretmanager.admin'\n"
            "See: infrastructure/base/PERMISSIONS.txt"
        ),
        "cloudsql.instances.create": (
            "\n\nSOLUTION: Grant Cloud SQL Admin role to service account.\n"
            "Command: gcloud projects add-iam-policy-binding PROJECT_ID "
            "--member='serviceAccount:SA_EMAIL' --role='roles/cloudsql.admin'\n"
            "See: infrastructure/base/PERMISSIONS.txt"
        ),
        "storage.buckets.create": (
            "\n\nSOLUTION: Grant Storage Admin role to service account.\n"
            "Command: gcloud projects add-iam-policy-binding PROJECT_ID "
            "--member='serviceAccount:SA_EMAIL' --role='roles/storage.admin'\n"
            "See: infrastructure/base/PERMISSIONS.txt"
        ),
        "compute.firewalls.create": (
            "\n\nSOLUTION: Grant Compute Network Admin role to service account.\n"
            "Command: gcloud projects add-iam-policy-binding PROJECT_ID "
            "--member='serviceAccount:SA_EMAIL' --role='roles/compute.networkAdmin'\n"
            "See: infrastructure/base/PERMISSIONS.txt"
        ),
        "already exists": (
            "\n\nSOLUTION: Resource already exists from previous deployment.\n"
            "Either destroy the existing resource or use a different name/region."
        ),
        "Permission denied": (
            "\n\nSOLUTION: Service account lacks required GCP permissions.\n"
            "See: infrastructure/base/PERMISSIONS.txt for complete list."
        ),
        "Error waiting for Create Instance": (
            "\n\nSOLUTION: Terraform timed out waiting for Cloud SQL instance to be ready.\n"
            "This can happen if the region is congested. Try registering the hospital again (Retry)."
        ),
        "timed out after": (
            "\n\nSOLUTION: The deployment operation timed out.\n"
            "The infrastructure may still be creating in the background. Please wait a few minutes and try again."
        )
    }
    
    enhanced_message = error_message
    
    for keyword, solution in enhancements.items():
        if keyword in error_message:
            enhanced_message += solution
            break
    
    return enhanced_message

