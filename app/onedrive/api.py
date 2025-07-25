import requests
import os
from dotenv import load_dotenv
import pandas as pd
from io import BytesIO
from app.config import Config as cfg


def get_access_token():
    """
    Get an access token for Microsoft Graph API using client credentials.
    """
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


def get_excel_dataframe():
    """
    Get the latest Excel data from OneDrive and return it as a DataFrame
    using optimized column loading.
    """
    token = get_access_token()
    file_bytes = read_file_from_user_onedrive(
        token, cfg.ONEDRIVE_USER_EMAIL, cfg.ONEDRIVE_FILE_PATH
    )

    # Define the columns to read: A-S and AC
    # A-S are columns 0-18, AC is column 28
    usecols = list(range(19)) + [28]

    # Read only the specified columns
    df = pd.read_excel(BytesIO(file_bytes), header=2, usecols=usecols)

    # Select rows 4-200 (indices 3-199)
    df_final = df.iloc[3:200]

    return df_final


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


def update_excel_cell(cell_address, value, worksheet_name="Job Log"):
    """
    Update a specific Excel cell via Microsoft Graph API

    Args:
        cell_address: Excel cell address (e.g., "O155")
        value: Value to set in the cell
        worksheet_name: Name of the worksheet (default: "Sheet1")

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Get access token
        access_token = get_access_token()

        # Build the URL for updating the cell
        user_email = cfg.ONEDRIVE_USER_EMAIL
        file_path = cfg.ONEDRIVE_FILE_PATH

        # URL to update a specific cell range
        url = f"https://graph.microsoft.com/v1.0/users/{user_email}/drive/root:/{file_path}:/workbook/worksheets/{worksheet_name}/range(address='{cell_address}')"

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

        # Payload with the new value
        payload = {"values": [[value]]}

        print(f"Updating Excel cell {cell_address} with value: {value}")
        print(f"URL: {url}")

        # Make the PATCH request
        response = requests.patch(url, headers=headers, json=payload)

        if response.status_code == 200:
            print(f"Successfully updated cell {cell_address} with value '{value}'")
            return True
        else:
            print(f"Error updating Excel: {response.status_code} - {response.text}")
            return False

    except Exception as e:
        print(f"Exception in update_excel_cell: {e}")
        return False


##############################################
## Helper function to get drive and user id ##
##############################################
def get_drive_and_folder_id():
    access_token = get_access_token()
    headers = {
        "Authorization": f"Bearer {access_token}",
    }

    file_path = cfg.ONEDRIVE_FILE_PATH
    user_email = (
        cfg.ONEDRIVE_USER_EMAIL
    )  # e.g., "mmcgarey@communityinspectionservicesteam.onmicrosoft.com"

    url = f"https://graph.microsoft.com/v1.0/users/{user_email}/drive/root:/{file_path}:/parentReference"
    headers = {"Authorization": f"Bearer {access_token}"}
    r = requests.get(url, headers=headers)
    r.raise_for_status()
    parent = r.json()
    drive_id = parent["driveId"]
    folder_id = parent["id"]
    return drive_id, folder_id


if __name__ == "__main__":

    drive_id, folder_id = get_drive_and_folder_id()
    if drive_id and folder_id:
        print("\nUse this in your webhook subscription:")
        print(f"resource: /drives/{drive_id}/items/{folder_id}")
