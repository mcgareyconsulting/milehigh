import requests
import os
from dotenv import load_dotenv
import pandas as pd
from io import BytesIO
from app.config import Config as cfg


def get_access_token():
    url = f"https://login.microsoftonline.com/{cfg.AZURE_TENANT_ID}/oauth2/v2.0/token"
    data = {
        "grant_type": "client_credentials",
        "client_id": cfg.AZURE_CLIENT_ID,
        "client_secret": cfg.AZURE_CLIENT_SECRET,
        "scope": "https://graph.microsoft.com/.default",
    }
    r = requests.post(url, data=data)
    r.raise_for_status()
    return r.json()["access_token"]


def read_file_from_user_onedrive(access_token, user_email, file_path):
    url = f"https://graph.microsoft.com/v1.0/users/{user_email}/drive/root:/{file_path}:/content"
    headers = {"Authorization": f"Bearer {access_token}"}
    r = requests.get(url, headers=headers)
    r.raise_for_status()
    return r.content


def list_root_contents(access_token, user_email):
    url = f"https://graph.microsoft.com/v1.0/users/{user_email}/drive/root/children"
    headers = {"Authorization": f"Bearer {access_token}"}
    r = requests.get(url, headers=headers)
    r.raise_for_status()
    return r.json()


def build_unique_identifiers(df):
    """
    Combines 'Job #' and 'Release #' columns into unique identifiers in the format 'Job #-Release #'.
    Returns a list of these identifiers.
    """
    # Drop rows where either value is missing
    filtered = df.dropna(subset=["Job #", "Release #"])
    # Convert to string and combine
    identifiers = (
        filtered["Job #"].astype(str) + "-" + filtered["Release #"].astype(str)
    )
    return identifiers.tolist()


def get_onedrive_identifiers():
    user_email = "mmcgarey@communityinspectionservicesteam.onmicrosoft.com"
    file_path = "Job Log 2.4 DM play toy (1).xlsm"

    token = get_access_token()
    file_bytes = read_file_from_user_onedrive(token, user_email, file_path)
    df = pd.read_excel(BytesIO(file_bytes), header=2)
    return build_unique_identifiers(df)
